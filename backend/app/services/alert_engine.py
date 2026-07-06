"""
Background alert engine.

Runs every 60 seconds:
  * Any HC whose last source_report.received_at is older than 3 minutes
    is treated as OFFLINE. We SMS the head-of-center (phone_number_1)
    and all admin numbers — once per outage to avoid spam.
  * If io_running != 'Yes' or sql_running != 'Yes', SMS admins
    once per outage with the centre name, contact, AnyDesk/RustDesk IDs
    and a short AI-suggested fix.

The de-dup is in-memory; restarting FastAPI will re-send active outages,
which is intentional (it confirms the alerter survived the restart).
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple

from sqlalchemy import text

from app.core.database import SessionLocal

try:
    from app.services.sms_service import (
        notify_admins, notify_head_of_center, build_replica_down_message,
    )
except Exception:  # pragma: no cover
    notify_admins = notify_head_of_center = build_replica_down_message = None
try:
    from app.services.email_service import notify_admins_email
except Exception:  # pragma: no cover
    notify_admins_email = None

logger = logging.getLogger(__name__)

POLL_SECONDS   = 60
OFFLINE_AFTER  = timedelta(minutes=3)

# (foss_id, kind) -> sent_at
_seen: Dict[Tuple[str, str], datetime] = {}
_seen_lock = threading.Lock()


def _already_alerted(key: Tuple[str, str], cooldown=timedelta(hours=1)) -> bool:
    with _seen_lock:
        last = _seen.get(key)
        if last and datetime.utcnow() - last < cooldown:
            return True
        _seen[key] = datetime.utcnow()
        return False


def _clear(key: Tuple[str, str]):
    with _seen_lock:
        _seen.pop(key, None)


def _tick():
    if notify_admins is None:
        return
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT sr.foss_id, sr.health_center_name, sr.received_at,
                       sr.io_running, sr.sql_running,
                       hc.id  AS hc_id,
                       hc.phone_number_1, hc.phone_contact_1,
                       hc.anydesk_id, hc.rustdesk_id
                FROM source_reports sr
                LEFT JOIN health_centers hc ON hc.foss_id = sr.foss_id
                """
            )
        ).mappings().all()

        now = datetime.utcnow()
        for r in rows:
            f = r["foss_id"]
            name = r["health_center_name"] or f

            # 1. Offline? -> notify ONLY the head of the health center
            age = now - r["received_at"] if r["received_at"] else timedelta(days=1)
            if age > OFFLINE_AFTER:
                if not _already_alerted((f, "offline")):
                    msg = (
                        f"[MEDISOFT] {name} local server is OFFLINE / not reachable "
                        f"(no heartbeat for {int(age.total_seconds()//60)} min). "
                        f"Please check the server power and internet connection."
                    )
                    try:
                        if r.get("phone_number_1"):
                            notify_head_of_center(db, r["phone_number_1"], msg,
                                                  r.get("hc_id") or "", name)
                        if notify_admins_email is not None:
                            notify_admins_email(db, f"[MEDISOFT] {name} local server offline", f"<p>{msg}</p>", r.get("hc_id") or "", name)
                    except Exception as exc:
                        logger.warning("offline notification failed: %s", exc)
                continue  # don't also fire replica alert for an offline host
            else:
                _clear((f, "offline"))

            # 2. Replica IO / SQL down?
            io_ok  = (r["io_running"]  or "").lower() == "yes"
            sql_ok = (r["sql_running"] or "").lower() == "yes"
            if not (io_ok and sql_ok):
                if not _already_alerted((f, "replica")):
                    msg = build_replica_down_message(
                        name, r.get("phone_contact_1"),
                        r["io_running"] or "?", r["sql_running"] or "?",
                        r.get("anydesk_id"), r.get("rustdesk_id"),
                        error_msg="",
                        ai_suggestion="Try Auto-Heal from the dashboard or "
                                      "STOP/RESET/START REPLICA on the source.",
                    )
                    try:
                        notify_admins(db, msg, r.get("hc_id") or "", name)
                        if notify_admins_email is not None:
                            notify_admins_email(db, f"[MEDISOFT] {name} replica problem", f"<p>{msg}</p>", r.get("hc_id") or "", name)
                    except Exception as exc:
                        logger.warning("replica notification failed: %s", exc)
            else:
                _clear((f, "replica"))
    except Exception as exc:
        logger.warning("alert engine tick failed: %s", exc)
    finally:
        db.close()


def _loop():
    logger.info("Medisoft alert engine started (poll=%ss)", POLL_SECONDS)
    while True:
        try:
            _tick()
        except Exception:
            logger.exception("alert engine loop error")
        time.sleep(POLL_SECONDS)


def start_alert_engine():
    t = threading.Thread(target=_loop, name="medisoft-alert-engine", daemon=True)
    t.start()
    return t
