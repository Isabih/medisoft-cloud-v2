from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

RESEND_URL = "https://api.resend.com/emails"


def _load_config(db: Session) -> Dict[str, Any]:
    cfg = {
        "api_key": os.getenv("RESEND_API_KEY", ""),
        "from_email": os.getenv("ALERT_EMAIL_FROM", ""),
        "admin_emails": os.getenv("ADMIN_EMAILS", ""),
    }
    try:
        row = db.execute(text("SELECT * FROM settings WHERE id=1")).mappings().first()
        if row:
            for src, dst in (("resend_api_key", "api_key"), ("alert_email_from", "from_email"), ("admin_emails", "admin_emails")):
                v = row.get(src)
                if v not in (None, ""):
                    cfg[dst] = v
    except Exception:
        pass
    return cfg


def admin_emails(db: Session) -> List[str]:
    raw = _load_config(db).get("admin_emails") or ""
    return [x.strip() for x in str(raw).replace(";", ",").split(",") if x.strip()]


def send_email(db: Session, to: str, subject: str, html: str, center_id: Optional[str] = None, center_name: Optional[str] = None) -> Dict[str, Any]:
    cfg = _load_config(db)
    status = "failed"
    err = None
    provider_id = None
    if not cfg.get("api_key") or not cfg.get("from_email"):
        err = "Resend API key or sender email not configured"
    else:
        try:
            r = requests.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
                json={"from": cfg["from_email"], "to": [to], "subject": subject, "html": html},
                timeout=15,
            )
            if 200 <= r.status_code < 300:
                status = "sent"
                try:
                    provider_id = r.json().get("id")
                except Exception:
                    provider_id = None
            else:
                err = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as exc:
            err = str(exc)
    try:
        db.execute(text("""
            INSERT INTO admin_notifications (id, alert_id, channel, recipient, status, sent_at)
            VALUES (:id, NULL, 'email', :recipient, :status, :sent_at)
        """), {"id": str(uuid.uuid4()), "recipient": to, "status": status, "sent_at": datetime.utcnow()})
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    return {"to": to, "status": status, "error": err, "provider_id": provider_id}


def notify_admins_email(db: Session, subject: str, html: str, center_id: Optional[str] = None, center_name: Optional[str] = None) -> List[Dict[str, Any]]:
    return [send_email(db, e, subject, html, center_id, center_name) for e in admin_emails(db)]


def send_test_email(db: Session, to: str) -> Dict[str, Any]:
    return send_email(db, to, "Medisoft Guardian Cloud test email", "<p>Medisoft Guardian Cloud email alerts are configured correctly.</p>")
