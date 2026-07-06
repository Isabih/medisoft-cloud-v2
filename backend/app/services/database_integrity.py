"""Database integrity and drift scoring for v1.1.

This module compares what the health-centre agent reports from the local
server with what the cloud replica currently contains. It is intentionally
lightweight: it does not compare every row every minute. It compares size,
table count, selected row counts, and latest update timestamps.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v or default)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v or default)
    except Exception:
        return default


def _dt(v: Any):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def _table_exists(db: Session, schema: str, table: str) -> bool:
    try:
        return bool(db.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema=:schema AND table_name=:table
        """), {"schema": schema, "table": table}).scalar() or 0)
    except Exception:
        return False


def get_cloud_database_stats(db: Session, database_name: str, check_table: str, check_time_column: str) -> Dict[str, Any]:
    """Read cloud-side replica stats for one database/schema."""
    stats = {
        "cloud_size_mb": 0.0,
        "cloud_table_count": 0,
        "cloud_rows_count": 0,
        "latest_cloud_time": None,
    }
    if not database_name:
        return stats

    row = db.execute(text("""
        SELECT
          COALESCE(ROUND(SUM(data_length + index_length)/1024/1024,2), 0) AS size_mb,
          COUNT(*) AS table_count
        FROM information_schema.tables
        WHERE table_schema=:schema
    """), {"schema": database_name}).mappings().first()
    if row:
        stats["cloud_size_mb"] = _safe_float(row["size_mb"])
        stats["cloud_table_count"] = _safe_int(row["table_count"])

    if check_table and _table_exists(db, database_name, check_table):
        try:
            stats["cloud_rows_count"] = _safe_int(db.execute(text(
                f"SELECT COUNT(*) FROM `{database_name}`.`{check_table}`"
            )).scalar())
        except Exception:
            stats["cloud_rows_count"] = 0
        if check_time_column:
            try:
                stats["latest_cloud_time"] = db.execute(text(
                    f"SELECT MAX(`{check_time_column}`) FROM `{database_name}`.`{check_table}`"
                )).scalar()
            except Exception:
                stats["latest_cloud_time"] = None
    return stats


def score_integrity(local_size_mb: float, cloud_size_mb: float, local_rows: int, cloud_rows: int,
                    local_tables: int, cloud_tables: int, latest_local: Any, latest_cloud: Any) -> Tuple[int, str, str, str]:
    """Return (score, status, probable_cause, recommended_fix)."""
    score = 100
    causes: List[str] = []
    fixes: List[str] = []

    # Size difference can be normal because indexes/storage differ; use reasonable thresholds.
    size_diff = max(local_size_mb - cloud_size_mb, 0)
    size_pct = (size_diff / local_size_mb * 100) if local_size_mb > 0 else 0
    if size_pct > 20 and size_diff > 100:
        score -= 20
        causes.append(f"Cloud database is {size_diff:.1f} MB smaller than local database.")
        fixes.append("Confirm replication filters, check stopped SQL/IO thread, and verify the cloud schema belongs to the same health centre.")
    elif size_pct > 10 and size_diff > 50:
        score -= 10
        causes.append(f"Cloud database size is behind local by {size_diff:.1f} MB.")
        fixes.append("Monitor replication lag and compare important table counts.")

    if local_tables and cloud_tables and local_tables != cloud_tables:
        score -= 20
        causes.append(f"Table count mismatch: local={local_tables}, cloud={cloud_tables}.")
        fixes.append("Check missing tables, replication ignore/do-db rules, and recent restore/migration differences.")

    row_diff = max(local_rows - cloud_rows, 0)
    if local_rows > 0:
        row_pct = row_diff / local_rows * 100
        if row_pct > 5 and row_diff > 500:
            score -= 25
            causes.append(f"Cloud is missing about {row_diff:,} rows from the monitored table.")
            fixes.append("Check SQL thread errors, duplicate-key skips, and whether the correct check table is configured.")
        elif row_pct > 1 and row_diff > 100:
            score -= 10
            causes.append(f"Cloud row count is behind local by {row_diff:,} rows.")
            fixes.append("Allow replication to catch up, then re-check. If not improving, inspect SQL/IO errors.")

    ll = _dt(latest_local)
    lc = _dt(latest_cloud)
    if ll and lc and ll > lc:
        minutes = (ll - lc).total_seconds() / 60
        if minutes > 60:
            score -= 20
            causes.append(f"Cloud latest update is {minutes:.0f} minutes behind local latest update.")
            fixes.append("Start with SQL/IO thread status, then check network/VPN and replication lag.")
        elif minutes > 15:
            score -= 10
            causes.append(f"Cloud latest update is {minutes:.0f} minutes behind local.")
            fixes.append("Watch the next heartbeat; if delay grows, open First Aid actions.")

    score = max(0, min(100, score))
    if score >= 90:
        status = "healthy"
    elif score >= 70:
        status = "minor_drift"
    elif score >= 40:
        status = "major_drift"
    else:
        status = "critical_drift"

    if not causes:
        causes.append("Local and cloud database indicators are aligned within safe thresholds.")
        fixes.append("No action needed. Continue normal monitoring.")
    return score, status, " ".join(causes), " ".join(fixes)


def record_integrity_check(db: Session, *, center_id: str, center_name: str, foss_id: str, database_name: str,
                           local_size_mb: float, local_rows_count: int, local_table_count: int,
                           local_latest_time: Any, local_table_summary_json: Any = None) -> Dict[str, Any]:
    check_table = os.getenv("CHECK_TABLE_NAME", "address")
    check_time_column = os.getenv("CHECK_TIME_COLUMN", "updated_at")
    cloud = get_cloud_database_stats(db, database_name, check_table, check_time_column)

    cloud_size_mb = _safe_float(cloud.get("cloud_size_mb"))
    cloud_rows_count = _safe_int(cloud.get("cloud_rows_count"))
    cloud_table_count = _safe_int(cloud.get("cloud_table_count"))
    latest_cloud_time = cloud.get("latest_cloud_time")

    rows_difference = int(local_rows_count or 0) - int(cloud_rows_count or 0)
    size_difference_mb = round(float(local_size_mb or 0) - float(cloud_size_mb or 0), 2)

    score, status, cause, fix = score_integrity(
        float(local_size_mb or 0), cloud_size_mb,
        int(local_rows_count or 0), cloud_rows_count,
        int(local_table_count or 0), cloud_table_count,
        local_latest_time, latest_cloud_time,
    )

    res = db.execute(text("""
        INSERT INTO database_integrity_checks
          (center_id, center_name, foss_id, database_name,
           local_size_mb, cloud_size_mb, size_difference_mb,
           local_rows_count, cloud_rows_count, rows_difference,
           local_table_count, cloud_table_count,
           latest_local_time, latest_cloud_time,
           data_health_score, integrity_status, probable_cause, recommended_fix, created_at)
        VALUES
          (:cid, :cn, :foss, :dbn,
           :lsize, :csize, :sdiff,
           :lrows, :crows, :rdiff,
           :ltables, :ctables,
           :llatest, :clatest,
           :score, :status, :cause, :fix, NOW())
    """), {
        "cid": center_id, "cn": center_name, "foss": foss_id, "dbn": database_name,
        "lsize": local_size_mb or 0, "csize": cloud_size_mb, "sdiff": size_difference_mb,
        "lrows": local_rows_count or 0, "crows": cloud_rows_count, "rdiff": rows_difference,
        "ltables": local_table_count or 0, "ctables": cloud_table_count,
        "llatest": _dt(local_latest_time), "clatest": _dt(latest_cloud_time),
        "score": score, "status": status, "cause": cause, "fix": fix,
    })

    check_id = getattr(res, "lastrowid", None)

    # Optional per-table summaries from agent. Best effort only.
    try:
        summary = local_table_summary_json
        if isinstance(summary, str):
            summary = json.loads(summary) if summary.strip() else []
        if isinstance(summary, list) and check_id:
            for item in summary[:25]:
                table = str(item.get("table") or item.get("name") or "")[:255]
                if not table:
                    continue
                local_table_rows = _safe_int(item.get("rows"))
                local_table_size = _safe_float(item.get("size_mb"))
                cloud_table_rows = 0
                cloud_table_size = 0.0
                if _table_exists(db, database_name, table):
                    try:
                        cloud_table_rows = _safe_int(db.execute(text(f"SELECT COUNT(*) FROM `{database_name}`.`{table}`")).scalar())
                    except Exception:
                        pass
                    try:
                        rr = db.execute(text("""
                          SELECT ROUND((data_length + index_length)/1024/1024,2) AS size_mb
                          FROM information_schema.tables
                          WHERE table_schema=:schema AND table_name=:table
                        """), {"schema": database_name, "table": table}).mappings().first()
                        cloud_table_size = _safe_float(rr["size_mb"] if rr else 0)
                    except Exception:
                        pass
                db.execute(text("""
                    INSERT INTO database_integrity_table_checks
                      (check_id, table_name, local_rows_count, cloud_rows_count, rows_difference, local_size_mb, cloud_size_mb)
                    VALUES (:check_id, :table, :lrows, :crows, :rdiff, :lsize, :csize)
                """), {"check_id": check_id, "table": table, "lrows": local_table_rows, "crows": cloud_table_rows,
                      "rdiff": local_table_rows - cloud_table_rows, "lsize": local_table_size, "csize": cloud_table_size})
    except Exception:
        pass

    db.execute(text("""
        UPDATE monitored_databases SET
          cloud_rows_count=:crows, cloud_size_mb=:csize,
          local_rows_count=:lrows, local_size_mb=:lsize,
          local_table_count=:ltables, cloud_table_count=:ctables,
          rows_difference=:rdiff, size_difference_mb=:sdiff,
          latest_local_time=:llatest, latest_cloud_time=:clatest,
          data_health_score=:score, integrity_status=:status,
          integrity_summary=:summary, drift_detected=:drift,
          last_integrity_check=NOW(), rows_count=:lrows, data_size_mb=:lsize, last_checked=NOW()
        WHERE health_center_id=:cid AND database_name=:dbn
    """), {"cid": center_id, "dbn": database_name, "crows": cloud_rows_count, "csize": cloud_size_mb,
          "lrows": local_rows_count or 0, "lsize": local_size_mb or 0, "ltables": local_table_count or 0, "ctables": cloud_table_count,
          "rdiff": rows_difference, "sdiff": size_difference_mb, "llatest": _dt(local_latest_time), "clatest": _dt(latest_cloud_time),
          "score": score, "status": status, "summary": f"{cause} Recommended fix: {fix}", "drift": 1 if score < 90 else 0})

    return {
        "data_health_score": score,
        "integrity_status": status,
        "local_size_mb": float(local_size_mb or 0),
        "cloud_size_mb": cloud_size_mb,
        "size_difference_mb": size_difference_mb,
        "local_rows_count": int(local_rows_count or 0),
        "cloud_rows_count": cloud_rows_count,
        "rows_difference": rows_difference,
        "local_table_count": int(local_table_count or 0),
        "cloud_table_count": cloud_table_count,
        "latest_local_time": str(local_latest_time) if local_latest_time else None,
        "latest_cloud_time": str(latest_cloud_time) if latest_cloud_time else None,
        "probable_cause": cause,
        "recommended_fix": fix,
    }
