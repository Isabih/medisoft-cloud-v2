"""
Cloud Admin Command Center
These endpoints are separate from health-centre First Aid.
They affect the central/cloud server only, and are disabled by default for safety.
Enable with ENABLE_CLOUD_ADMIN_COMMANDS=true only for trusted super admins.
"""
import os
import subprocess
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_service import log_audit

router = APIRouter(prefix="/cloud-admin", tags=["cloud-admin-commands"])

ALLOWED_CLOUD_ACTIONS = {
    "restart_backend": ["systemctl", "restart", "medisoft-monitor-backend"],
    "restart_frontend": ["systemctl", "restart", "medisoft-monitor-frontend"],
    "restart_nginx": ["systemctl", "restart", "nginx"],
    "restart_grafana": ["systemctl", "restart", "grafana-server"],
    "restart_prometheus": ["systemctl", "restart", "prometheus"],
    "restart_cloud_mysql": ["systemctl", "restart", "mysql"],
}

class CloudCommandRequest(BaseModel):
    requested_by: Optional[str] = "super_admin"
    confirm: Optional[bool] = False
    reason: Optional[str] = None


def _enabled():
    return os.getenv("ENABLE_CLOUD_ADMIN_COMMANDS", "false").lower() == "true"


@router.get("/commands")
def list_cloud_commands():
    return {
        "target": "cloud_server",
        "enabled": _enabled(),
        "warning": "These commands affect the central cloud server only, not health centres.",
        "actions": list(ALLOWED_CLOUD_ACTIONS.keys()),
    }


@router.post("/commands/{action}")
def run_cloud_command(action: str, body: CloudCommandRequest, db: Session = Depends(get_db)):
    if action not in ALLOWED_CLOUD_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported cloud command: {action}")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required for cloud admin commands")
    if not _enabled():
        log_audit(db, f"cloud_admin.{action}", target_type="cloud_server", target_id="cloud", actor=body.requested_by, outcome="blocked", details="ENABLE_CLOUD_ADMIN_COMMANDS is false")
        raise HTTPException(status_code=403, detail="Cloud admin commands are disabled. Set ENABLE_CLOUD_ADMIN_COMMANDS=true to enable.")

    started = datetime.utcnow()
    try:
        proc = subprocess.run(ALLOWED_CLOUD_ACTIONS[action], text=True, capture_output=True, timeout=60)
        ok = proc.returncode == 0
        result = (proc.stdout + "\n" + proc.stderr).strip()[-2000:]
        log_audit(db, f"cloud_admin.{action}", target_type="cloud_server", target_id="cloud", actor=body.requested_by, outcome="success" if ok else "failure", details=result)
        return {"ok": ok, "target": "cloud_server", "action": action, "started_at": started.isoformat() + "Z", "result": result}
    except Exception as exc:
        log_audit(db, f"cloud_admin.{action}", target_type="cloud_server", target_id="cloud", actor=body.requested_by, outcome="failure", details=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
