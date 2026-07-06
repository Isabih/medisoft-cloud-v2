from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.services.sms_service import send_sms

router = APIRouter(prefix="/sms", tags=["sms"])


@router.get("/logs")
def list_logs(
    db: Session = Depends(get_db),
    center_id: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    where = "WHERE 1=1"
    params = {"limit": limit}
    if center_id:
        where += " AND center_id = :cid"
        params["cid"] = center_id

    rows = db.execute(
        text(f"""
            SELECT id, to_number, sender, recipient_role, center_id, center_name,
                   message, status, provider_message_id, error, sent_at, delivered_at
            FROM sms_logs {where}
            ORDER BY sent_at DESC
            LIMIT :limit
        """),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/{sms_id}/resend")
def resend(sms_id: str, db: Session = Depends(get_db)):
    from app.services.audit_service import log_audit
    row = db.execute(
        text("SELECT to_number, message, recipient_role, center_id, center_name "
             "FROM sms_logs WHERE id = :id"),
        {"id": sms_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404, "SMS log not found")
    res = send_sms(db, row["to_number"], row["message"],
                   row["recipient_role"], row["center_id"], row["center_name"])
    ok = bool(res and res.get("status") in ("sent", "delivered", "queued"))
    log_audit(
        db, "sms.resend",
        target_type="sms", target_id=str(sms_id),
        target_name=row["to_number"], actor="admin",
        outcome="success" if ok else "failure",
        details=f"to={row['to_number']} center={row['center_name']}",
    )
    return res
