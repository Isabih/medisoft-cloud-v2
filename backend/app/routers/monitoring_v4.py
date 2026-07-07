from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.services.monitoring_v4 import collect_once, registered_centers

router = APIRouter(prefix="/monitoring-v4", tags=["Monitoring v4"])


@router.get("/health")
def health():
    return {"ok": True, "service": "monitoring-v4"}


@router.post("/collect-now")
def collect_now():
    return collect_once()


@router.get("/registered-centers")
def get_registered_centers(db: Session = Depends(get_db)):
    return registered_centers(db)


@router.get("/center-complete/{foss_id}")
def center_complete(foss_id: str, db: Session = Depends(get_db)):
    hc = db.execute(text("SELECT * FROM health_centers WHERE foss_id=:f LIMIT 1"), {"f": foss_id}).mappings().first()
    local = db.execute(text("SELECT * FROM source_agent_reports WHERE foss_id=:f ORDER BY id DESC LIMIT 1"), {"f": foss_id}).mappings().first()
    source_rich = None
    try:
        source_rich = db.execute(text("SELECT * FROM source_reports WHERE foss_id=:f ORDER BY received_at DESC LIMIT 1"), {"f": foss_id}).mappings().first()
    except Exception:
        pass
    cloud = db.execute(text("SELECT * FROM cloud_replica_reports WHERE foss_id=:f ORDER BY COALESCE(collected_at, checked_at, created_at) DESC LIMIT 1"), {"f": foss_id}).mappings().first()
    integrity = db.execute(text("SELECT * FROM database_integrity_snapshots WHERE foss_id=:f ORDER BY checked_at DESC LIMIT 1"), {"f": foss_id}).mappings().first()
    return {
        "registered": dict(hc) if hc else None,
        "latest_local_payload": dict(local) if local else None,
        "latest_rich_source_payload": dict(source_rich) if source_rich else None,
        "latest_cloud_payload": dict(cloud) if cloud else None,
        "latest_integrity": dict(integrity) if integrity else None,
    }
