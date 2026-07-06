"""
Remote-control endpoints. Each call appends a row to `agent_actions`;
the local agent picks it up on its next /hybrid/source-report poll and
executes it (see auto_heal() in new_local-installer.sh).

Recognised actions (server-side; agent maps them to shell commands):
  - restart_mysql
  - restart_replica
  - reset_replica
  - start_replica
  - stop_replica
  - custom    (params is a free-form string)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_service import log_audit

router = APIRouter(prefix="/agent", tags=["agent"])

ALLOWED_ACTIONS = {
    "restart_mysql",
    "restart_replica",
    "reset_replica",
    "start_replica",
    "stop_replica",
    "custom",
}


class ActionRequest(BaseModel):
    params: Optional[str] = None
    requested_by: Optional[str] = "admin"


def _queue(db: Session, foss_id: str, action: str, params: Optional[str], who: Optional[str]):
    if action not in ALLOWED_ACTIONS:
        log_audit(db, f"agent.{action}", target_type="health_center",
                  target_id=foss_id, actor=who, outcome="failure",
                  details=f"unknown action: {action}")
        return {"ok": False, "error": f"unknown action: {action}"}
    db.execute(
        text(
            """
            INSERT INTO agent_actions (foss_id, action, params, status, requested_by, created_at)
            VALUES (:f, :a, :p, 'pending', :w, :now)
            """
        ),
        {
            "f": foss_id, "a": action, "p": params or "",
            "w": who or "admin", "now": datetime.utcnow(),
        },
    )
    db.commit()
    log_audit(
        db, f"agent.{action}",
        target_type="health_center", target_id=foss_id,
        actor=who, outcome="pending",
        details=f"Queued for agent (params={params or '-'})",
    )
    return {"ok": True, "queued": action, "foss_id": foss_id}


@router.post("/{foss_id}/restart-mysql")
def restart_mysql(foss_id: str, body: ActionRequest = ActionRequest(), db: Session = Depends(get_db)):
    return _queue(db, foss_id, "restart_mysql", body.params, body.requested_by)


@router.post("/{foss_id}/restart-replica")
def restart_replica(foss_id: str, body: ActionRequest = ActionRequest(), db: Session = Depends(get_db)):
    return _queue(db, foss_id, "restart_replica", body.params, body.requested_by)


@router.post("/{foss_id}/reset-replica")
def reset_replica(foss_id: str, body: ActionRequest = ActionRequest(), db: Session = Depends(get_db)):
    return _queue(db, foss_id, "reset_replica", body.params, body.requested_by)


@router.post("/{foss_id}/start-replica")
def start_replica(foss_id: str, body: ActionRequest = ActionRequest(), db: Session = Depends(get_db)):
    return _queue(db, foss_id, "start_replica", body.params, body.requested_by)


@router.post("/{foss_id}/stop-replica")
def stop_replica(foss_id: str, body: ActionRequest = ActionRequest(), db: Session = Depends(get_db)):
    return _queue(db, foss_id, "stop_replica", body.params, body.requested_by)


@router.post("/{foss_id}/custom")
def custom(foss_id: str, body: ActionRequest, db: Session = Depends(get_db)):
    return _queue(db, foss_id, "custom", body.params, body.requested_by)


@router.get("/{foss_id}/actions")
def list_actions(foss_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT id, action, params, status, requested_by, created_at, "
            "dispatched_at, result FROM agent_actions WHERE foss_id = :f "
            "ORDER BY created_at DESC LIMIT 50"
        ),
        {"f": foss_id},
    ).mappings().all()
    return [dict(r) for r in rows]

class ActionResult(BaseModel):
    status: str = "done"
    result: Optional[str] = ""


@router.post("/{foss_id}/actions/{action_id}/result")
def report_action_result(foss_id: str, action_id: int, body: ActionResult, db: Session = Depends(get_db)):
    safe_status = body.status if body.status in {"done", "failed"} else "done"
    db.execute(
        text("""
            UPDATE agent_actions
            SET status=:status, result=:result
            WHERE id=:id AND foss_id=:f
        """),
        {"status": safe_status, "result": body.result or "", "id": action_id, "f": foss_id},
    )
    db.commit()
    log_audit(db, "agent.action_result", target_type="health_center", target_id=foss_id, actor="agent", outcome="success", details=f"action_id={action_id} status={safe_status} result={body.result or ''}")
    return {"ok": True, "status": safe_status}
