from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.retention_service import (
    ensure_retention_schema,
    get_retention_settings,
    purge_old_monitoring_data,
)

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/status")
def retention_status(db: Session = Depends(get_db)):
    ensure_retention_schema(db)
    detailed_days, incident_days, enabled = get_retention_settings(db)
    latest = db.execute(text("""
        SELECT id, started_at, finished_at, detailed_retention_days, incident_retention_days,
               incidents_upserted, rows_deleted, status, message
        FROM retention_runs
        ORDER BY started_at DESC
        LIMIT 1
    """)).mappings().first()

    counts = {}
    for table in [
        "source_agent_reports", "cloud_replica_reports", "local_status_reports",
        "hybrid_diagnoses", "heartbeat_logs", "database_metrics", "incident_history"
    ]:
        try:
            counts[table] = int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
        except Exception:
            counts[table] = None

    return {
        "enabled": enabled,
        "detailed_retention_days": detailed_days,
        "incident_history_retention_days": incident_days,
        "latest_run": dict(latest) if latest else None,
        "table_counts": counts,
        "policy": "Detailed monitoring data is deleted after the configured window. Compact incident_history remains for long-term reports.",
    }


@router.post("/run")
def run_retention(force: bool = Query(True)):
    return purge_old_monitoring_data(force=force)
