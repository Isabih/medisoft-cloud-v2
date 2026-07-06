from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_service import log_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def list_logs(
    db: Session = Depends(get_db),
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    outcome: Optional[str] = Query(None),
    limit: int = Query(500, le=2000),
):
    where = "WHERE 1=1"
    p: dict = {"limit": limit}
    if target_type:
        where += " AND target_type = :tt"; p["tt"] = target_type
    if target_id:
        where += " AND target_id = :ti"; p["ti"] = target_id
    if action:
        where += " AND action LIKE :a"; p["a"] = f"%{action}%"
    if outcome:
        where += " AND outcome = :o"; p["o"] = outcome
    try:
        rows = db.execute(
            text(
                f"""
                SELECT id, action, target_type, target_id, target_name,
                       actor, outcome, details, created_at
                FROM audit_logs
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            p,
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


@router.post("/log")
def write_log(
    payload: dict,
    db: Session = Depends(get_db),
):
    """Manual log entry from the UI (e.g. operator notes)."""
    log_audit(
        db,
        payload.get("action") or "manual.note",
        target_type=payload.get("target_type"),
        target_id=payload.get("target_id"),
        target_name=payload.get("target_name"),
        actor=payload.get("actor") or "admin",
        outcome=payload.get("outcome") or "success",
        details=payload.get("details"),
    )
    return {"ok": True}
