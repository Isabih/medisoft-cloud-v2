import json
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

        mysql_ok = good(local.get("mysql_status") or hc.get("mysql_status"))
        internet_ok = good(local.get("internet_status") or hc.get("internet_status"))
        io_ok = good(cloud.get("io_running") or local.get("io_running"))
        sql_ok = good(cloud.get("sql_running") or local.get("sql_running"))

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

        if online and replication_ok:
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
            status = "offline"
            success_rate = 0
            risk_score = 100
            health_score = 0

        last_seen = local.get("created_at") or local.get("sent_at") or hc.get("last_seen")

        item = {
            **hc,
            "foss_id": foss_id,
            "name": hc.get("name"),
            "health_center_name": hc.get("name"),
            "db_name": local.get("db_name") or hc.get("database_name"),
            "database_name": local.get("database_name") or local.get("db_name") or hc.get("database_name"),
            "channel_name": local.get("channel_name") or cloud.get("channel_name") or hc.get("replication_channel"),

            "status": status,
            "internet_status": "online" if internet_ok else "offline",
            "mysql_status": "online" if mysql_ok else "offline",

            "backend_connection": "online" if heartbeat_ok else "failed",
            "cloud_connection": "online" if heartbeat_ok else "failed",
            "agent_connection": "online" if heartbeat_ok else "failed",
            "local_server_reachable": heartbeat_ok,

            "heartbeat": "ok" if heartbeat_ok else "down",
            "heartbeat_status": "ok" if heartbeat_ok else "down",
            "heartbeat_age": int(heartbeat_age) if heartbeat_age is not None else None,
            "heartbeat_age_minutes": int(heartbeat_age) if heartbeat_age is not None else None,

            "io_running": "Yes" if io_ok else "No",
            "sql_running": "Yes" if sql_ok else "No",
            "replica_io": "Yes" if io_ok else "No",
            "replica_sql": "Yes" if sql_ok else "No",
            "replication_status": "ok" if replication_ok else "partial",
            "seconds_behind": int(cloud.get("seconds_behind") or local.get("seconds_behind") or 0),

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

            "last_seen": str(last_seen) if last_seen else None,
            "last_data_timestamp": str(last_seen) if last_seen else None,
            "last_updated": str(cloud.get("created_at") or cloud.get("checked_at") or last_seen) if (cloud.get("created_at") or cloud.get("checked_at") or last_seen) else None,

            "replication": {
                "io_running": "Yes" if io_ok else "No",
                "sql_running": "Yes" if sql_ok else "No",
                "seconds_behind": int(cloud.get("seconds_behind") or 0),
                "last_io_error": cloud.get("last_io_error") or "",
                "last_sql_error": cloud.get("last_sql_error") or "",
            },
        }

        rows.append(item)

    return rows
