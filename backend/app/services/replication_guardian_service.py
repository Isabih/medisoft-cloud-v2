import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.guardian import (
    LocalStatusReport,
    ReplicaEmergencyState,
    ReplicationGuardianEvent,
)
from app.routers.websocket import manager


UNKNOWN_DB_RE = re.compile(r"Unknown database '([^']+)'")
DROP_MISSING_RE = re.compile(r"Can't drop database '([^']+)'; database doesn't exist")


def _json_default(v: Any):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return str(v)


def serialize_row(row: Any) -> dict:
    return {k: _json_default(v) for k, v in dict(row).items()}


def get_channel_snapshot(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT
          c.CHANNEL_NAME AS channel_name,
          c.HOST AS source_host,
          c.PORT AS source_port,
          c.USER AS source_user,
          COALESCE(cs.SERVICE_STATE, 'OFF') AS io_state,
          COALESCE(ap.SERVICE_STATE, 'OFF') AS sql_state,
          COALESCE(cs.LAST_ERROR_NUMBER, 0) AS last_io_errno,
          COALESCE(cs.LAST_ERROR_MESSAGE, '') AS last_io_error,
          COALESCE(ap.LAST_ERROR_NUMBER, 0) AS last_sql_errno,
          COALESCE(ap.LAST_ERROR_MESSAGE, '') AS last_sql_error,
          hc.id AS center_id,
          hc.name AS center_name,
          hc.database_name,
          hc.foss_id,
          hc.province,
          hc.district
        FROM performance_schema.replication_connection_configuration c
        LEFT JOIN performance_schema.replication_connection_status cs USING (CHANNEL_NAME)
        LEFT JOIN performance_schema.replication_applier_status ap USING (CHANNEL_NAME)
        LEFT JOIN health_centers hc ON hc.replication_channel = c.CHANNEL_NAME
        ORDER BY c.CHANNEL_NAME
    """)).mappings().all()
    return [serialize_row(r) for r in rows]


def get_channel_worker_errors(db: Session, channel_name: str) -> list[str]:
    rows = db.execute(text("""
        SELECT LAST_ERROR_MESSAGE
        FROM performance_schema.replication_applier_status_by_worker
        WHERE CHANNEL_NAME = :channel_name
          AND LAST_ERROR_MESSAGE IS NOT NULL
          AND LAST_ERROR_MESSAGE <> ''
    """), {"channel_name": channel_name}).mappings().all()
    return [r["LAST_ERROR_MESSAGE"] for r in rows]


def classify_channel(snapshot: dict, worker_errors: list[str]) -> dict:
    io_on = str(snapshot.get("io_state", "")).upper() == "ON"
    sql_on = str(snapshot.get("sql_state", "")).upper() == "ON"
    last_io = snapshot.get("last_io_error", "") or ""
    last_sql = snapshot.get("last_sql_error", "") or ""

    if io_on and sql_on:
        return {"classification": "healthy", "severity": "info", "message": "Replication healthy"}

    for msg in worker_errors:
        m = UNKNOWN_DB_RE.search(msg)
        if m:
            return {
                "classification": "unknown_database",
                "severity": "critical",
                "message": msg,
                "database": m.group(1),
            }
        m = DROP_MISSING_RE.search(msg)
        if m:
            return {
                "classification": "drop_missing_database",
                "severity": "warning",
                "message": msg,
                "database": m.group(1),
            }

    if "Authentication requires secure connection" in last_io:
        return {"classification": "auth_secure_connection_required", "severity": "critical", "message": last_io}
    if "Can't connect to MySQL server" in last_io:
        return {"classification": "connectivity_failure", "severity": "critical", "message": last_io}
    if not io_on and sql_on:
        return {"classification": "io_not_running", "severity": "critical", "message": last_io or "Replica IO thread not running"}
    if io_on and not sql_on:
        return {"classification": "sql_not_running", "severity": "critical", "message": last_sql or "Replica SQL thread not running"}
    return {"classification": "degraded", "severity": "critical", "message": last_io or last_sql or "Replication degraded"}


async def broadcast_event(event: dict):
    try:
        await manager.broadcast(event)
    except Exception:
        pass


def upsert_alert(db: Session, snapshot: dict, classification: dict) -> None:
    channel_name = snapshot.get("channel_name")
    center_id = snapshot.get("center_id")
    center_name = snapshot.get("center_name") or channel_name

    active = db.query(Alert).filter(
        Alert.type == "replication_problem",
        Alert.center_id == center_id,
        Alert.resolved_at.is_(None),
    ).first()

    message = classification.get("message") or "Replication problem detected"
    severity = classification.get("severity", "critical")

    if active:
        active.message = message
        active.severity = severity
    else:
        db.add(Alert(
            center_id=center_id or channel_name,
            center_name=center_name,
            type="replication_problem",
            message=message,
            severity=severity,
        ))

    state = db.query(ReplicaEmergencyState).filter_by(channel_name=channel_name).first()
    if state:
        state.is_active = True
        state.message = message
        state.classification = classification.get("classification")
        state.resolved_at = None
        state.center_id = center_id
        state.center_name = center_name
    else:
        db.add(ReplicaEmergencyState(
            center_id=center_id,
            center_name=center_name,
            channel_name=channel_name,
            severity=severity,
            classification=classification.get("classification"),
            is_active=True,
            message=message,
        ))


def resolve_replication_alerts(db: Session, snapshot: dict) -> None:
    center_id = snapshot.get("center_id")
    channel_name = snapshot.get("channel_name")
    now = datetime.utcnow()
    for alert in db.query(Alert).filter(
        Alert.type == "replication_problem",
        Alert.center_id == center_id,
        Alert.resolved_at.is_(None),
    ).all():
        alert.resolved_at = now

    state = db.query(ReplicaEmergencyState).filter_by(channel_name=channel_name).first()
    if state and state.is_active:
        state.is_active = False
        state.resolved_at = now
        state.message = "Resolved automatically because replica is healthy"


def record_guardian_event(
    db: Session,
    snapshot: dict,
    event_type: str,
    status: str,
    classification: dict,
    action_taken: str | None = None,
    details: dict | None = None,
) -> ReplicationGuardianEvent:
    event = ReplicationGuardianEvent(
        center_id=snapshot.get("center_id"),
        center_name=snapshot.get("center_name"),
        channel_name=snapshot.get("channel_name"),
        source_host=snapshot.get("source_host"),
        event_type=event_type,
        classification=classification.get("classification"),
        status=status,
        message=classification.get("message"),
        action_taken=action_taken,
        details_json=json.dumps(details or {}, default=_json_default),
    )
    db.add(event)
    db.flush()
    return event


def _safe_db_name(channel_name: str, db_name: str) -> bool:
    return db_name == channel_name or db_name.startswith(f"{channel_name}_")


def repair_channel(db: Session, channel_name: str) -> dict:
    snapshots = get_channel_snapshot(db)
    snapshot = next((s for s in snapshots if s["channel_name"] == channel_name), None)
    if not snapshot:
        raise ValueError(f"Channel '{channel_name}' not found")

    worker_errors = get_channel_worker_errors(db, channel_name)
    classification = classify_channel(snapshot, worker_errors)
    action_taken = None

    if classification["classification"] == "healthy":
        record_guardian_event(db, snapshot, "manual_repair", "skipped", classification, "Already healthy")
        db.commit()
        return {"success": True, "message": "Channel already healthy", "channel_name": channel_name}

    try:
        if classification["classification"] == "unknown_database":
            missing_db = classification.get("database")
            if not missing_db or not _safe_db_name(channel_name, missing_db):
                raise ValueError("Unsafe database auto-create refused")
            db.execute(text(f"CREATE DATABASE IF NOT EXISTS `{missing_db}`"))
            db.execute(text("STOP REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            db.execute(text("START REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            action_taken = f"Created database {missing_db} and restarted channel"

        elif classification["classification"] == "drop_missing_database":
            db.execute(text("STOP REPLICA SQL_THREAD FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            db.execute(text("SET GLOBAL sql_replica_skip_counter = 1"))
            db.execute(text("START REPLICA SQL_THREAD FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            action_taken = "Skipped one failing SQL event and restarted SQL thread"

        else:
            db.execute(text("STOP REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            db.execute(text("START REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
            action_taken = "Restarted replica channel"

        record_guardian_event(db, snapshot, "manual_repair", "started", classification, action_taken)
        db.commit()
        return {"success": True, "message": action_taken, "channel_name": channel_name}

    except Exception as exc:
        record_guardian_event(db, snapshot, "manual_repair", "failed", classification, str(exc))
        db.commit()
        return {"success": False, "message": str(exc), "channel_name": channel_name}


def guardian_status_payload(db: Session) -> dict:
    snapshots = get_channel_snapshot(db)
    channels = []
    healthy = 0
    broken = 0
    active_emergencies = db.query(ReplicaEmergencyState).filter_by(is_active=True).count()

    for snap in snapshots:
        worker_errors = get_channel_worker_errors(db, snap["channel_name"])
        classification = classify_channel(snap, worker_errors)
        is_healthy = classification["classification"] == "healthy"
        healthy += 1 if is_healthy else 0
        broken += 0 if is_healthy else 1
        channels.append({
            **snap,
            "classification": classification["classification"],
            "last_error": classification["message"],
            "emergency": not is_healthy,
            "auto_heal_enabled": classification["classification"] in {
                "unknown_database",
                "drop_missing_database",
                "io_not_running",
                "sql_not_running",
                "degraded",
            },
        })

    auto_heals_today = db.execute(text("""
        SELECT COUNT(*) FROM replication_guardian_events
        WHERE DATE(created_at) = CURRENT_DATE
          AND event_type IN ('heal', 'manual_repair')
          AND status IN ('success', 'started')
    """)).scalar() or 0

    manual_repairs_today = db.execute(text("""
        SELECT COUNT(*) FROM replication_guardian_events
        WHERE DATE(created_at) = CURRENT_DATE
          AND event_type = 'manual_repair'
    """)).scalar() or 0

    return {
        "summary": {
            "total_channels": len(channels),
            "healthy_channels": healthy,
            "broken_channels": broken,
            "active_emergencies": active_emergencies,
            "auto_heals_today": auto_heals_today,
            "manual_repairs_today": manual_repairs_today,
        },
        "channels": channels,
    }


def guardian_events_payload(db: Session, limit: int = 100) -> list[dict]:
    events = db.query(ReplicationGuardianEvent).order_by(
        ReplicationGuardianEvent.created_at.desc()
    ).limit(limit).all()

    out = []
    for ev in events:
        out.append({
            "id": ev.id,
            "center_id": ev.center_id,
            "center_name": ev.center_name,
            "channel_name": ev.channel_name,
            "source_host": ev.source_host,
            "event_type": ev.event_type,
            "classification": ev.classification,
            "status": ev.status,
            "message": ev.message,
            "action_taken": ev.action_taken,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })
    return out


def save_local_status_report(db: Session, payload: dict) -> dict:
    center_name = (
        payload.get("health_center_name")
        or payload.get("center_name")
        or payload.get("hostname")
        or ""
    ).strip()

    center = None
    search_params = {
        "foss_id": (payload.get("foss_id") or "").strip(),
        "db_name": (payload.get("db_name") or "").strip(),
        "channel_name": (payload.get("channel_name") or "").strip(),
        "hostname": (payload.get("hostname") or "").strip(),
        "name": center_name,
    }

    if search_params["foss_id"]:
        center = db.execute(text("""
            SELECT id, name, database_name, last_data_timestamp, foss_id, replication_channel
            FROM health_centers
            WHERE foss_id = :foss_id
            LIMIT 1
        """), {"foss_id": search_params["foss_id"]}).mappings().first()

    if not center and search_params["db_name"]:
        center = db.execute(text("""
            SELECT id, name, database_name, last_data_timestamp, foss_id, replication_channel
            FROM health_centers
            WHERE LOWER(database_name) = LOWER(:db_name)
            LIMIT 1
        """), {"db_name": search_params["db_name"]}).mappings().first()

    if not center and search_params["channel_name"]:
        center = db.execute(text("""
            SELECT id, name, database_name, last_data_timestamp, foss_id, replication_channel
            FROM health_centers
            WHERE LOWER(replication_channel) = LOWER(:channel_name)
            LIMIT 1
        """), {"channel_name": search_params["channel_name"]}).mappings().first()

    if not center and search_params["name"]:
        center = db.execute(text("""
            SELECT id, name, database_name, last_data_timestamp, foss_id, replication_channel
            FROM health_centers
            WHERE LOWER(name) = LOWER(:name)
               OR LOWER(database_name) = LOWER(:name)
            LIMIT 1
        """), {"name": search_params["name"]}).mappings().first()

    if not center and not center_name and not search_params["db_name"] and not search_params["channel_name"] and not search_params["foss_id"]:
        raise ValueError("health_center_name, hostname, db_name, channel_name, or foss_id is required")

    center_id = center["id"] if center else None
    resolved_center_name = (
        center["name"] if center
        else (
            center_name
            or search_params["db_name"]
            or search_params["channel_name"]
            or search_params["foss_id"]
            or "Unknown Center"
        )
    )

    cloud_row_count = 0
    cloud_latest_time = None

    if center:
        metric = db.execute(text("""
            SELECT rows_count, last_checked
            FROM monitored_databases
            WHERE health_center_id = :center_id
            ORDER BY last_checked DESC
            LIMIT 1
        """), {"center_id": center_id}).mappings().first()

        if metric:
            cloud_row_count = int(metric.get("rows_count") or 0)
            cloud_latest_time = metric.get("last_checked")
        else:
            cloud_latest_time = center.get("last_data_timestamp")

    if isinstance(cloud_latest_time, str) and cloud_latest_time:
        try:
            cloud_latest_time = datetime.fromisoformat(
                cloud_latest_time.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except Exception:
            cloud_latest_time = None

    local_row_count = int(payload.get("local_row_count") or 0)

    local_latest_time = payload.get("local_latest_time")
    if isinstance(local_latest_time, str) and local_latest_time:
        try:
            local_latest_time = datetime.fromisoformat(
                local_latest_time.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except Exception:
            local_latest_time = None

    reported_at = payload.get("reported_at")
    if isinstance(reported_at, str) and reported_at:
        try:
            reported_at = datetime.fromisoformat(
                reported_at.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except Exception:
            reported_at = datetime.utcnow()
    else:
        reported_at = datetime.utcnow()

    compare_status = "unknown"
    comparison_message = "Insufficient data to compare local and cloud"
    freshness_minutes = None

    if local_latest_time and cloud_latest_time:
        try:
            freshness_minutes = int(
                abs((local_latest_time - cloud_latest_time).total_seconds()) // 60
            )
        except Exception:
            freshness_minutes = None

        if local_row_count == cloud_row_count and freshness_minutes is not None and freshness_minutes <= 5:
            compare_status = "up_to_date"
            comparison_message = "Cloud data is up to date"
        elif local_row_count >= cloud_row_count:
            compare_status = "behind"
            comparison_message = "Cloud appears behind local data"
        else:
            compare_status = "ahead"
            comparison_message = "Cloud row count is ahead of local row count"

    elif local_row_count and cloud_row_count:
        compare_status = "up_to_date" if local_row_count == cloud_row_count else "behind"
        comparison_message = "Compared by row count only"

    report = LocalStatusReport(
        center_id=center_id,
        center_name=resolved_center_name,
        agent_status="online",
        internet_status=payload.get("internet_status") or "unknown",
        mysql_status=payload.get("mysql_status") or "unknown",
        backend_status=payload.get("backend_status") or payload.get("cloud_connection") or "unknown",
        cpu_usage=payload.get("cpu_usage") or 0,
        ram_usage=payload.get("ram_usage") or 0,
        storage_usage=payload.get("storage_usage") or payload.get("disk_usage") or 0,
        local_row_count=local_row_count,
        cloud_row_count=cloud_row_count,
        local_latest_time=local_latest_time,
        cloud_latest_time=cloud_latest_time,
        compare_status=compare_status,
        comparison_message=comparison_message,
        sync_freshness_minutes=freshness_minutes,
        reported_at=reported_at,
    )
    db.add(report)

    if center_id:
        db.execute(text("""
            UPDATE health_centers
            SET status = CASE WHEN :internet_status = 'online' AND :mysql_status = 'online' THEN 'online' ELSE status END,
                internet_status = :internet_status,
                mysql_status = :mysql_status,
                cloud_connection = :backend_status,
                cpu_usage = :cpu_usage,
                ram_usage = :ram_usage,
                disk_usage = :storage_usage,
                last_seen = :reported_at
            WHERE id = :center_id
        """), {
            "internet_status": payload.get("internet_status") or "unknown",
            "mysql_status": payload.get("mysql_status") or "unknown",
            "backend_status": payload.get("backend_status") or payload.get("cloud_connection") or "unknown",
            "cpu_usage": payload.get("cpu_usage") or 0,
            "ram_usage": payload.get("ram_usage") or 0,
            "storage_usage": payload.get("storage_usage") or payload.get("disk_usage") or 0,
            "reported_at": reported_at,
            "center_id": center_id,
        })

    db.commit()
    return {
        "success": True,
        "center_id": center_id,
        "center_name": resolved_center_name,
        "compare_status": compare_status,
        "comparison_message": comparison_message,
        "reported_at": reported_at.isoformat(),
    }


def local_status_payload(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT
            l.center_id AS health_center_id,
            l.center_name AS health_center_name,
            l.agent_status,
            l.internet_status,
            l.mysql_status,
            l.storage_usage,
            l.cpu_usage,
            l.ram_usage,
            l.local_latest_time,
            l.cloud_latest_time,
            l.local_row_count,
            l.cloud_row_count,
            l.compare_status,
            l.comparison_message,
            l.sync_freshness_minutes,
            l.reported_at
        FROM local_status_reports l
        JOIN (
            SELECT COALESCE(center_id, center_name) AS grp, MAX(reported_at) AS max_reported_at
            FROM local_status_reports
            GROUP BY COALESCE(center_id, center_name)
        ) latest
          ON COALESCE(l.center_id, l.center_name) = latest.grp
         AND l.reported_at = latest.max_reported_at
        ORDER BY l.center_name
    """)).mappings().all()
    return [serialize_row(r) for r in rows]