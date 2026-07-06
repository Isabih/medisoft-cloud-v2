from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/active")
def active_alerts(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT *
        FROM alerts
        WHERE resolved_at IS NULL
        ORDER BY created_at DESC
    """)).mappings().all()

    return [dict(r) for r in rows]


@router.get("")
def alerts_by_center(center_id: str | None = None, db: Session = Depends(get_db)):
    if center_id:
        rows = db.execute(
            text("SELECT * FROM alerts WHERE center_id = :center_id ORDER BY created_at DESC"),
            {"center_id": center_id}
        ).mappings().all()
    else:
        rows = db.execute(
            text("SELECT * FROM alerts ORDER BY created_at DESC")
        ).mappings().all()

    return [dict(r) for r in rows]


@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    db.execute(
        text("UPDATE alerts SET resolved_at = NOW() WHERE id = :id"),
        {"id": alert_id}
    )
    db.commit()
    return {"success": True}