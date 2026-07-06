from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

router = APIRouter(prefix="/sms", tags=["SMS"])

@router.get("/logs")
def get_sms_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT
            id,
            to_number,
            recipient_role,
            center_id,
            center_name,
            message,
            status,
            provider_message_id,
            error,
            sent_at,
            delivered_at
        FROM sms_logs
        ORDER BY sent_at DESC
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    return jsonable_encoder({
        "count": len(rows),
        "logs": [dict(row) for row in rows],
    })
