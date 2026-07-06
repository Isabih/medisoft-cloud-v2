"""
SMS service — Intouch Rwanda gateway (https://intouchsms.co.rw).

Credentials are read first from the `settings` table (configurable from
the Settings page in the UI), then from environment variables as a
fallback for first-boot installs:

  INTOUCH_USERNAME      (or legacy AT_USERNAME)
  INTOUCH_PASSWORD      (or legacy AT_API_KEY)
  INTOUCH_SENDER_ID     (or legacy AT_SENDER_ID)
  INTOUCH_API_URL       (default: https://intouchsms.co.rw)
  ADMIN_PHONE_NUMBERS   comma-separated E.164 list
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://intouchsms.co.rw"


def _load_config(db: Session) -> Dict[str, Any]:
    """Read SMS config from settings table, falling back to env vars."""
    cfg = {
        "provider": "intouch",
        "api_url": os.getenv("INTOUCH_API_URL", DEFAULT_API_URL),
        "username": os.getenv("INTOUCH_USERNAME") or os.getenv("AT_USERNAME"),
        "password": os.getenv("INTOUCH_PASSWORD") or os.getenv("AT_API_KEY"),
        "sender_id": os.getenv("INTOUCH_SENDER_ID") or os.getenv("AT_SENDER_ID"),
        "admin_numbers": os.getenv("ADMIN_PHONE_NUMBERS", ""),
    }
    try:
        row = db.execute(text("SELECT * FROM settings WHERE id = 1")).mappings().first()
        if row:
            for src, dst in (
                ("sms_provider", "provider"),
                ("sms_api_url", "api_url"),
                ("sms_username", "username"),
                ("sms_password", "password"),
                ("sms_sender_id", "sender_id"),
                ("admin_phone_numbers", "admin_numbers"),
            ):
                v = row.get(src) if hasattr(row, "get") else row[src] if src in row.keys() else None
                if v not in (None, ""):
                    cfg[dst] = v
    except Exception:
        pass
    return cfg


def _admin_numbers(db: Session) -> List[str]:
    raw = _load_config(db).get("admin_numbers") or ""
    return [n.strip() for n in str(raw).split(",") if n.strip()]


def _post_intouch(cfg: Dict[str, Any], to: str, message: str) -> Dict[str, Any]:
    """POST to Intouch Rwanda gateway. Returns {status, provider_message_id, error}."""
    url = (cfg.get("api_url") or DEFAULT_API_URL).rstrip("/")
    payload = {
        "recipients": [to],
        "message": message,
        "sender": cfg.get("sender_id") or "",
        "username": cfg.get("username") or "",
        "password": cfg.get("password") or "",
    }
    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text}
            return {
                "status": "sent",
                "provider_message_id": str(body.get("messageId") or body.get("id") or "") or None,
                "error": None,
                "raw": body,
            }
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": f"HTTP {r.status_code}: {r.text[:200]}",
        }
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "provider_message_id": None, "error": str(e)}


def send_sms(
    db: Session,
    to: str,
    message: str,
    recipient_role: str = "admin",
    center_id: Optional[str] = None,
    center_name: Optional[str] = None,
) -> dict:
    """Send one SMS via the configured gateway and persist to sms_logs."""
    log_id = str(uuid.uuid4())
    cfg = _load_config(db)

    if not cfg.get("username") or not cfg.get("password"):
        status, provider_msg_id, error = "failed", None, "SMS credentials not configured (Settings → SMS)"
        logger.error(error)
    else:
        result = _post_intouch(cfg, to, message)
        status = result["status"]
        provider_msg_id = result["provider_message_id"]
        error = result["error"]

    db.execute(
        text(
            """
            INSERT INTO sms_logs
              (id, to_number, sender, recipient_role, center_id, center_name,
               message, status, provider_message_id, error, sent_at)
            VALUES
              (:id, :to, :sender, :role, :cid, :cname, :msg, :st, :pid, :err, :sent)
            """
        ),
        {
            "id": log_id, "to": to,
            "sender": cfg.get("sender_id") or "",
            "role": recipient_role,
            "cid": center_id, "cname": center_name,
            "msg": message, "st": status,
            "pid": provider_msg_id, "err": error,
            "sent": datetime.utcnow(),
        },
    )
    db.commit()

    return {
        "id": log_id, "to_number": to, "recipient_role": recipient_role,
        "center_id": center_id, "center_name": center_name,
        "message": message, "status": status,
        "provider_message_id": provider_msg_id, "error": error,
        "sent_at": datetime.utcnow().isoformat(),
    }


def notify_admins(db: Session, message: str, center_id: Optional[str] = None,
                  center_name: Optional[str] = None) -> List[dict]:
    return [send_sms(db, n, message, "admin", center_id, center_name) for n in _admin_numbers(db)]


def notify_head_of_center(db: Session, head_phone: str, message: str,
                          center_id: str, center_name: str) -> Optional[dict]:
    if not head_phone:
        return None
    return send_sms(db, head_phone, message, "head_of_center", center_id, center_name)


def build_replica_down_message(center_name: str, contact: str, io: str, sql: str,
                               anydesk: Optional[str], rustdesk: Optional[str],
                               error_msg: str, ai_suggestion: Optional[str]) -> str:
    parts = [
        f"[MEDISOFT] {center_name} replica issue.",
        f"IO={io} SQL={sql}.",
        f"Contact: {contact or 'N/A'}.",
    ]
    if anydesk:
        parts.append(f"AnyDesk: {anydesk}.")
    if rustdesk:
        parts.append(f"RustDesk: {rustdesk}.")
    if error_msg:
        parts.append(f"Err: {error_msg[:80]}.")
    if ai_suggestion:
        parts.append(f"AI: {ai_suggestion[:120]}")
    return " ".join(parts)


def send_test_sms(db: Session, to: str) -> dict:
    """Convenience for the Settings → 'Send test SMS' button."""
    return send_sms(db, to, "[MEDISOFT] Test SMS — your Intouch gateway is configured correctly.", "test")
