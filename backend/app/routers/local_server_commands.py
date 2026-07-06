"""
Local Server Command Center
These endpoints affect ONE selected health-centre/local server only.
The cloud backend DOES NOT execute the command directly. It queues the command
in agent_actions; the matching local agent pulls it and executes it locally.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_service import log_audit

router = APIRouter(prefix="/local-servers", tags=["local-server-commands"])

# Dashboard/local first aid actions. These must be executed by the local agent only.
ALLOWED_LOCAL_ACTIONS = {
    "restart_mysql": "Restart local MySQL service",
    "start_replica": "Start local replica channel",
    "stop_replica": "Stop local replica channel",
    "restart_replica": "Restart local replica channel",
    "start_sql": "Start local SQL thread for the configured channel",
    "start_io": "Start local IO thread for the configured channel",
    "stop_sql": "Stop local SQL thread for the configured channel",
    "stop_io": "Stop local IO thread for the configured channel",
    "test_mysql": "Test local MySQL connectivity",
    "run_diagnostics": "Collect local diagnostic status",
    "refresh_status": "Send an immediate status report",
}

class CommandRequest(BaseModel):
    requested_by: Optional[str] = "admin"
    channel_name: Optional[str] = None
    params: Optional[str] = None
    reason: Optional[str] = None

class CommandResult(BaseModel):
    status: str = "done"
    result: Optional[str] = ""


def _queue_local_command(db: Session, server_id: str, action: str, body: CommandRequest):
    if action not in ALLOWED_LOCAL_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported local-server command: {action}")

    # If dashboard did not pass channel_name, use latest reported channel for this server.
    channel = body.channel_name
    if not channel:
        row = db.execute(
            text("SELECT channel_name FROM source_reports WHERE foss_id=:f LIMIT 1"),
            {"f": server_id},
        ).mappings().first()
        channel = row["channel_name"] if row and row.get("channel_name") else ""

    params = {
        "channel_name": channel,
        "params": body.params or "",
        "reason": body.reason or "dashboard first aid",
        "target": "local_server",
    }

    import json
    db.execute(text("""
        INSERT INTO agent_actions (foss_id, action, params, status, requested_by, created_at)
        VALUES (:f, :a, :p, 'pending', :w, :now)
    """), {
        "f": server_id,
        "a": action,
        "p": json.dumps(params),
        "w": body.requested_by or "admin",
        "now": datetime.utcnow(),
    })
    db.commit()

    log_audit(
        db,
        f"local_server_command.{action}",
        target_type="local_server",
        target_id=server_id,
        actor=body.requested_by or "admin",
        outcome="pending",
        details=f"Queued local command. channel={channel or '-'} reason={body.reason or '-'}",
    )
    return {
        "ok": True,
        "target": "local_server",
        "server_id": server_id,
        "channel_name": channel,
        "queued": action,
        "message": "Command queued. The local agent will execute it on that health-centre server only.",
    }


@router.post("/{server_id}/commands/{action}")
def queue_local_command(server_id: str, action: str, body: CommandRequest = CommandRequest(), db: Session = Depends(get_db)):
    return _queue_local_command(db, server_id, action, body)


@router.post("/{server_id}/commands/restart-replica")
def restart_replica(server_id: str, body: CommandRequest = CommandRequest(), db: Session = Depends(get_db)):
    return _queue_local_command(db, server_id, "restart_replica", body)


@router.post("/{server_id}/commands/start-sql")
def start_sql(server_id: str, body: CommandRequest = CommandRequest(), db: Session = Depends(get_db)):
    return _queue_local_command(db, server_id, "start_sql", body)


@router.post("/{server_id}/commands/start-io")
def start_io(server_id: str, body: CommandRequest = CommandRequest(), db: Session = Depends(get_db)):
    return _queue_local_command(db, server_id, "start_io", body)


@router.post("/{server_id}/commands/restart-mysql")
def restart_mysql(server_id: str, body: CommandRequest = CommandRequest(), db: Session = Depends(get_db)):
    return _queue_local_command(db, server_id, "restart_mysql", body)


@router.get("/{server_id}/commands")
def list_local_commands(server_id: str, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, foss_id AS server_id, action, params, status, requested_by,
               created_at, dispatched_at, result
        FROM agent_actions
        WHERE foss_id=:f
        ORDER BY created_at DESC
        LIMIT 100
    """), {"f": server_id}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{server_id}/commands/next")
def get_next_local_command(server_id: str, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT id, action, params
        FROM agent_actions
        WHERE foss_id=:f AND status='pending'
        ORDER BY created_at ASC
        LIMIT 1
    """), {"f": server_id}).mappings().first()
    if not row:
        return {"ok": True, "command": None}
    db.execute(text("UPDATE agent_actions SET status='dispatched', dispatched_at=:now WHERE id=:id"), {"id": row["id"], "now": datetime.utcnow()})
    db.commit()
    return {"ok": True, "command": dict(row)}


@router.post("/{server_id}/commands/{command_id}/result")
def report_local_command_result(server_id: str, command_id: int, body: CommandResult, db: Session = Depends(get_db)):
    status = body.status if body.status in {"done", "failed"} else "done"
    db.execute(text("""
        UPDATE agent_actions
        SET status=:status, result=:result
        WHERE id=:id AND foss_id=:f
    """), {"status": status, "result": body.result or "", "id": command_id, "f": server_id})
    db.commit()
    log_audit(db, "local_server_command.result", target_type="local_server", target_id=server_id, actor="agent", outcome=status, details=f"command_id={command_id} result={body.result or ''}")
    return {"ok": True, "status": status}
