"""System health-check endpoint.

Verifies that core subsystems are reachable after install:
- Database connectivity
- Registered API routers (key routes present)
- WebSocket manager state (active connection count)
- Agent control reachability (queued commands table accessible)
- Alert engine + SMS service config
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


def _check_db(db: Session) -> Dict[str, Any]:
    t0 = time.time()
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_table(db: Session, name: str) -> Dict[str, Any]:
    try:
        row = db.execute(text(f"SELECT COUNT(*) AS c FROM {name}")).first()
        return {"ok": True, "rows": int(row[0]) if row else 0}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_routes(request: Request, required: List[str]) -> Dict[str, Any]:
    paths = {getattr(r, "path", "") for r in request.app.routes}
    missing = [r for r in required if r not in paths]
    return {"ok": not missing, "missing": missing, "total_routes": len(paths)}


def _check_websocket(request: Request) -> Dict[str, Any]:
    try:
        from app.routers.websocket import manager  # type: ignore

        return {"ok": True, "active_connections": len(manager.active_connections)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _check_sms(db: Session) -> Dict[str, Any]:
    try:
        from app.services.sms_service import _load_config  # type: ignore
        cfg = _load_config(db)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    has_user = bool(cfg.get("username"))
    has_pass = bool(cfg.get("password"))
    admins = [p for p in str(cfg.get("admin_numbers") or "").split(",") if p.strip()]
    return {
        "ok": has_user and has_pass,
        "provider": cfg.get("provider") or "intouch",
        "username_set": has_user,
        "password_set": has_pass,
        "admin_recipients": len(admins),
    }


@router.get("/health-check")
def system_health_check(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    prefix = settings.api_v1_prefix
    required_routes = [
        f"{prefix}/health",
        f"{prefix}/auth/login",
        f"{prefix}/dashboard/centers-live",
        f"{prefix}/health-centers",
        f"{prefix}/hybrid/source-report",
        f"{prefix}/installer/local-agent",
        f"{prefix}/audit/logs",
        f"{prefix}/sms/logs",
        "/ws/monitor",
    ]

    checks = {
        "database": _check_db(db),
        "routes": _check_routes(request, required_routes),
        "websocket": _check_websocket(request),
        "agent_control": _check_table(db, "agent_commands") if True else {"ok": False},
        "audit_log": _check_table(db, "audit_logs"),
        "sms_logs": _check_table(db, "sms_logs"),
        "sms_config": _check_sms(db),
    }

    # agent_commands table may not exist on older installs — degrade gracefully
    if not checks["agent_control"]["ok"]:
        checks["agent_control"]["hint"] = "Run sql/upgrades_v3.sql to create agent_commands"

    overall = all(v.get("ok") for v in checks.values())
    return {
        "ok": overall,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_prefix": prefix,
        "checks": checks,
    }
