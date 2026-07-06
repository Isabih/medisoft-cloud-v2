"""
Local-agent ingestion endpoint for Medisoft Guardian Cloud.

The local agent sends one report every 30-60 seconds directly to:
    POST /api/v1/hybrid/source-report

This endpoint updates the live dashboard, replication history, heartbeat logs,
local status reports, timeline events, and returns queued first-aid actions.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.diagnosis_rules import diagnose_context
from app.services.database_integrity import record_integrity_check

try:
    from app.routers.websocket import ws_manager  # type: ignore
except Exception:  # pragma: no cover
    ws_manager = None

router = APIRouter(prefix="/hybrid", tags=["hybrid"])


def _up(value: Any) -> bool:
    return str(value or "").strip().lower() in {"yes", "on", "online", "running", "ok", "connected"}


def _parse_dt(value: Any):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _score(row: dict) -> int:
    score = 100
    if not _up(row.get("cloud_connection")): score -= 15
    if not _up(row.get("mysql_status")): score -= 20
    if not _up(row.get("io_running")): score -= 20
    if not _up(row.get("sql_running")): score -= 20
    if float(row.get("disk_usage") or 0) >= 90: score -= 10
    if float(row.get("ram_usage") or 0) >= 90: score -= 5
    if float(row.get("cpu_usage") or 0) >= 95: score -= 5
    return max(0, min(100, score))


def _ensure_alert(db: Session, center_id: str, center_name: str, atype: str, severity: str, message: str):
    existing = db.execute(text("""
        SELECT id FROM alerts
        WHERE center_id=:cid AND type=:type AND resolved_at IS NULL
        LIMIT 1
    """), {"cid": center_id, "type": atype}).first()
    if not existing:
        db.execute(text("""
            INSERT INTO alerts (id, center_id, center_name, type, message, severity, created_at)
            VALUES (:id, :cid, :cn, :type, :msg, :sev, :now)
        """), {"id": str(uuid.uuid4()), "cid": center_id, "cn": center_name, "type": atype, "msg": message, "sev": severity, "now": datetime.utcnow()})


def _resolve_alert(db: Session, center_id: str, atype: str):
    db.execute(text("UPDATE alerts SET resolved_at=NOW() WHERE center_id=:cid AND type=:type AND resolved_at IS NULL"), {"cid": center_id, "type": atype})


def _timeline(db: Session, center_id: str, center_name: str, event_type: str, severity: str, title: str, message: str = ""):
    # avoid writing the exact same heartbeat every minute; only write important events or every 15 min info
    db.execute(text("""
        INSERT INTO center_timeline_events (center_id, center_name, event_type, severity, title, message, created_at)
        VALUES (:cid, :cn, :et, :sev, :title, :msg, :now)
    """), {"cid": center_id, "cn": center_name, "et": event_type, "sev": severity, "title": title[:255], "msg": message, "now": datetime.utcnow()})


class SourceReport(BaseModel):
    foss_id: str
    health_center_name: Optional[str] = None
    db_name: Optional[str] = None
    channel_name: Optional[str] = None
    hostname: Optional[str] = None

    mysql_status: Optional[str] = None
    internet_status: Optional[str] = None
    cloud_connection: Optional[str] = None
    vpn_status: Optional[str] = None

    cpu_usage: float = 0
    ram_usage: float = 0
    disk_usage: float = 0
    database_size_mb: float = 0

    source_config_ok: Optional[Any] = 0
    connected_replicas: int = 0
    replica_hosts: Optional[Any] = ""

    io_running: Optional[str] = None
    sql_running: Optional[str] = None
    seconds_behind: Optional[float] = None
    last_io_error: Optional[str] = ""
    last_sql_error: Optional[str] = ""

    local_row_count: int = 0
    local_table_count: int = 0
    local_table_summary_json: Optional[Any] = None
    local_latest_time: Optional[str] = None
    sent_at: Optional[str] = None
    agent_version: Optional[str] = "1.0.0"


@router.get("/health")
def hybrid_health():
    return {"status": "ok", "service": "hybrid-ingestion"}


@router.post("/source-report")
async def source_report(payload: SourceReport, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    center_name = payload.health_center_name or payload.foss_id
    local_latest_dt = _parse_dt(payload.local_latest_time)
    sent_dt = _parse_dt(payload.sent_at) or now
    replica_hosts = payload.replica_hosts
    if isinstance(replica_hosts, (list, tuple, dict)):
        replica_hosts = json.dumps(replica_hosts)
    replica_hosts = str(replica_hosts or "")

    live_row = {
        "cloud_connection": payload.cloud_connection,
        "mysql_status": payload.mysql_status,
        "io_running": payload.io_running,
        "sql_running": payload.sql_running,
        "cpu_usage": payload.cpu_usage,
        "ram_usage": payload.ram_usage,
        "disk_usage": payload.disk_usage,
    }
    health_score = _score(live_row)
    status = "online" if _up(payload.cloud_connection) and _up(payload.mysql_status) else "offline"
    if status == "online" and (not _up(payload.io_running) or not _up(payload.sql_running)):
        status = "partial"

    # 1. Latest source report snapshot
    db.execute(text("""
        INSERT INTO source_reports
          (foss_id, health_center_name, db_name, channel_name, hostname,
           mysql_status, internet_status, cloud_connection, vpn_status,
           cpu_usage, ram_usage, disk_usage, database_size_mb,
           source_config_ok, connected_replicas, replica_hosts,
           io_running, sql_running, seconds_behind, last_io_error, last_sql_error, agent_version, local_row_count, local_table_count, local_table_summary_json, local_latest_time, sent_at, received_at)
        VALUES
          (:foss_id, :name, :db, :ch, :host,
           :mysql, :inet, :cloud, :vpn,
           :cpu, :ram, :disk, :size,
           :cfg, :rep_count, :rep_hosts,
           :io, :sql, :lag, :ioerr, :sqlerr, :agent_version, :rows, :tables, :table_summary, :latest, :sent, :received)
        ON DUPLICATE KEY UPDATE
          health_center_name=VALUES(health_center_name), db_name=VALUES(db_name), channel_name=VALUES(channel_name), hostname=VALUES(hostname),
          mysql_status=VALUES(mysql_status), internet_status=VALUES(internet_status), cloud_connection=VALUES(cloud_connection), vpn_status=VALUES(vpn_status),
          cpu_usage=VALUES(cpu_usage), ram_usage=VALUES(ram_usage), disk_usage=VALUES(disk_usage), database_size_mb=VALUES(database_size_mb),
          source_config_ok=VALUES(source_config_ok), connected_replicas=VALUES(connected_replicas), replica_hosts=VALUES(replica_hosts),
          io_running=VALUES(io_running), sql_running=VALUES(sql_running), seconds_behind=VALUES(seconds_behind), last_io_error=VALUES(last_io_error), last_sql_error=VALUES(last_sql_error), agent_version=VALUES(agent_version),
          local_row_count=VALUES(local_row_count), local_table_count=VALUES(local_table_count), local_table_summary_json=VALUES(local_table_summary_json), local_latest_time=VALUES(local_latest_time), sent_at=VALUES(sent_at), received_at=VALUES(received_at)
    """), {
        "foss_id": payload.foss_id, "name": center_name, "db": payload.db_name or "", "ch": payload.channel_name or "", "host": payload.hostname or "",
        "mysql": payload.mysql_status or "unknown", "inet": payload.internet_status or "unknown", "cloud": payload.cloud_connection or "online", "vpn": payload.vpn_status or "unknown",
        "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage, "size": payload.database_size_mb,
        "cfg": 1 if str(payload.source_config_ok).lower() in ("1", "true", "yes") else 0, "rep_count": payload.connected_replicas, "rep_hosts": replica_hosts,
        "io": payload.io_running or "No", "sql": payload.sql_running or "No", "lag": payload.seconds_behind, "ioerr": payload.last_io_error or "", "sqlerr": payload.last_sql_error or "", "agent_version": payload.agent_version or "1.0.0",
        "rows": payload.local_row_count, "tables": payload.local_table_count, "table_summary": json.dumps(payload.local_table_summary_json or []), "latest": local_latest_dt, "sent": sent_dt, "received": now,
    })

    # 2. Ensure/update health center
    hc = db.execute(text("SELECT id, name, last_seen, status, mysql_status FROM health_centers WHERE foss_id=:f LIMIT 1"), {"f": payload.foss_id}).mappings().first()
    if not hc:
        center_id = str(uuid.uuid4())
        db.execute(text("""
            INSERT INTO health_centers
              (id, name, province, district, foss_id, database_name, replication_channel,
               status, internet_status, mysql_status, cloud_connection, last_seen, last_data_timestamp,
               data_size_mb, cpu_usage, ram_usage, disk_usage, agent_version, agent_last_report, health_score, created_at)
            VALUES
              (:id, :name, '', '', :foss, :db, :ch,
               :status, :inet, :mysql, :cloud, :seen, :data_ts,
               :size, :cpu, :ram, :disk, :agent_version, :agent_report, :score, :now)
        """), {"id": center_id, "name": center_name, "foss": payload.foss_id, "db": payload.db_name or payload.foss_id,
              "ch": payload.channel_name or payload.db_name or payload.foss_id, "status": status, "inet": payload.internet_status or "unknown",
              "mysql": payload.mysql_status or "unknown", "cloud": payload.cloud_connection or "online", "seen": now, "data_ts": local_latest_dt,
              "size": payload.database_size_mb, "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage,
              "agent_version": payload.agent_version or "1.0.0", "agent_report": now, "score": health_score, "now": now})
        db.execute(text("""
            INSERT INTO monitored_databases (id, health_center_id, database_name, replica_status, rows_count, data_size_mb, last_checked)
            VALUES (:id, :cid, :db, :status, :rows, :size, :now)
        """), {"id": str(uuid.uuid4()), "cid": center_id, "db": payload.db_name or payload.foss_id, "status": "ok", "rows": payload.local_row_count, "size": payload.database_size_mb, "now": now})
        _timeline(db, center_id, center_name, "agent", "success", "Agent registered", f"{payload.hostname or ''} started reporting to cloud.")
    else:
        center_id = hc["id"]
        db.execute(text("""
            UPDATE health_centers SET
                name=COALESCE(NULLIF(:name,''), name), database_name=COALESCE(NULLIF(:db,''), database_name), replication_channel=COALESCE(NULLIF(:ch,''), replication_channel),
                status=:status, internet_status=:inet, mysql_status=:mysql, cloud_connection=:cloud, last_seen=:seen, last_data_timestamp=:data_ts,
                data_size_mb=:size, cpu_usage=:cpu, ram_usage=:ram, disk_usage=:disk, agent_version=:agent_version, agent_last_report=:agent_report, health_score=:score
            WHERE id=:id
        """), {"id": center_id, "name": center_name, "db": payload.db_name or "", "ch": payload.channel_name or "", "status": status,
              "inet": payload.internet_status or "unknown", "mysql": payload.mysql_status or "unknown", "cloud": payload.cloud_connection or "online",
              "seen": now, "data_ts": local_latest_dt, "size": payload.database_size_mb, "cpu": payload.cpu_usage, "ram": payload.ram_usage,
              "disk": payload.disk_usage, "agent_version": payload.agent_version or "1.0.0", "agent_report": now, "score": health_score})


    # 2b. Database Integrity & Drift Check (v1.1)
    integrity = None
    try:
        # Ensure monitored_databases row exists for current database even for old centers.
        exists_md = db.execute(text("""
            SELECT id FROM monitored_databases
            WHERE health_center_id=:cid AND database_name=:dbn LIMIT 1
        """), {"cid": center_id, "dbn": payload.db_name or payload.foss_id}).first()
        if not exists_md:
            db.execute(text("""
                INSERT INTO monitored_databases (id, health_center_id, database_name, replica_status, rows_count, data_size_mb, last_checked)
                VALUES (:id, :cid, :dbn, 'ok', :rows, :size, :now)
            """), {"id": str(uuid.uuid4()), "cid": center_id, "dbn": payload.db_name or payload.foss_id,
                  "rows": payload.local_row_count, "size": payload.database_size_mb, "now": now})
        integrity = record_integrity_check(
            db,
            center_id=center_id,
            center_name=center_name,
            foss_id=payload.foss_id,
            database_name=payload.db_name or payload.foss_id,
            local_size_mb=payload.database_size_mb,
            local_rows_count=payload.local_row_count,
            local_table_count=payload.local_table_count,
            local_latest_time=local_latest_dt,
            local_table_summary_json=payload.local_table_summary_json,
        )
        if integrity.get("data_health_score", 100) < 90:
            _ensure_alert(
                db, center_id, center_name, "database_drift", "warning" if integrity.get("data_health_score", 0) >= 70 else "critical",
                f"Database drift detected: {integrity.get('probable_cause')}"
            )
        else:
            _resolve_alert(db, center_id, "database_drift")
    except Exception as exc:
        integrity = {"integrity_status": "check_failed", "probable_cause": str(exc), "recommended_fix": "Check cloud DB permissions and v1.1 migration."}

    # 3. History tables
    db.execute(text("""
        INSERT INTO heartbeat_logs (id, center_id, foss_id, mysql_status, internet_status, cloud_connection, cpu_usage, ram_usage, disk_usage, received_at)
        VALUES (:id, :cid, :f, :mysql, :inet, :cloud, :cpu, :ram, :disk, :now)
    """), {"id": str(uuid.uuid4()), "cid": center_id, "f": payload.foss_id, "mysql": payload.mysql_status or "unknown", "inet": payload.internet_status or "unknown", "cloud": payload.cloud_connection or "online", "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage, "now": now})

    db.execute(text("""
        INSERT INTO replication_status (id, center_id, channel_name, source_host, io_running, sql_running, seconds_behind, last_io_error, last_sql_error, checked_at)
        VALUES (:id, :cid, :ch, :host, :io, :sql, :lag, :ioerr, :sqlerr, :now)
    """), {"id": str(uuid.uuid4()), "cid": center_id, "ch": payload.channel_name or "", "host": "", "io": payload.io_running or "No", "sql": payload.sql_running or "No", "lag": payload.seconds_behind, "ioerr": payload.last_io_error or "", "sqlerr": payload.last_sql_error or "", "now": now})

    db.execute(text("""
        INSERT INTO local_status_reports
          (id, center_id, center_name, agent_status, internet_status, mysql_status, backend_status, cpu_usage, ram_usage, storage_usage,
           local_row_count, cloud_row_count, local_latest_time, cloud_latest_time, compare_status, comparison_message, sync_freshness_minutes, reported_at)
        VALUES
          (:id, :cid, :name, 'online', :inet, :mysql, :cloud, :cpu, :ram, :disk,
           :local_rows, 0, :local_latest, :cloud_latest, :cmp, :msg, :fresh, :now)
    """), {"id": str(uuid.uuid4()), "cid": center_id, "name": center_name, "inet": payload.internet_status or "unknown", "mysql": payload.mysql_status or "unknown", "cloud": payload.cloud_connection or "online", "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage, "local_rows": payload.local_row_count, "local_latest": local_latest_dt, "cloud_latest": local_latest_dt, "cmp": "ok" if status == "online" else "warning", "msg": f"Agent report received at {now.isoformat()}", "fresh": 0, "now": now})

    # 4. Alerts + timeline + AI comment
    if not _up(payload.mysql_status):
        _ensure_alert(db, center_id, center_name, "MYSQL_OFFLINE", "critical", "Local MySQL is offline or not accepting connections.")
        _timeline(db, center_id, center_name, "alert", "critical", "MySQL offline", "Dashboard first aid: Restart MySQL.")
    else:
        _resolve_alert(db, center_id, "MYSQL_OFFLINE")
    if not _up(payload.io_running):
        _ensure_alert(db, center_id, center_name, "REPLICA_IO_OFF", "critical", f"Replica IO thread is {payload.io_running or 'No'}.")
        _timeline(db, center_id, center_name, "replication", "critical", "Replica IO stopped", payload.last_io_error or "Use first aid: Start/Restart Replica.")
    else:
        _resolve_alert(db, center_id, "REPLICA_IO_OFF")
    if not _up(payload.sql_running):
        _ensure_alert(db, center_id, center_name, "REPLICA_SQL_OFF", "critical", f"Replica SQL thread is {payload.sql_running or 'No'}.")
        _timeline(db, center_id, center_name, "replication", "critical", "Replica SQL stopped", payload.last_sql_error or "Use first aid: Start/Restart Replica.")
    else:
        _resolve_alert(db, center_id, "REPLICA_SQL_OFF")
    if payload.disk_usage >= 90:
        _ensure_alert(db, center_id, center_name, "DISK_HIGH", "critical", f"Disk usage is {payload.disk_usage}%.")
    else:
        _resolve_alert(db, center_id, "DISK_HIGH")

    ai_comment = diagnose_context({
        "center": {"mysql_status": payload.mysql_status, "internet_status": payload.internet_status, "cloud_connection": payload.cloud_connection, "cpu_usage": payload.cpu_usage, "ram_usage": payload.ram_usage, "disk_usage": payload.disk_usage, "last_seen": now},
        "replication": {"io_running": payload.io_running, "sql_running": payload.sql_running, "seconds_behind": payload.seconds_behind, "last_io_error": payload.last_io_error, "last_sql_error": payload.last_sql_error},
        "extra": {},
    })

    # 5. Dequeue one action
    action_row = db.execute(text("""
        SELECT id, action, params FROM agent_actions
        WHERE foss_id=:f AND status='pending'
        ORDER BY created_at ASC LIMIT 1
    """), {"f": payload.foss_id}).mappings().first()

    response: Dict[str, Any] = {"ok": True, "center_id": center_id, "health_score": health_score,
        "database_integrity": integrity, "ai_comment": ai_comment}
    if action_row:
        db.execute(text("UPDATE agent_actions SET status='dispatched', dispatched_at=:now WHERE id=:id"), {"id": action_row["id"], "now": now})
        _timeline(db, center_id, center_name, "repair", "info", f"First Aid queued: {action_row['action']}", "Agent will run it on next poll.")
        response.update({"action": action_row["action"], "params": action_row["params"] or "", "action_id": action_row["id"]})

    db.commit()

    if ws_manager is not None:
        try:
            await ws_manager.broadcast({"type": "source_report", "center_id": payload.foss_id, "payload": response, "timestamp": now.isoformat()})
        except Exception:
            pass
    return response


@router.get("/source-reports")
def list_source_reports(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM source_reports ORDER BY received_at DESC")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/source-reports/{foss_id}")
def get_source_report(foss_id: str, db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM source_reports WHERE foss_id=:f"), {"f": foss_id}).mappings().first()
    return dict(row) if row else None
