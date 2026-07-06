"""Per-health-center chronological timeline (heartbeat, replication, SMS, repair...)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/timeline", tags=["timeline"])


class TimelineEventIn(BaseModel):
    center_id: str
    event_type: str
    title: str
    severity: str | None = "info"
    message: str | None = None
    center_name: str | None = None


@router.get("/{center_id}")
def list_timeline(center_id: str, limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    """Aggregate events for a center: manual + heartbeats + alerts + SMS + repairs."""
    events: list[dict] = []

    try:
        rows = db.execute(text(
            """
            SELECT id, event_type, severity, title, message, created_at
            FROM center_timeline_events
            WHERE center_id = :cid
            ORDER BY created_at DESC
            LIMIT :lim
            """
        ), {"cid": center_id, "lim": limit}).mappings().all()
        events.extend(dict(r) for r in rows)
    except Exception:
        pass

    # Alerts
    try:
        rows = db.execute(text(
            """
            SELECT CONCAT('alert-', id) AS id, 'alert' AS event_type,
                   severity, type AS title, message, created_at
            FROM alerts WHERE center_id = :cid
            ORDER BY created_at DESC LIMIT 100
            """
        ), {"cid": center_id}).mappings().all()
        events.extend(dict(r) for r in rows)
    except Exception:
        pass

    # SMS logs (source + destination + body)
    try:
        rows = db.execute(text(
            """
            SELECT CONCAT('sms-', id) AS id, 'sms' AS event_type,
                   CASE WHEN status='failed' THEN 'warning' ELSE 'info' END AS severity,
                   CONCAT('SMS ', UPPER(status), ' → ', to_number) AS title,
                   message, sent_at AS created_at
            FROM sms_logs WHERE center_id = :cid
            ORDER BY sent_at DESC LIMIT 100
            """
        ), {"cid": center_id}).mappings().all()
        events.extend(dict(r) for r in rows)
    except Exception:
        pass

    # Guardian / repair events
    try:
        rows = db.execute(text(
            """
            SELECT CONCAT('rep-', id) AS id, 'repair' AS event_type,
                   CASE WHEN status='failure' THEN 'critical'
                        WHEN status='success' THEN 'success' ELSE 'info' END AS severity,
                   CONCAT('Auto-repair: ', event_type) AS title,
                   COALESCE(details, '') AS message, created_at
            FROM replication_guardian_events WHERE center_id = :cid
            ORDER BY created_at DESC LIMIT 100
            """
        ), {"cid": center_id}).mappings().all()
        events.extend(dict(r) for r in rows)
    except Exception:
        pass

    events.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    return events[:limit]


@router.post("")
def add_event(payload: TimelineEventIn, db: Session = Depends(get_db)):
    if not payload.center_id or not payload.event_type or not payload.title:
        raise HTTPException(400, "center_id, event_type and title are required")
    db.execute(text(
        """
        INSERT INTO center_timeline_events
            (center_id, center_name, event_type, severity, title, message)
        VALUES (:cid, :cn, :et, :sev, :tt, :msg)
        """
    ), {
        "cid": payload.center_id,
        "cn": payload.center_name,
        "et": payload.event_type[:50],
        "sev": (payload.severity or "info")[:20],
        "tt": payload.title[:255],
        "msg": payload.message,
    })
    db.commit()
    return {"ok": True}


def record(db: Session, center_id: str, event_type: str, title: str,
           severity: str = "info", message: str | None = None,
           center_name: str | None = None) -> None:
    """Internal helper — never raises."""
    try:
        db.execute(text(
            """
            INSERT INTO center_timeline_events
                (center_id, center_name, event_type, severity, title, message)
            VALUES (:cid, :cn, :et, :sev, :tt, :msg)
            """
        ), {
            "cid": center_id, "cn": center_name,
            "et": event_type[:50], "sev": severity[:20],
            "tt": title[:255], "msg": message,
        })
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
