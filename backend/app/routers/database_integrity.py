"""Database Integrity API - v1.1."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/database-integrity", tags=["database-integrity"])


@router.get("/summary")
def integrity_summary(db: Session = Depends(get_db)):
    total = int(db.execute(text("SELECT COUNT(*) FROM monitored_databases")).scalar() or 0)
    rows = db.execute(text("""
        SELECT integrity_status, COUNT(*) c
        FROM monitored_databases
        GROUP BY integrity_status
    """)).mappings().all()
    by_status = {r["integrity_status"] or "unknown": int(r["c"] or 0) for r in rows}
    avg_score = float(db.execute(text("SELECT COALESCE(AVG(data_health_score),0) FROM monitored_databases")).scalar() or 0)
    drifting = int(db.execute(text("SELECT COUNT(*) FROM monitored_databases WHERE COALESCE(drift_detected,0)=1 OR COALESCE(data_health_score,100)<90")).scalar() or 0)
    latest = db.execute(text("""
        SELECT md.*, hc.name AS health_center_name, hc.foss_id
        FROM monitored_databases md
        LEFT JOIN health_centers hc ON hc.id=md.health_center_id
        ORDER BY md.last_integrity_check DESC
        LIMIT 20
    """)).mappings().all()
    return {
        "total_databases": total,
        "healthy": by_status.get("healthy", 0),
        "minor_drift": by_status.get("minor_drift", 0),
        "major_drift": by_status.get("major_drift", 0),
        "critical_drift": by_status.get("critical_drift", 0),
        "unknown": by_status.get("unknown", 0),
        "drifting": drifting,
        "average_data_health_score": round(avg_score, 1),
        "latest": [dict(r) for r in latest],
    }


@router.get("/centers/{center_id}")
def integrity_by_center(center_id: str, db: Session = Depends(get_db)):
    current = db.execute(text("""
        SELECT md.*, hc.name AS health_center_name, hc.foss_id
        FROM monitored_databases md
        LEFT JOIN health_centers hc ON hc.id=md.health_center_id
        WHERE md.health_center_id=:cid
        ORDER BY md.last_integrity_check DESC
    """), {"cid": center_id}).mappings().all()
    history = db.execute(text("""
        SELECT * FROM database_integrity_checks
        WHERE center_id=:cid
        ORDER BY created_at DESC
        LIMIT 100
    """), {"cid": center_id}).mappings().all()
    return {"current": [dict(r) for r in current], "history": [dict(r) for r in history]}


@router.get("/latest")
def latest_integrity_checks(limit: int = 100, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    rows = db.execute(text(f"""
        SELECT * FROM database_integrity_checks
        ORDER BY created_at DESC
        LIMIT {limit}
    """)).mappings().all()
    return [dict(r) for r in rows]
