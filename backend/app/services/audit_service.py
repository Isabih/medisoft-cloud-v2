"""Lightweight audit-log helper.

Every operational action (remote agent command, SMS resend, backup update,
auto-heal, etc.) should call `log_audit(...)` so it shows up in the
/api/v1/audit/logs feed consumed by the UI.

Failures are swallowed — auditing must never break the originating action.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    action: str,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_name: Optional[str] = None,
    actor: Optional[str] = "system",
    outcome: str = "success",
    details: Optional[str] = None,
) -> None:
    try:
        db.execute(
            text(
                """
                INSERT INTO audit_logs
                    (action, target_type, target_id, target_name,
                     actor, outcome, details, created_at)
                VALUES
                    (:a, :tt, :ti, :tn, :ac, :oc, :d, :now)
                """
            ),
            {
                "a": action[:64],
                "tt": (target_type or None),
                "ti": (target_id or None),
                "tn": (target_name or None),
                "ac": (actor or "system")[:64],
                "oc": outcome if outcome in ("success", "failure", "pending") else "success",
                "d": (details or None),
                "now": datetime.utcnow(),
            },
        )
        db.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning("audit log insert failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
