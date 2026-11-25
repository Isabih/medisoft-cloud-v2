import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/databases", tags=["databases"])

SYSTEM_DATABASES = {
    "mysql",
    "information_schema",
    "performance_schema",
    "sys",
    "central_monitoring",
    "hearts360_v2",
    "medisoft_demo",
    "medisoft_monitoring",
}


def best_schema_for_channel(channel: str, schemas: list[str]) -> tuple[str, int]:
    if not channel:
        return "", 0
    candidates = [s for s in schemas if s == channel]
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


def read_address_prefill(db: Session, schema: str) -> dict:
    result = dict(health_center_name="", province="", district="", foss_id="")
    # Only called for schema names returned by the connected server.
    quoted = "`" + schema.replace("`", "``") + "`"
    try:
        columns = set(db.execute(text("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'address'
        """), {"schema": schema}).scalars())
        if not {"address_id", "district", "hc", "fosaid"} <= columns:
            result["prefill_status"] = "unavailable"
            return result
        province_expr = "`province`" if "province" in columns else "NULL"
        row = db.execute(text(f"""
            SELECT {province_expr} AS province, district, hc, fosaid
            FROM {quoted}.address
            ORDER BY address_id ASC LIMIT 1
        """)).mappings().first()
        if row:
            for key, column in (("health_center_name", "hc"), ("province", "province"),
                                ("district", "district"), ("foss_id", "fosaid")):
                result[key] = str(row[column]) if row[column] is not None else ""
        result["prefill_status"] = ("available" if "province" in columns else "partial") if row else "empty"
    except Exception as exc:
        logger.warning("Address prefill unavailable for %s (%s)", schema, type(exc).__name__)
        result["prefill_status"] = "unavailable"
    return result


@router.get("/available")
def available_databases(db: Session = Depends(get_db)):
    channels = replication_channels(db)
    schemas = [name for name in db.execute(text("""
        SELECT SCHEMA_NAME FROM information_schema.SCHEMATA ORDER BY SCHEMA_NAME
    """)).scalars() if name.lower() not in SYSTEM_DATABASES]
    registered = set(db.execute(text("""
        SELECT database_name FROM health_centers
        UNION SELECT database_name FROM monitored_databases
    """)).scalars())
    registered_channels = set(db.execute(text("""
        SELECT replication_channel FROM health_centers
        WHERE replication_channel IS NOT NULL
    """)).scalars())
    matches = {}
    for row in channels:
        channel = row["replication_channel"]
        schema, score = best_schema_for_channel(channel, schemas)
        if schema and channel not in registered_channels:
            matches.setdefault(schema, []).append(row)
    results = []
    for schema in schemas:
        if schema in registered or schema in registered_channels:
            continue
        candidates = matches.get(schema, [])
        row = candidates[0] if len(candidates) == 1 else {}
        results.append({
            "schema_name": schema,
            **read_address_prefill(db, schema),
            "replication_channel": row.get("replication_channel", ""),
            "source_host": row.get("source_host", ""),
            "source_port": row.get("source_port") or 3306,
            "io_thread": row.get("io_thread") or "UNKNOWN",
            "sql_thread": row.get("sql_thread") or "UNKNOWN",
            "schema_visible": True,
            "match_score": 100 if row else 0,
            "match_type": "exact" if row else "local-only",
        })
    return sorted(results, key=lambda r: (-r["match_score"], r["schema_name"]))
