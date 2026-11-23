import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard-live-final-v4"])

def good(v):
    return str(v or "").strip().lower() in ("yes", "online", "ok", "running", "true", "1", "on")

def safe_json(v, default):
    try:
        if not v:
            return default
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return default

@router.get("/centers-live")
def centers_live(db: Session = Depends(get_db)):
    centers = db.execute(text("SELECT * FROM health_centers ORDER BY name")).mappings().all()
    rows = []
    # Cloud clock sampled once per request; agent timestamps are historical reports.
    clock_row = db.execute(text("SELECT UTC_TIMESTAMP() AS cloud_utc, NOW() AS cloud_local, @@session.time_zone AS mysql_timezone")).mappings().first()

    for hc in centers:
        hc = dict(hc)
        foss_id = str(hc.get("foss_id") or "")

        local = db.execute(text("""
            SELECT *,
                   TIMESTAMPDIFF(MINUTE, COALESCE(created_at, sent_at), NOW()) AS heartbeat_age_minutes
            FROM source_agent_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        cloud = db.execute(text("""
            SELECT *,
                   TIMESTAMPDIFF(MINUTE, COALESCE(created_at, checked_at, collected_at), NOW()) AS cloud_age_minutes
            FROM cloud_replica_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        # Dedicated incident metadata: never infer root cause from a red status card.
        try:
            incident = db.execute(text("""
                SELECT state, diagnosis_json, opened_at, last_checked, recovery_emailed_at
                FROM replication_io_incidents WHERE foss_id=:foss_id
            """), {"foss_id": foss_id}).mappings().first()
        except Exception:
            db.rollback()
            incident = None

        integ = db.execute(text("""
            SELECT *
            FROM database_integrity_snapshots
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        local = dict(local or {})
        cloud = dict(cloud or {})
        integ = dict(integ or {})

        heartbeat_age = local.get("heartbeat_age_minutes")
        heartbeat_ok = heartbeat_age is not None and int(heartbeat_age) <= 10

        cloud_age = cloud.get("cloud_age_minutes")
        cloud_fresh = cloud_age is not None and 0 <= int(cloud_age) <= 10
        mysql_ok = heartbeat_ok and good(local.get("mysql_status"))
        internet_ok = heartbeat_ok and good(local.get("internet_status"))
        # Cloud replica state is authoritative; never infer it from a source agent.
        io_ok = cloud_fresh and good(cloud.get("io_running"))
        sql_ok = cloud_fresh and good(cloud.get("sql_running"))
        io_state = ("Yes" if io_ok else "No") if cloud_fresh and cloud.get("io_running") is not None else "Unknown"
        sql_state = ("Yes" if sql_ok else "No") if cloud_fresh and cloud.get("sql_running") is not None else "Unknown"

        rows_count = int(local.get("local_rows_count") or integ.get("local_rows_count") or 0)
        table_count = int(local.get("local_table_count") or integ.get("local_table_count") or 0)

        db_size = float(
            local.get("database_size_mb")
            or local.get("local_size_mb")
            or integ.get("local_size_mb")
            or hc.get("data_size_mb")
            or 0
        )

        row_diff = int(integ.get("rows_difference") or 0)
        size_diff = float(integ.get("size_difference_mb") or 0)

        if rows_count > 0:
            db_health = max(0, min(100, round(100 - (abs(row_diff) / max(rows_count, 1) * 100), 1)))
        elif db_size > 0:
            db_health = 100
        else:
            db_health = 0

        drift_reason = "No drift detected"
        if row_diff != 0:
            drift_reason = f"Row difference detected: {row_diff} rows"
        elif abs(size_diff) > 5:
            drift_reason = f"Database size difference detected: {size_diff} MB"
        elif db_health < 100:
            drift_reason = "Database integrity mismatch detected"

        replication_ok = io_ok and sql_ok
        online = heartbeat_ok and mysql_ok and internet_ok

        if online and replication_ok and cloud_fresh:
            status = "online"
            success_rate = 100
            risk_score = 0
            health_score = db_health if db_health > 0 else 100
        elif heartbeat_ok:
            status = "partial"
            success_rate = 70
            risk_score = 30
            health_score = 70
        else:
            status = "unreachable"
            success_rate = 0
            risk_score = 100
            health_score = 0

        last_seen = local.get("created_at") or local.get("sent_at") or hc.get("last_seen")

        # Schema inspection equivalent to SHOW COLUMNS/INDEX, using metadata only.
        # Never scan the entire database or assume an orders primary key.
        schema_name = hc.get("database_name")
        order_columns, order_indexes = [], []
        if schema_name:
            order_columns = [dict(x) for x in db.execute(text("""
                SELECT COLUMN_NAME AS name, DATA_TYPE AS type, IS_NULLABLE AS nullable,
                       COLUMN_KEY AS column_key
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=:schema AND TABLE_NAME='orders'
                ORDER BY ORDINAL_POSITION
            """), {"schema": schema_name}).mappings().all()]
            order_indexes = [dict(x) for x in db.execute(text("""
                SELECT INDEX_NAME AS name, COLUMN_NAME AS column_name,
                       SEQ_IN_INDEX AS position, NON_UNIQUE AS non_unique
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA=:schema AND TABLE_NAME='orders'
                ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """), {"schema": schema_name}).mappings().all()]
        # sent_at is reported by the local agent; it is NOT an independently
        # verified local server clock. Do not infer clock skew from it alone.
        agent_sent_at = local.get("sent_at")
        orders_diagnosis = {
            "schema_exists": bool(order_columns),
            "columns": order_columns,
            "indexes": order_indexes,
            "cloud_time_utc": str(clock_row["cloud_utc"]) if clock_row else None,
            "cloud_time_local": str(clock_row["cloud_local"]) if clock_row else None,
            "cloud_mysql_timezone": str(clock_row["mysql_timezone"]) if clock_row else None,
            "local_agent_reported_time": str(agent_sent_at) if agent_sent_at else None,
            "local_agent_received_at": str(local.get("received_at")) if local.get("received_at") else None,
            "local_clock_skew_seconds": None,
            "local_clock_status": "unverified",
            "orders_local_count": None,
            "orders_cloud_count": None,
            "orders_difference": None,
            "comparison_status": "awaiting_checkpointed_orders_metrics",
            "comparison_reason": "Local agent does not yet provide a verified orders-only count at a shared replication checkpoint.",
            "replication_lag_seconds": int(cloud["seconds_behind"]) if cloud_fresh and cloud.get("seconds_behind") is not None else None,
            "lag_reason": (
                "Cloud replica IO is not running; inspect IO diagnostics." if cloud_fresh and not io_ok else
                "Cloud replica SQL is not running; inspect Last_SQL_Error." if cloud_fresh and not sql_ok else
                "Replica reports delay, but source cause is not established." if cloud_fresh and cloud.get("seconds_behind") not in (None, 0) else
                "No current lag evidence." if cloud_fresh else
                "Cloud replica report is missing or stale; lag cannot be determined."
            ),
        }

        item = {
            "orders_diagnostics": orders_diagnosis,
            **hc,
            "foss_id": foss_id,
            "name": hc.get("name"),
            "health_center_name": hc.get("name"),
            "db_name": local.get("db_name") or hc.get("database_name"),
            "database_name": local.get("database_name") or local.get("db_name") or hc.get("database_name"),
            "channel_name": local.get("channel_name") or cloud.get("channel_name") or hc.get("replication_channel"),

            "status": status,
            "io_diagnostics": ({
                **{k: v for k, v in safe_json(incident["diagnosis_json"], {}).items() if k in ("io_state", "cause_code", "confidence", "reason", "suggested_solution", "checks", "mysql_error_number", "checked_at")},
                "incident_state": incident["state"],
                "incident_opened_at": str(incident["opened_at"]) if incident["opened_at"] else None,
                "recovery_emailed_at": str(incident["recovery_emailed_at"]) if incident["recovery_emailed_at"] else None,
            } if incident else None),
            "internet_status": ("online" if internet_ok else "offline") if heartbeat_ok and local.get("internet_status") is not None else "unknown",
            "mysql_status": ("online" if mysql_ok else "offline") if heartbeat_ok and local.get("mysql_status") is not None else "unknown",

            "backend_connection": "online" if heartbeat_ok else "failed",
            "cloud_connection": "online" if heartbeat_ok else "failed",
            "agent_connection": "online" if heartbeat_ok else "failed",
            "local_server_reachable": heartbeat_ok,

            "heartbeat": "ok" if heartbeat_ok else "down",
            "heartbeat_status": "ok" if heartbeat_ok else "down",
            "heartbeat_age": int(heartbeat_age) if heartbeat_age is not None else None,
            "heartbeat_age_minutes": int(heartbeat_age) if heartbeat_age is not None else None,

            "io_running": io_state,
            "sql_running": sql_state,
            "replica_io": io_state,
            "replica_sql": sql_state,
            "replication_status": ("ok" if replication_ok else "critical") if cloud_fresh else "unknown",
            "seconds_behind": int(cloud["seconds_behind"]) if cloud_fresh and cloud.get("seconds_behind") is not None else None,

            "last_io_error": cloud.get("last_io_error") or local.get("last_io_error") or "",
            "last_sql_error": cloud.get("last_sql_error") or local.get("last_sql_error") or "",

            "cpu_usage": float(local.get("cpu_usage") or hc.get("cpu_usage") or 0),
            "ram_usage": float(local.get("ram_usage") or hc.get("ram_usage") or 0),
            "disk_usage": float(local.get("disk_usage") or hc.get("disk_usage") or 0),

            "database_size_mb": db_size,
            "local_size_mb": db_size,
            "data_size_mb": db_size,

            "rows": rows_count,
            "rows_count": rows_count,
            "local_rows_count": rows_count,
            "local_table_count": table_count,

            "db_health": db_health,
            "db_health_score": db_health,
            "db_health_percent": db_health,
            "integrity_score": db_health,

            "rows_difference": row_diff,
            "size_difference_mb": size_diff,
            "drift_reason": drift_reason,
            "drift_summary": drift_reason,

            "orders_today": 0,
            "success_rate": success_rate,
            "risk_score": risk_score,
            "health_score": health_score,

            "cloud_report_fresh": cloud_fresh,
            "cloud_report_age_minutes": int(cloud_age) if cloud_age is not None else None,
            "last_seen": str(last_seen) if last_seen else None,
            "last_data_timestamp": str(last_seen) if last_seen else None,
            "last_updated": str(cloud.get("created_at") or cloud.get("checked_at") or last_seen) if (cloud.get("created_at") or cloud.get("checked_at") or last_seen) else None,

            "replication": {
                "io_running": io_state,
                "sql_running": sql_state,
                "seconds_behind": int(cloud["seconds_behind"]) if cloud_fresh and cloud.get("seconds_behind") is not None else None,
                "last_io_error": cloud.get("last_io_error") or "",
                "last_sql_error": cloud.get("last_sql_error") or "",
            },
        }

        rows.append(item)

    return rows
