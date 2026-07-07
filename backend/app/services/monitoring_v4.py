"""Medisoft Guardian Monitoring Backend v4.

Cloud-side collector integrated inside the FastAPI backend.
It reads registered health centres, collects cloud replica status from local
cloud MySQL channels, compares latest local agent payloads, and updates the
existing dashboard tables. No separate cloud collector service is required.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()

INTERVAL_SECONDS = 60


def _now() -> datetime:
    return datetime.utcnow()


def _value(row: Any, *keys: str, default: Any = None) -> Any:
    if not row:
        return default
    d = dict(row)
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in d:
            return d[k]
        lk = str(k).lower()
        if lk in lower:
            return lower[lk]
    return default


def _norm_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        s = v.strip().replace("T", " ").replace("Z", "")
        try:
            return datetime.fromisoformat(s).replace(tzinfo=None)
        except Exception:
            return None
    return None


def _safe_channel(channel: str) -> str:
    # MySQL channel names in this system are normal identifiers like gasetsa.
    # Still escape single quotes defensively.
    return str(channel or "").replace("'", "''")


def _up(value: Any) -> bool:
    return str(value or "").strip().lower() in {"yes", "on", "online", "running", "ok", "connected", "source"}


def table_exists(db: Session, name: str) -> bool:
    return bool(db.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name=:t
    """), {"t": name}).scalar() or 0)


def column_exists(db: Session, table: str, column: str) -> bool:
    return bool(db.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name=:t AND column_name=:c
    """), {"t": table, "c": column}).scalar() or 0)


def add_column(db: Session, table: str, column: str, ddl: str) -> None:
    if table_exists(db, table) and not column_exists(db, table, column):
        db.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl}"))


def migrate_monitoring_v4(db: Session) -> None:
    """In-place migration. Never drops FK-linked tables."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS cloud_replica_reports (
          id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          foss_id VARCHAR(64) NOT NULL,
          db_name VARCHAR(128) NULL,
          channel_name VARCHAR(128) NULL,
          source_host VARCHAR(255) NULL,
          io_running VARCHAR(16) NOT NULL DEFAULT 'No',
          sql_running VARCHAR(16) NOT NULL DEFAULT 'No',
          seconds_behind FLOAT NULL,
          last_io_error TEXT NULL,
          last_sql_error TEXT NULL,
          checked_at DATETIME NULL,
          created_at DATETIME NOT NULL DEFAULT (now()),
          KEY ix_cloud_replica_reports_foss_id (foss_id),
          KEY ix_cloud_replica_reports_id (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))

    for col, ddl in [
        ("health_center_id", "VARCHAR(36) NULL AFTER foss_id"),
        ("health_center_name", "VARCHAR(255) NULL AFTER health_center_id"),
        ("cloud_database_size_mb", "DECIMAL(12,2) DEFAULT 0 AFTER last_sql_error"),
        ("cloud_table_count", "INT DEFAULT 0 AFTER cloud_database_size_mb"),
        ("cloud_rows_count", "BIGINT DEFAULT 0 AFTER cloud_table_count"),
        ("cloud_latest_time", "DATETIME NULL AFTER cloud_rows_count"),
        ("source_log_file", "VARCHAR(255) NULL AFTER cloud_latest_time"),
        ("read_source_log_pos", "BIGINT NULL AFTER source_log_file"),
        ("relay_log_file", "VARCHAR(255) NULL AFTER read_source_log_pos"),
        ("relay_log_pos", "BIGINT NULL AFTER relay_log_file"),
        ("raw_json", "LONGTEXT NULL AFTER relay_log_pos"),
        ("collected_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER raw_json"),
    ]:
        add_column(db, "cloud_replica_reports", col, ddl)

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS database_integrity_snapshots (
          id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          foss_id VARCHAR(64) NOT NULL,
          health_center_id VARCHAR(36) NULL,
          db_name VARCHAR(128) NULL,
          channel_name VARCHAR(128) NULL,
          local_size_mb DECIMAL(12,2) DEFAULT 0,
          cloud_size_mb DECIMAL(12,2) DEFAULT 0,
          size_difference_mb DECIMAL(12,2) DEFAULT 0,
          local_table_count INT DEFAULT 0,
          cloud_table_count INT DEFAULT 0,
          local_rows_count BIGINT DEFAULT 0,
          cloud_rows_count BIGINT DEFAULT 0,
          rows_difference BIGINT DEFAULT 0,
          local_latest_time DATETIME NULL,
          cloud_latest_time DATETIME NULL,
          status VARCHAR(50) NOT NULL DEFAULT 'unknown',
          summary TEXT NULL,
          checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_integrity_foss_time (foss_id, checked_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """))

    # Source report extensions used by Local Agent v4.
    for col, ddl in [
        ("database_size_mb", "DECIMAL(12,2) DEFAULT 0"),
        ("local_size_mb", "DECIMAL(12,2) DEFAULT 0"),
        ("local_table_count", "INT DEFAULT 0"),
        ("local_rows_count", "BIGINT DEFAULT 0"),
        ("local_latest_time", "DATETIME NULL"),
        ("agent_version", "VARCHAR(50) NULL"),
    ]:
        add_column(db, "source_agent_reports", col, ddl)

    # Dashboard compatibility columns in monitored_databases.
    for col, ddl in [
        ("local_rows_count", "BIGINT DEFAULT 0"),
        ("cloud_rows_count", "BIGINT DEFAULT 0"),
        ("rows_difference", "BIGINT DEFAULT 0"),
        ("local_size_mb", "DECIMAL(12,2) DEFAULT 0"),
        ("cloud_size_mb", "DECIMAL(12,2) DEFAULT 0"),
        ("size_difference_mb", "DECIMAL(12,2) DEFAULT 0"),
        ("local_table_count", "INT DEFAULT 0"),
        ("cloud_table_count", "INT DEFAULT 0"),
        ("latest_local_time", "DATETIME NULL"),
        ("latest_cloud_time", "DATETIME NULL"),
        ("integrity_summary", "TEXT NULL"),
        ("last_integrity_check", "DATETIME NULL"),
        ("integrity_status", "VARCHAR(50) DEFAULT 'unknown'"),
        ("data_health_score", "FLOAT DEFAULT 0"),
        ("drift_detected", "TINYINT(1) DEFAULT 0"),
    ]:
        add_column(db, "monitored_databases", col, ddl)

    # Health center columns used by UI.
    for col, ddl in [
        ("agent_version", "VARCHAR(50) NULL"),
        ("agent_last_report", "DATETIME NULL"),
        ("health_score", "INT NOT NULL DEFAULT 0"),
    ]:
        add_column(db, "health_centers", col, ddl)

    db.commit()


def registered_centers(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT id, foss_id, name, database_name, replication_channel, source_host
        FROM health_centers
        WHERE foss_id IS NOT NULL AND foss_id <> ''
          AND database_name IS NOT NULL AND database_name <> ''
          AND replication_channel IS NOT NULL AND replication_channel <> ''
        ORDER BY name
    """)).mappings().all()
    return [dict(r) for r in rows]


def latest_local(db: Session, foss_id: str) -> Optional[dict]:
    # Prefer source_agent_reports because /api/v1/hybrid/source-report writes there.
    row = None
    if table_exists(db, "source_agent_reports"):
        row = db.execute(text("""
            SELECT * FROM source_agent_reports
            WHERE foss_id=:f
            ORDER BY id DESC
            LIMIT 1
        """), {"f": foss_id}).mappings().first()
    if row:
        d = dict(row)
        # Fill from source_reports if source_agent_reports lacks v4 stats.
        if (not d.get("local_rows_count")) and table_exists(db, "source_reports"):
            sr = db.execute(text("""
                SELECT * FROM source_reports WHERE foss_id=:f
                ORDER BY received_at DESC LIMIT 1
            """), {"f": foss_id}).mappings().first()
            if sr:
                srd = dict(sr)
                d["database_size_mb"] = d.get("database_size_mb") or srd.get("database_size_mb") or 0
                d["local_size_mb"] = d.get("local_size_mb") or srd.get("database_size_mb") or 0
                d["local_table_count"] = d.get("local_table_count") or srd.get("local_table_count") or 0
                d["local_rows_count"] = d.get("local_rows_count") or srd.get("local_row_count") or 0
                d["local_latest_time"] = d.get("local_latest_time") or srd.get("local_latest_time")
                d["agent_version"] = d.get("agent_version") or srd.get("agent_version")
        return d

    if table_exists(db, "source_reports"):
        sr = db.execute(text("""
            SELECT * FROM source_reports WHERE foss_id=:f
            ORDER BY received_at DESC LIMIT 1
        """), {"f": foss_id}).mappings().first()
        if sr:
            srd = dict(sr)
            return {
                "id": srd.get("id"), "foss_id": srd.get("foss_id"),
                "db_name": srd.get("db_name"), "channel_name": srd.get("channel_name"),
                "hostname": srd.get("hostname"), "mysql_status": srd.get("mysql_status"),
                "internet_status": srd.get("internet_status"), "cloud_connection": srd.get("cloud_connection"),
                "cpu_usage": srd.get("cpu_usage"), "ram_usage": srd.get("ram_usage"), "disk_usage": srd.get("disk_usage"),
                "database_size_mb": srd.get("database_size_mb"), "local_size_mb": srd.get("database_size_mb"),
                "local_table_count": srd.get("local_table_count"), "local_rows_count": srd.get("local_row_count"),
                "local_latest_time": srd.get("local_latest_time"), "source_config_ok": srd.get("source_config_ok"),
                "connected_replicas": srd.get("connected_replicas"), "replica_hosts_json": srd.get("replica_hosts"),
                "created_at": srd.get("received_at"), "sent_at": srd.get("sent_at"),
                "agent_version": srd.get("agent_version"),
            }
    return None


def replica_status(db: Session, channel: str) -> dict:
    channel = _safe_channel(channel)
    try:
        row = db.execute(text(f"SHOW REPLICA STATUS FOR CHANNEL '{channel}'")).mappings().first()
    except Exception as exc:
        return {"io_running": "No", "sql_running": "No", "seconds_behind": None, "last_io_error": str(exc), "last_sql_error": "", "source_host": None, "source_log_file": None, "read_source_log_pos": None, "relay_log_file": None, "relay_log_pos": None, "raw": {}}
    if not row:
        return {"io_running": "No", "sql_running": "No", "seconds_behind": None, "last_io_error": "No replica status row found", "last_sql_error": "", "source_host": None, "source_log_file": None, "read_source_log_pos": None, "relay_log_file": None, "relay_log_pos": None, "raw": {}}
    d = dict(row)
    return {
        "io_running": _value(d, "Replica_IO_Running", "Slave_IO_Running", default="No"),
        "sql_running": _value(d, "Replica_SQL_Running", "Slave_SQL_Running", default="No"),
        "seconds_behind": _value(d, "Seconds_Behind_Source", "Seconds_Behind_Master"),
        "last_io_error": _value(d, "Last_IO_Error", default="") or "",
        "last_sql_error": _value(d, "Last_SQL_Error", default="") or "",
        "source_host": _value(d, "Source_Host", "Master_Host"),
        "source_log_file": _value(d, "Source_Log_File", "Master_Log_File"),
        "read_source_log_pos": _value(d, "Read_Source_Log_Pos", "Read_Master_Log_Pos"),
        "relay_log_file": _value(d, "Relay_Log_File"),
        "relay_log_pos": _value(d, "Relay_Log_Pos"),
        "raw": d,
    }


def db_stats(db: Session, schema_name: str) -> dict:
    row = db.execute(text("""
        SELECT ROUND(COALESCE(SUM(data_length + index_length),0)/1024/1024,2) AS size_mb,
               COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema=:s
    """), {"s": schema_name}).mappings().first() or {}
    tables = db.execute(text("""
        SELECT table_name AS t
        FROM information_schema.tables
        WHERE table_schema=:s
        ORDER BY (data_length + index_length) DESC
        LIMIT 25
    """), {"s": schema_name}).mappings().all()
    total_rows = 0
    latest_values: list[datetime] = []
    candidates = ["updated_at", "date_updated", "modified_at", "created_at", "date_created", "created", "date", "visit_date"]

    for item in tables:
        table = _value(item, "t", "T", "table_name", "TABLE_NAME")
        if not table:
            continue
        try:
            c = db.execute(text(f"SELECT COUNT(*) AS c FROM `{schema_name}`.`{table}`")).mappings().first()
            total_rows += int(_value(c, "c", "C", default=0) or 0)
        except Exception as exc:
            logger.debug("cloud count failed for %s.%s: %s", schema_name, table, exc)
        for col in candidates:
            try:
                exists = db.execute(text("""
                    SELECT COUNT(*) AS c FROM information_schema.columns
                    WHERE table_schema=:s AND table_name=:t AND column_name=:c
                """), {"s": schema_name, "t": table, "c": col}).scalar() or 0
                if exists:
                    mx = db.execute(text(f"SELECT MAX(`{col}`) AS latest FROM `{schema_name}`.`{table}`")).mappings().first()
                    dt = _norm_dt(_value(mx, "latest", "LATEST"))
                    if dt:
                        latest_values.append(dt)
            except Exception:
                pass
    return {
        "cloud_database_size_mb": float(_value(row, "size_mb", "SIZE_MB", default=0) or 0),
        "cloud_table_count": int(_value(row, "table_count", "TABLE_COUNT", default=0) or 0),
        "cloud_rows_count": int(total_rows),
        "cloud_latest_time": max(latest_values) if latest_values else None,
    }


def compare(local: Optional[dict], cloud: dict) -> dict:
    local_size = float((local or {}).get("local_size_mb") or (local or {}).get("database_size_mb") or 0)
    local_rows = int((local or {}).get("local_rows_count") or (local or {}).get("local_row_count") or 0)
    local_tables = int((local or {}).get("local_table_count") or 0)
    cloud_size = float(cloud.get("cloud_database_size_mb") or 0)
    cloud_rows = int(cloud.get("cloud_rows_count") or 0)
    cloud_tables = int(cloud.get("cloud_table_count") or 0)
    rows_diff = local_rows - cloud_rows
    size_diff = round(local_size - cloud_size, 2)
    if not local:
        status, summary = "waiting_local", "Waiting for local agent payload."
    elif local_rows == 0 and cloud_rows > 0:
        status, summary = "waiting_local_stats", "Local agent is online but has not sent row-count statistics yet. Upgrade/restart Local Agent v4."
    elif abs(rows_diff) <= 10 and abs(size_diff) <= 20:
        status, summary = "healthy", "Local and cloud data look aligned."
    elif abs(rows_diff) <= 1000:
        status, summary = "minor_drift", "Small difference between local and cloud data."
    else:
        status, summary = "major_drift", "Large difference between local and cloud data."
    return {
        "local_size_mb": local_size,
        "cloud_size_mb": cloud_size,
        "size_difference_mb": size_diff,
        "local_table_count": local_tables,
        "cloud_table_count": cloud_tables,
        "local_rows_count": local_rows,
        "cloud_rows_count": cloud_rows,
        "rows_difference": rows_diff,
        "local_latest_time": _norm_dt((local or {}).get("local_latest_time") or (local or {}).get("sent_at")),
        "cloud_latest_time": cloud.get("cloud_latest_time"),
        "status": status,
        "summary": summary,
    }


def health_score(local: Optional[dict], repl: dict, integ: dict) -> int:
    score = 100
    if not local:
        score -= 35
    else:
        if not _up(local.get("mysql_status")): score -= 25
        if not _up(local.get("internet_status")): score -= 10
        if float(local.get("disk_usage") or 0) >= 90: score -= 10
        if float(local.get("ram_usage") or 0) >= 90: score -= 5
        if float(local.get("cpu_usage") or 0) >= 95: score -= 5
    if not _up(repl.get("io_running")): score -= 20
    if not _up(repl.get("sql_running")): score -= 20
    if float(repl.get("seconds_behind") or 0) > 300: score -= 15
    if integ.get("status") in {"major_drift", "critical_drift"}: score -= 15
    elif integ.get("status") == "minor_drift": score -= 5
    return max(0, min(100, score))


def store_result(db: Session, center: dict, local: Optional[dict], repl: dict, stats: dict, integ: dict) -> dict:
    db.execute(text("""
        INSERT INTO cloud_replica_reports (
          foss_id, health_center_id, health_center_name, db_name, channel_name,
          source_host, io_running, sql_running, seconds_behind,
          last_io_error, last_sql_error,
          cloud_database_size_mb, cloud_table_count, cloud_rows_count, cloud_latest_time,
          source_log_file, read_source_log_pos, relay_log_file, relay_log_pos,
          raw_json, checked_at, collected_at
        ) VALUES (
          :foss_id, :health_center_id, :health_center_name, :db_name, :channel_name,
          :source_host, :io_running, :sql_running, :seconds_behind,
          :last_io_error, :last_sql_error,
          :cloud_database_size_mb, :cloud_table_count, :cloud_rows_count, :cloud_latest_time,
          :source_log_file, :read_source_log_pos, :relay_log_file, :relay_log_pos,
          :raw_json, :now, :now
        )
    """), {
        "foss_id": center["foss_id"], "health_center_id": center["id"], "health_center_name": center["name"],
        "db_name": center["database_name"], "channel_name": center["replication_channel"],
        "source_host": repl.get("source_host"), "io_running": repl.get("io_running") or "No", "sql_running": repl.get("sql_running") or "No",
        "seconds_behind": repl.get("seconds_behind"), "last_io_error": repl.get("last_io_error") or "", "last_sql_error": repl.get("last_sql_error") or "",
        "cloud_database_size_mb": stats.get("cloud_database_size_mb") or 0, "cloud_table_count": stats.get("cloud_table_count") or 0,
        "cloud_rows_count": stats.get("cloud_rows_count") or 0, "cloud_latest_time": stats.get("cloud_latest_time"),
        "source_log_file": repl.get("source_log_file"), "read_source_log_pos": repl.get("read_source_log_pos"), "relay_log_file": repl.get("relay_log_file"), "relay_log_pos": repl.get("relay_log_pos"),
        "raw_json": json.dumps(repl.get("raw") or {}, default=str), "now": _now(),
    })
    cloud_report_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    db.execute(text("""
        INSERT INTO database_integrity_snapshots (
          foss_id, health_center_id, db_name, channel_name,
          local_size_mb, cloud_size_mb, size_difference_mb,
          local_table_count, cloud_table_count,
          local_rows_count, cloud_rows_count, rows_difference,
          local_latest_time, cloud_latest_time, status, summary, checked_at
        ) VALUES (
          :foss_id, :health_center_id, :db_name, :channel_name,
          :local_size_mb, :cloud_size_mb, :size_difference_mb,
          :local_table_count, :cloud_table_count,
          :local_rows_count, :cloud_rows_count, :rows_difference,
          :local_latest_time, :cloud_latest_time, :status, :summary, :now
        )
    """), {**integ, "foss_id": center["foss_id"], "health_center_id": center["id"], "db_name": center["database_name"], "channel_name": center["replication_channel"], "now": _now()})

    # Update replication_status with cloud authoritative IO/SQL.
    db.execute(text("""
        INSERT INTO replication_status (id, center_id, channel_name, source_host, io_running, sql_running, seconds_behind, last_io_error, last_sql_error, checked_at)
        VALUES (:id, :cid, :ch, :host, :io, :sql, :lag, :ioerr, :sqlerr, :now)
    """), {"id": str(__import__('uuid').uuid4()), "cid": center["id"], "ch": center["replication_channel"], "host": repl.get("source_host") or center.get("source_host") or "", "io": repl.get("io_running") or "No", "sql": repl.get("sql_running") or "No", "lag": repl.get("seconds_behind"), "ioerr": repl.get("last_io_error") or "", "sqlerr": repl.get("last_sql_error") or "", "now": _now()})

    # Update monitored_databases for existing dashboard.
    md = db.execute(text("SELECT id FROM monitored_databases WHERE health_center_id=:cid AND database_name=:db LIMIT 1"), {"cid": center["id"], "db": center["database_name"]}).mappings().first()
    if not md:
        db.execute(text("""
            INSERT INTO monitored_databases (id, health_center_id, database_name, replica_status, rows_count, data_size_mb, last_checked)
            VALUES (:id, :cid, :db, :status, :rows, :size, :now)
        """), {"id": str(__import__('uuid').uuid4()), "cid": center["id"], "db": center["database_name"], "status": integ["status"], "rows": integ["local_rows_count"], "size": integ["local_size_mb"] or integ["cloud_size_mb"], "now": _now()})
    db.execute(text("""
        UPDATE monitored_databases SET
          replica_status=:replica_status, rows_count=:rows, data_size_mb=:size, last_checked=:now,
          local_rows_count=:local_rows_count, cloud_rows_count=:cloud_rows_count, rows_difference=:rows_difference,
          local_size_mb=:local_size_mb, cloud_size_mb=:cloud_size_mb, size_difference_mb=:size_difference_mb,
          local_table_count=:local_table_count, cloud_table_count=:cloud_table_count,
          latest_local_time=:local_latest_time, latest_cloud_time=:cloud_latest_time,
          integrity_status=:status, integrity_summary=:summary, last_integrity_check=:now,
          data_health_score=:score, drift_detected=:drift
        WHERE health_center_id=:cid AND database_name=:db
    """), {**integ, "cid": center["id"], "db": center["database_name"], "replica_status": "ok" if _up(repl.get("io_running")) and _up(repl.get("sql_running")) else "broken", "rows": integ["local_rows_count"], "size": integ["local_size_mb"] or integ["cloud_size_mb"], "now": _now(), "score": 100 if integ["status"] == "healthy" else 70 if integ["status"] == "minor_drift" else 40, "drift": 0 if integ["status"] == "healthy" else 1})

    score = health_score(local, repl, integ)
    is_online = bool(local and _up(local.get("mysql_status")) and _up(repl.get("io_running")) and _up(repl.get("sql_running")) and float(repl.get("seconds_behind") or 0) <= 30)
    status = "online" if is_online else "partial" if (local or _up(repl.get("io_running")) or _up(repl.get("sql_running"))) else "offline"
    db.execute(text("""
        UPDATE health_centers SET
          status=:status,
          mysql_status=:mysql_status,
          internet_status=:internet_status,
          cloud_connection=:cloud_connection,
          last_seen=COALESCE(:last_seen, NOW()),
          data_size_mb=:data_size_mb,
          cpu_usage=:cpu, ram_usage=:ram, disk_usage=:disk,
          agent_version=:agent_version,
          agent_last_report=COALESCE(:last_seen, NOW()),
          health_score=:health_score
        WHERE id=:id
    """), {
        "id": center["id"], "status": status,
        "mysql_status": (local or {}).get("mysql_status") or "unknown",
        "internet_status": (local or {}).get("internet_status") or "unknown",
        "cloud_connection": (local or {}).get("cloud_connection") or "unknown",
        "last_seen": (local or {}).get("created_at"),
        "data_size_mb": integ["local_size_mb"] or integ["cloud_size_mb"],
        "cpu": (local or {}).get("cpu_usage") or 0,
        "ram": (local or {}).get("ram_usage") or 0,
        "disk": (local or {}).get("disk_usage") or 0,
        "agent_version": (local or {}).get("agent_version") or "monitoring-v4",
        "health_score": score,
    })
    return {"foss_id": center["foss_id"], "io": repl.get("io_running"), "sql": repl.get("sql_running"), "lag": repl.get("seconds_behind"), "integrity": integ["status"], "cloud_report_id": cloud_report_id, "health_score": score}


def collect_once() -> dict:
    db = SessionLocal()
    try:
        migrate_monitoring_v4(db)
        centers = registered_centers(db)
        results = []
        for center in centers:
            try:
                local = latest_local(db, center["foss_id"])
                repl = replica_status(db, center["replication_channel"])
                stats = db_stats(db, center["database_name"])
                integ = compare(local, stats)
                results.append(store_result(db, center, local, repl, stats, integ))
                db.commit()
            except Exception as exc:
                logger.exception("Monitoring v4 failed for %s: %s", center.get("foss_id"), exc)
                db.rollback()
                results.append({"foss_id": center.get("foss_id"), "error": str(exc)})
        return {"ok": True, "centers": len(centers), "results": results, "checked_at": _now().isoformat()}
    finally:
        db.close()


def _loop() -> None:
    logger.info("Monitoring v4 scheduler started")
    while True:
        try:
            collect_once()
        except Exception:
            logger.exception("Monitoring v4 tick failed")
        time.sleep(INTERVAL_SECONDS)


def start_monitoring_v4() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
        t = threading.Thread(target=_loop, name="monitoring-v4", daemon=True)
        t.start()
