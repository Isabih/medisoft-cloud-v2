import re
import uuid
import pymysql

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/health-centers", tags=["health-centers"])


class ValidateDbRequest(BaseModel):
    database_name: str


class RegisterHealthCenterRequest(BaseModel):
    name: str
    province: str
    district: str
    database_name: str
    foss_id: str
    replication_channel: str | None = None
    source_host: str | None = None
    source_port: int | None = 3306
    expected_sync_interval: int | None = 15
    anydesk_id: str | None = None
    rustdesk_id: str | None = None
    phone_number_1: str | None = None
    phone_contact_1: str | None = None
    phone_role_1: str | None = None   # e.g. Titulaire | Comptable | ...
    phone_number_2: str | None = None
    phone_contact_2: str | None = None
    phone_role_2: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    selected_database_schema: str | None = None


def normalize_name(value: str) -> str:
    value = (value or "").strip().lower()

    patterns = [
        r"_new\d*$",
        r"_\d+$",
        r"_cit$",
        r"_sake_\d+$",
    ]

    changed = True
    while changed:
        changed = False
        for pattern in patterns:
            new_value = re.sub(pattern, "", value)
            if new_value != value:
                value = new_value
                changed = True

    return value.strip("_").strip()


def channel_match_score(database_name: str, channel_name: str) -> int:
    db_raw = (database_name or "").strip().lower()
    ch_raw = (channel_name or "").strip().lower()

    db_norm = normalize_name(db_raw)
    ch_norm = normalize_name(ch_raw)

    if db_raw == ch_raw:
        return 100

    if db_norm == ch_norm:
        return 90

    if db_raw.startswith(ch_raw + "_"):
        return 80

    if db_norm.startswith(ch_norm):
        return 70

    if ch_norm and ch_norm in db_norm:
        return 60

    return 0


def normalize_status(value: str | None) -> str:
    value = (value or "").strip().upper()
    if value in {"YES", "ON", "RUNNING"}:
        return "ON"
    if value in {"NO", "OFF", "STOPPED"}:
        return "OFF"
    return "UNKNOWN"


def build_match_info(database_name: str, health_center_name: str, channel_name: str) -> dict:
    score = channel_match_score(database_name, channel_name)

    db_norm = normalize_name(database_name or "")
    hc_norm = normalize_name(health_center_name or "")
    ch_norm = normalize_name(channel_name or "")

    if score >= 100:
        return {
            "match_score": 100,
            "match_type": "exact",
            "match_reason": "Database name matches replication channel exactly.",
        }

    if score >= 90:
        return {
            "match_score": 90,
            "match_type": "strong",
            "match_reason": "Database and channel match strongly, but one side contains a naming variation such as suffix or formatting difference.",
        }

    if score >= 80:
        return {
            "match_score": 80,
            "match_type": "possible",
            "match_reason": "Database and channel are related, but not exact. Review carefully before registration.",
        }

    if hc_norm and (db_norm == hc_norm or hc_norm in db_norm or db_norm in hc_norm):
        return {
            "match_score": 90,
            "match_type": "strong_name",
            "match_reason": "Health center name looks very close to the database name, but replication channel does not match strongly.",
        }

    if ch_norm and hc_norm and (ch_norm == hc_norm or hc_norm in ch_norm or ch_norm in hc_norm):
        return {
            "match_score": 80,
            "match_type": "name_channel_possible",
            "match_reason": "Health center name and replication channel look related, but the database name is not a strong exact match.",
        }

    return {
        "match_score": score,
        "match_type": "weak",
        "match_reason": "Mapping is weak. Database, channel, or health center naming does not match clearly.",
    }


def detect_wrong_mapping(database_name: str, replication_channel: str, health_center_name: str) -> tuple[bool, str]:
    match = build_match_info(database_name, health_center_name, replication_channel)
    score = match["match_score"]

    if score < 80:
        return True, "Wrong mapping suspected: database name does not match replication channel strongly enough."

    return False, ""


def fetch_replication_config(db: Session, database_name: str, health_center_name: str = "") -> dict:
    rows = db.execute(
        text("""
            SELECT
                c.CHANNEL_NAME AS replication_channel,
                c.HOST AS source_host,
                c.PORT AS source_port,
                cs.SERVICE_STATE AS io_thread,
                ap.SERVICE_STATE AS sql_thread
            FROM performance_schema.replication_connection_configuration c
            LEFT JOIN performance_schema.replication_connection_status cs USING (CHANNEL_NAME)
            LEFT JOIN performance_schema.replication_applier_status ap USING (CHANNEL_NAME)
        """)
    ).mappings().all()

    best = None
    best_score = 0

    for row in rows:
        score = channel_match_score(database_name, row.get("replication_channel") or "")
        if score > best_score:
            best = row
            best_score = score

    if best:
        match_info = build_match_info(
            database_name=database_name,
            health_center_name=health_center_name,
            channel_name=best.get("replication_channel") or "",
        )

        io_thread = normalize_status(best.get("io_thread"))
        sql_thread = normalize_status(best.get("sql_thread"))

        replication_warning = ""
        if io_thread != "ON" or sql_thread != "ON":
            replication_warning = "⚠️ replication broken"

        wrong_mapping, wrong_mapping_reason = detect_wrong_mapping(
            database_name=database_name,
            replication_channel=best.get("replication_channel") or "",
            health_center_name=health_center_name,
        )

        return {
            "replication_channel": best.get("replication_channel") or "",
            "source_host": best.get("source_host") or "",
            "source_port": best.get("source_port") or 3306,
            "io_thread": io_thread,
            "sql_thread": sql_thread,
            "match_score": match_info["match_score"],
            "match_type": match_info["match_type"],
            "match_reason": match_info["match_reason"],
            "wrong_mapping": wrong_mapping,
            "wrong_mapping_reason": wrong_mapping_reason,
            "replication_warning": replication_warning,
        }

    return {
        "replication_channel": "",
        "source_host": "",
        "source_port": 3306,
        "io_thread": "UNKNOWN",
        "sql_thread": "UNKNOWN",
        "match_score": 0,
        "match_type": "weak",
        "match_reason": "No replication channel was matched to this database.",
        "wrong_mapping": True,
        "wrong_mapping_reason": "No matching replication channel was found.",
        "replication_warning": "⚠️ replication broken",
    }


@router.get("")
def list_health_centers(db: Session = Depends(get_db)):
    """Return registered health centers merged with the latest live Monitoring v4 data.

    This keeps the old /health-centers endpoint compatible with the frontend while
    using the same live source of truth as /dashboard/centers-live.
    """
    centers = db.execute(text("""
        SELECT
            hc.id,
            hc.name,
            hc.province,
            hc.district,
            hc.database_name,
            hc.foss_id,
            hc.replication_channel,
            hc.source_host,
            hc.source_port,
            hc.status,
            hc.internet_status,
            hc.mysql_status,
            hc.cloud_connection,
            hc.last_seen,
            hc.last_data_timestamp,
            hc.data_size_mb,
            hc.risk_score,
            hc.success_rate,
            hc.avg_rows_per_sync,
            hc.avg_data_size_mb,
            hc.cpu_usage,
            hc.ram_usage,
            hc.disk_usage,
            hc.anydesk_id,
            hc.rustdesk_id,
            hc.phone_number_1,
            hc.phone_contact_1,
            hc.phone_role_1,
            hc.phone_number_2,
            hc.phone_contact_2,
            hc.phone_role_2,
            hc.expected_sync_interval,
            hc.latitude,
            hc.longitude,
            hc.agent_version,
            hc.health_score,
            hc.created_at
        FROM health_centers hc
        ORDER BY hc.name
    """)).mappings().all()

    results = []

    for center in centers:
        c = dict(center)
        foss_id = c.get("foss_id")

        local = None
        cloud = None
        integrity = None

        if foss_id:
            local = db.execute(text("""
                SELECT *
                FROM source_agent_reports
                WHERE foss_id = :foss_id
                ORDER BY id DESC
                LIMIT 1
            """), {"foss_id": foss_id}).mappings().first()

            cloud = db.execute(text("""
                SELECT *
                FROM cloud_replica_reports
                WHERE foss_id = :foss_id
                ORDER BY id DESC
                LIMIT 1
            """), {"foss_id": foss_id}).mappings().first()

            integrity = db.execute(text("""
                SELECT *
                FROM database_integrity_snapshots
                WHERE foss_id = :foss_id
                ORDER BY id DESC
                LIMIT 1
            """), {"foss_id": foss_id}).mappings().first()

        local = dict(local) if local else {}
        cloud = dict(cloud) if cloud else {}
        integrity = dict(integrity) if integrity else {}

        # Prefer live agent values, then cloud/integrity values, then registered fallback.
        c["status"] = c.get("status") or "offline"
        c["internet_status"] = local.get("internet_status") or c.get("internet_status") or "offline"
        c["mysql_status"] = local.get("mysql_status") or c.get("mysql_status") or "offline"
        c["cloud_connection"] = local.get("cloud_connection") or c.get("cloud_connection") or "failed"

        live_seen = local.get("created_at") or local.get("sent_at")
        c["last_seen"] = live_seen or c.get("last_seen")
        c["last_sync"] = cloud.get("checked_at") or cloud.get("collected_at") or live_seen or c.get("last_seen")
        c["last_updated"] = c["last_sync"]
        c["agent_last_report"] = live_seen

        c["cpu_usage"] = local.get("cpu_usage", c.get("cpu_usage"))
        c["ram_usage"] = local.get("ram_usage", c.get("ram_usage"))
        c["disk_usage"] = local.get("disk_usage", c.get("disk_usage"))
        c["agent_version"] = local.get("agent_version") or c.get("agent_version")

        local_size = local.get("local_size_mb") or local.get("database_size_mb")
        cloud_size = cloud.get("cloud_database_size_mb")
        c["data_size_mb"] = local_size or cloud_size or c.get("data_size_mb")
        c["db_size_mb"] = c.get("data_size_mb")
        c["local_size_mb"] = local_size
        c["cloud_size_mb"] = cloud_size
        c["local_table_count"] = local.get("local_table_count")
        c["cloud_table_count"] = cloud.get("cloud_table_count")
        c["local_rows_count"] = local.get("local_rows_count")
        c["cloud_rows_count"] = cloud.get("cloud_rows_count")
        c["rows_difference"] = integrity.get("rows_difference")
        c["size_difference_mb"] = integrity.get("size_difference_mb")
        c["integrity_status"] = integrity.get("status")
        c["integrity_summary"] = integrity.get("summary")
        c["data_health_score"] = 70 if integrity.get("status") == "minor_drift" else (100 if integrity.get("status") in ("healthy", "ok", "synced") else None)

        c["head_of_hc"] = c.get("phone_contact_1") or "Head of HC"
        c["head_phone"] = c.get("phone_number_1")

        replica_io = cloud.get("io_running") or local.get("io_running")
        replica_sql = cloud.get("sql_running") or local.get("sql_running")
        seconds_behind = cloud.get("seconds_behind") if cloud.get("seconds_behind") is not None else local.get("seconds_behind")

        c["replica_io"] = replica_io
        c["replica_sql"] = replica_sql
        c["seconds_behind"] = seconds_behind
        c["replication_io_running"] = str(replica_io or "").lower() in {"yes", "on", "true", "1"}
        c["replication_sql_running"] = str(replica_sql or "").lower() in {"yes", "on", "true", "1"}
        c["replication_lag_seconds"] = seconds_behind
        c["replication"] = {
            "channel_name": cloud.get("channel_name") or local.get("channel_name") or c.get("replication_channel"),
            "source_host": cloud.get("source_host") or c.get("source_host"),
            "io_running": "Yes" if c["replication_io_running"] else (replica_io or "No"),
            "sql_running": "Yes" if c["replication_sql_running"] else (replica_sql or "No"),
            "seconds_behind": seconds_behind,
            "last_io_error": cloud.get("last_io_error") or local.get("last_io_error") or "",
            "last_sql_error": cloud.get("last_sql_error") or local.get("last_sql_error") or "",
            "checked_at": cloud.get("checked_at") or cloud.get("collected_at") or local.get("created_at"),
        }

        backup = db.execute(text("""
            SELECT status, backup_date, file_size_mb, duration_seconds, created_at
            FROM backups
            WHERE center_id = :center_id
            ORDER BY created_at DESC
            LIMIT 1
        """), {"center_id": c.get("id")}).mappings().first()
        backup = dict(backup) if backup else None
        c["last_backup"] = backup
        c["backup_status"] = backup.get("status") if backup else None

        unresolved = db.execute(text("""
            SELECT COUNT(*)
            FROM alerts
            WHERE center_id = :center_id AND resolved_at IS NULL
        """), {"center_id": c.get("id")}).scalar()
        c["unresolved_alerts"] = int(unresolved or 0)

        # Derive overall status from live checks.
        if c["mysql_status"] == "online" and c["internet_status"] == "online" and c["replication_io_running"] and c["replication_sql_running"]:
            c["status"] = "online"
            c["health_score"] = c.get("health_score") or 95
        elif c["mysql_status"] == "online" or c["internet_status"] == "online" or c["replication_io_running"] or c["replication_sql_running"]:
            c["status"] = "partial"
            c["health_score"] = c.get("health_score") or 70
        else:
            c["status"] = "offline"
            c["health_score"] = c.get("health_score") or 0

        results.append(c)

    return results


@router.get("/{center_id}")
def get_health_center(center_id: str, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM health_centers WHERE id = :id"),
        {"id": center_id}
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Health center not found")

    replication = db.execute(text("""
        SELECT channel_name, source_host, io_running, sql_running, seconds_behind,
               last_io_error, last_sql_error, checked_at
        FROM replication_status
        WHERE center_id = :id
        ORDER BY checked_at DESC
        LIMIT 1
    """), {"id": center_id}).mappings().first()

    comparison = db.execute(text("""
        SELECT compare_status AS status,
               local_latest_time,
               cloud_latest_time,
               local_row_count,
               cloud_row_count,
               comparison_message AS message,
               sync_freshness_minutes
        FROM local_status_reports
        WHERE center_id = :id
        ORDER BY reported_at DESC
        LIMIT 1
    """), {"id": center_id}).mappings().first()

    resources = {
        "cpu_usage": row.get("cpu_usage") or 0,
        "ram_usage": row.get("ram_usage") or 0,
        "disk_usage": row.get("disk_usage") or 0,
    }

    response = dict(row)
    response["replication"] = dict(replication) if replication else {
        "channel_name": row.get("replication_channel"),
        "source_host": row.get("source_host"),
        "io_running": False,
        "sql_running": False,
        "seconds_behind": None,
        "last_io_error": "",
        "last_sql_error": "",
        "guardian_status": "unknown",
        "emergency": False,
    }
    response["resources"] = resources
    response["comparison"] = dict(comparison) if comparison else {
        "status": "unknown",
        "local_latest_time": None,
        "cloud_latest_time": row.get("last_data_timestamp"),
        "local_row_count": 0,
        "cloud_row_count": 0,
        "message": "No local status reports yet",
    }
    return response


@router.post("/validate-db")
def validate_db(payload: ValidateDbRequest, db: Session = Depends(get_db)):
    database_name = payload.database_name.strip()

    if not database_name:
        raise HTTPException(status_code=400, detail="database_name is required")

    schema_exists = db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.schemata
            WHERE LOWER(schema_name) = LOWER(:schema_name)
        """),
        {"schema_name": database_name}
    ).scalar()

    if not schema_exists:
        return {
            "exists": False,
            "already_registered": False,
            "prefill": None
        }

    already_registered = db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM health_centers
            WHERE LOWER(database_name) = LOWER(:database_name)
        """),
        {"database_name": database_name}
    ).scalar()

    prefill = {
        "province": "",
        "district": "",
        "name": "",
        "foss_id": "",
        "phone_contact_1": "",
        "phone_contact_2": "",
        "replication_channel": "",
        "source_host": "",
        "source_port": 3306,
        "io_thread": "UNKNOWN",
        "sql_thread": "UNKNOWN",
        "match_score": 0,
        "match_type": "weak",
        "match_reason": "",
        "wrong_mapping": False,
        "wrong_mapping_reason": "",
        "replication_warning": "",
    }

    try:
        conn = pymysql.connect(
            host=settings.mysql_source_host,
            user=settings.mysql_source_user,
            password=settings.mysql_source_password,
            database=database_name,
            cursorclass=pymysql.cursors.DictCursor,
        )

        with conn.cursor() as cur:
            cur.execute("""
                SELECT province, district, hc, fosaid, titulaire, comptable
                FROM address
                ORDER BY address_id ASC
                LIMIT 1
            """)
            row = cur.fetchone()

        conn.close()

        if row:
            prefill["province"] = row.get("province") or ""
            prefill["district"] = row.get("district") or ""
            prefill["name"] = row.get("hc") or ""
            prefill["foss_id"] = str(row.get("fosaid")) if row.get("fosaid") is not None else ""
            prefill["phone_contact_1"] = row.get("titulaire") or ""
            prefill["phone_contact_2"] = row.get("comptable") or ""

    except Exception as e:
        prefill["warning"] = f"Could not read address table: {str(e)}"

    replication = fetch_replication_config(db, database_name, prefill.get("name") or "")
    prefill["replication_channel"] = replication.get("replication_channel") or ""
    prefill["source_host"] = replication.get("source_host") or ""
    prefill["source_port"] = replication.get("source_port") or 3306
    prefill["io_thread"] = replication.get("io_thread") or "UNKNOWN"
    prefill["sql_thread"] = replication.get("sql_thread") or "UNKNOWN"
    prefill["match_score"] = replication.get("match_score") or 0
    prefill["match_type"] = replication.get("match_type") or "weak"
    prefill["match_reason"] = replication.get("match_reason") or ""
    prefill["wrong_mapping"] = replication.get("wrong_mapping") or False
    prefill["wrong_mapping_reason"] = replication.get("wrong_mapping_reason") or ""
    prefill["replication_warning"] = replication.get("replication_warning") or ""

    return {
        "exists": True,
        "already_registered": bool(already_registered),
        "prefill": prefill,
        "match_score": prefill.get("match_score", 0),
        "match_type": prefill.get("match_type", "weak"),
        "match_reason": prefill.get("match_reason", ""),
        "wrong_mapping": prefill.get("wrong_mapping", False),
        "wrong_mapping_reason": prefill.get("wrong_mapping_reason", ""),
        "io_thread": prefill.get("io_thread", "UNKNOWN"),
        "sql_thread": prefill.get("sql_thread", "UNKNOWN"),
        "replication_warning": prefill.get("replication_warning", ""),
    }


@router.post("")
def register_health_center(payload: RegisterHealthCenterRequest, db: Session = Depends(get_db)):
    selected_schema = (payload.selected_database_schema or payload.database_name or "").strip()
    submitted_database = (payload.database_name or "").strip()

    if not submitted_database:
        raise HTTPException(status_code=400, detail="database_name is required")

    if selected_schema and selected_schema.lower() != submitted_database.lower():
        raise HTTPException(
            status_code=400,
            detail="Selected database mapping is inconsistent. Please re-select the database."
        )

    replication = fetch_replication_config(db, submitted_database, payload.name or "")

    if replication.get("wrong_mapping"):
        raise HTTPException(
            status_code=400,
            detail=replication.get("wrong_mapping_reason") or "Wrong mapping detected. Registration blocked."
        )

    if replication.get("sql_thread") != "ON":
        raise HTTPException(
            status_code=400,
            detail="Registration blocked because SQL replication is OFF."
        )

    center_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO health_centers (
                id, name, province, district, database_name, foss_id,
                replication_channel, source_host, source_port,
                expected_sync_interval, anydesk_id, rustdesk_id,
                phone_number_1, phone_contact_1, phone_role_1,
                phone_number_2, phone_contact_2, phone_role_2,
                latitude, longitude,
                status, internet_status, mysql_status, cloud_connection
            )
            VALUES (
                :id, :name, :province, :district, :database_name, :foss_id,
                :replication_channel, :source_host, :source_port,
                :expected_sync_interval, :anydesk_id, :rustdesk_id,
                :phone_number_1, :phone_contact_1, :phone_role_1,
                :phone_number_2, :phone_contact_2, :phone_role_2,
                :latitude, :longitude,
                'offline', 'offline', 'offline', 'failed'
            )
        """),
        {
            "id": center_id,
            "name": payload.name,
            "province": payload.province,
            "district": payload.district,
            "database_name": submitted_database,
            "foss_id": payload.foss_id,
            "replication_channel": replication.get("replication_channel") or payload.replication_channel,
            "source_host": replication.get("source_host") or payload.source_host,
            "source_port": replication.get("source_port") or payload.source_port,
            "expected_sync_interval": payload.expected_sync_interval,
            "anydesk_id": payload.anydesk_id,
            "rustdesk_id": payload.rustdesk_id,
            "phone_number_1": payload.phone_number_1,
            "phone_contact_1": payload.phone_contact_1,
            "phone_role_1": payload.phone_role_1,
            "phone_number_2": payload.phone_number_2,
            "phone_contact_2": payload.phone_contact_2,
            "phone_role_2": payload.phone_role_2,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
        }
    )

    db.execute(
        text("""
            INSERT INTO monitored_databases (
                id, health_center_id, database_name, replica_status
            )
            VALUES (
                :id, :health_center_id, :database_name, 'ok'
            )
        """),
        {
            "id": str(uuid.uuid4()),
            "health_center_id": center_id,
            "database_name": submitted_database,
        }
    )

    db.commit()

    return {
        "success": True,
        "id": center_id,
        "message": "Health center registered successfully"
    }


@router.get("/{center_id}/replication-history")
def replication_history(center_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT *
            FROM replication_status
            WHERE center_id = :center_id
            ORDER BY checked_at DESC
            LIMIT 100
        """),
        {"center_id": center_id}
    ).mappings().all()

    return [dict(r) for r in rows]


@router.get("/{center_id}/backup-history")
def backup_history(center_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT *
            FROM backups
            WHERE center_id = :center_id
            ORDER BY created_at DESC
            LIMIT 100
        """),
        {"center_id": center_id}
    ).mappings().all()

    return [dict(r) for r in rows]


@router.get("/{center_id}/metrics-history")
def metrics_history(center_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT *
            FROM database_metrics
            WHERE center_id = :center_id
            ORDER BY date DESC
            LIMIT 100
        """),
        {"center_id": center_id}
    ).mappings().all()

    return [dict(r) for r in rows]


@router.get("/{center_id}/timeline")
def timeline(center_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT id, type, message, severity, created_at AS timestamp
            FROM alerts
            WHERE center_id = :center_id
            ORDER BY created_at DESC
            LIMIT 100
        """),
        {"center_id": center_id}
    ).mappings().all()

    return [dict(r) for r in rows]


@router.get("/{center_id}/heartbeat-timeline")
def heartbeat_timeline(center_id: str, hours: int = 24, db: Session = Depends(get_db)):
    hours = max(1, min(hours, 168))
    hc = db.execute(
        text("SELECT id, foss_id, name FROM health_centers WHERE id = :id"),
        {"id": center_id},
    ).mappings().first()
    if not hc:
        raise HTTPException(404, "Health center not found")

    foss_id = hc["foss_id"]

    try:
        buckets = db.execute(
            text("""
                SELECT
                    DATE_FORMAT(received_at, '%Y-%m-%d %H:00:00') AS bucket,
                    COUNT(*) AS total,
                    SUM(CASE WHEN LOWER(COALESCE(io_running,'')) IN ('yes','on')
                              AND LOWER(COALESCE(sql_running,'')) IN ('yes','on')
                              AND LOWER(COALESCE(mysql_status,'online')) = 'online'
                             THEN 1 ELSE 0 END) AS success,
                    SUM(CASE WHEN (LOWER(COALESCE(io_running,'')) IN ('yes','on'))
                              <> (LOWER(COALESCE(sql_running,'')) IN ('yes','on'))
                             THEN 1 ELSE 0 END) AS partial,
                    SUM(CASE WHEN LOWER(COALESCE(io_running,'')) NOT IN ('yes','on')
                              AND LOWER(COALESCE(sql_running,'')) NOT IN ('yes','on')
                             THEN 1 ELSE 0 END) AS failure,
                    AVG(cpu_usage) AS avg_cpu,
                    AVG(ram_usage) AS avg_ram
                FROM source_reports
                WHERE foss_id = :fid
                  AND received_at >= DATE_SUB(NOW(), INTERVAL :hrs HOUR)
                GROUP BY bucket
                ORDER BY bucket
            """),
            {"fid": foss_id, "hrs": hours},
        ).mappings().all()
        buckets = [dict(r) for r in buckets]
    except Exception:
        buckets = []

    sms_markers = []
    try:
        rows = db.execute(
            text("""
                SELECT id, sent_at, status, recipient_role, to_number, message
                FROM sms_logs
                WHERE center_id = :cid
                  AND sent_at >= DATE_SUB(NOW(), INTERVAL :hrs HOUR)
                ORDER BY sent_at
            """),
            {"cid": center_id, "hrs": hours},
        ).mappings().all()
        sms_markers = [dict(r) for r in rows]
    except Exception:
        sms_markers = []

    return {
        "center_id": center_id,
        "foss_id": foss_id,
        "hours": hours,
        "buckets": buckets,
        "sms_markers": sms_markers,
    }
