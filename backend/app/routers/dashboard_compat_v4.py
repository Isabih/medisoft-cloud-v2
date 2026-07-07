from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard-compat-v4"])

@router.get("/center-complete/{foss_id}")
def center_complete(foss_id: str, db: Session = Depends(get_db)):
    center = db.execute(text("""
        SELECT *
        FROM health_centers
        WHERE foss_id = :foss_id
        LIMIT 1
    """), {"foss_id": foss_id}).mappings().first()

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

    return {
        "registered": dict(center) if center else None,
        "latest_local_payload": dict(local) if local else None,
        "latest_cloud_payload": dict(cloud) if cloud else None,
        "latest_integrity": dict(integrity) if integrity else None,
    }
