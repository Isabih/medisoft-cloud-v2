import pymysql

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/databases", tags=["databases"])

SYSTEM_DATABASES = {
    "mysql",
    "information_schema",
    "performance_schema",
    "sys",
    "central_monitoring",
}


def best_schema_for_channel(channel: str, schemas: list[str]) -> tuple[str, int]:
    if not channel:
        return "", 0
    candidates = [s for s in schemas if s == channel or s == channel + "_new"]
    return (candidates[0], 100) if len(candidates) == 1 else ("", 0)


@router.get("/channels")
def replication_channels(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT c.CHANNEL_NAME AS replication_channel,
               c.HOST AS source_host, c.PORT AS source_port,
               cs.SERVICE_STATE AS io_thread,
               ap.SERVICE_STATE AS sql_thread,
               cs.LAST_ERROR_NUMBER AS io_error_number,
               COALESCE(w.LAST_ERROR_NUMBER, 0) AS sql_error_number
        FROM performance_schema.replication_connection_configuration c
        LEFT JOIN performance_schema.replication_connection_status cs USING (CHANNEL_NAME)
        LEFT JOIN performance_schema.replication_applier_status ap USING (CHANNEL_NAME)
        LEFT JOIN (
            SELECT CHANNEL_NAME, LAST_ERROR_NUMBER,
                   ROW_NUMBER() OVER (
                       PARTITION BY CHANNEL_NAME
                       ORDER BY LAST_ERROR_TIMESTAMP DESC, WORKER_ID
                   ) AS rn
            FROM performance_schema.replication_applier_status_by_worker
            WHERE LAST_ERROR_NUMBER <> 0
        ) w ON w.CHANNEL_NAME = c.CHANNEL_NAME AND w.rn = 1
        ORDER BY c.CHANNEL_NAME
    """)).mappings().all()
    return [dict(row) for row in rows]


def read_address_prefill(database_name: str) -> dict:
    result = {
        "health_center_name": "",
        "province": "",
        "district": "",
        "foss_id": "",
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
                SELECT province, district, hc, fosaid
                FROM address
                ORDER BY address_id ASC
                LIMIT 1
            """)
            row = cur.fetchone()

        conn.close()

        if row:
            result["health_center_name"] = row.get("hc") or ""
            result["province"] = row.get("province") or ""
            result["district"] = row.get("district") or ""
            result["foss_id"] = str(row.get("fosaid")) if row.get("fosaid") is not None else ""

    except Exception:
        pass

    return result


@router.get("/available")
def available_databases(db: Session = Depends(get_db)):
    channel_rows = db.execute(text("""
        SELECT
            c.CHANNEL_NAME AS replication_channel,
            c.HOST AS source_host,
            c.PORT AS source_port,
            cs.SERVICE_STATE AS io_thread,
            ap.SERVICE_STATE AS sql_thread
        FROM performance_schema.replication_connection_configuration c
        LEFT JOIN performance_schema.replication_connection_status cs USING (CHANNEL_NAME)
        LEFT JOIN performance_schema.replication_applier_status ap USING (CHANNEL_NAME)
        ORDER BY c.CHANNEL_NAME
    """)).mappings().all()

    schema_rows = db.execute(text("""
        SELECT schema_name AS schema_name
        FROM information_schema.schemata
        ORDER BY schema_name
    """)).mappings().all()

    all_schemas = [
        row["schema_name"]
        for row in schema_rows
        if row.get("schema_name") and row["schema_name"].lower() not in SYSTEM_DATABASES
    ]

    registered_rows = db.execute(text("""
        SELECT database_name
        FROM health_centers
    """)).mappings().all()

    registered = {
        (row.get("database_name") or "").strip().lower()
        for row in registered_rows
        if row.get("database_name")
    }

    results = []
    used_schemas = set()

    for row in channel_rows:
        channel = row.get("replication_channel") or ""
        source_host = row.get("source_host") or ""
        source_port = row.get("source_port") or 3306
        io_thread = row.get("io_thread") or "UNKNOWN"
        sql_thread = row.get("sql_thread") or "UNKNOWN"

        matched_schema, score = best_schema_for_channel(channel, all_schemas)

        if not matched_schema:
            matched_schema = f"{channel}_new"
            score = 0

        if matched_schema.lower() in registered:
            continue

        if matched_schema.lower() in used_schemas:
            continue

        used_schemas.add(matched_schema.lower())

        address_info = {}  # Facility identity requires separate authorized verification.

        results.append({
            "schema_name": matched_schema,
            "health_center_name": address_info.get("health_center_name", ""),
            "province": address_info.get("province", ""),
            "district": address_info.get("district", ""),
            "foss_id": address_info.get("foss_id", ""),
            "replication_channel": channel,
            "source_host": source_host,
            "source_port": source_port,
            "io_thread": io_thread,
            "sql_thread": sql_thread,
            "schema_visible": score > 0,
            "match_score": score,
            "match_type": (
                "exact" if score >= 90
                else "strong" if score >= 70
                else "partial" if score >= 60
                else "fallback"
            ),
        })

    unmatched_local_schemas = [
        schema for schema in all_schemas
        if schema.lower() not in used_schemas and schema.lower() not in registered
    ]

    for schema in unmatched_local_schemas:
        address_info = {}

        results.append({
            "schema_name": schema,
            "health_center_name": address_info.get("health_center_name", ""),
            "province": address_info.get("province", ""),
            "district": address_info.get("district", ""),
            "foss_id": address_info.get("foss_id", ""),
            "replication_channel": "",
            "source_host": "",
            "source_port": 3306,
            "io_thread": "UNKNOWN",
            "sql_thread": "UNKNOWN",
            "match_score": 0,
            "match_type": "local-only",
        })

    results.sort(key=lambda x: (-x["match_score"], x["schema_name"].lower()))
    return results
