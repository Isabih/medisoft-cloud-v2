from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/monitored-databases", tags=["monitored-databases"])


@router.get("")
def list_monitored_databases(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
            md.id,
            md.health_center_id,
            hc.name AS health_center_name,
            md.database_name,
            md.replica_status,
            md.rows_count,
            md.data_size_mb,
            md.last_checked,
            md.last_backup,
            md.drift_detected,
            md.backup_status
        FROM monitored_databases md
        LEFT JOIN health_centers hc ON hc.id = md.health_center_id
        ORDER BY md.database_name
    """)).mappings().all()

    return [dict(r) for r in rows]


@router.get("/{db_id}")
def get_monitored_database(db_id: str, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM monitored_databases WHERE id = :id"),
        {"id": db_id}
    ).mappings().first()

    return dict(row) if row else {}