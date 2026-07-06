from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.services.retention_service import ensure_retention_schema

router = APIRouter(prefix="/settings", tags=["settings"])

# Columns the API is allowed to read/write — anything else in the payload is ignored.
ALLOWED_FIELDS = {
    "day_close_time", "auto_generate_reports", "polling_interval",
    "heartbeat_timeout_seconds", "backup_check_time",
    "sms_provider", "sms_sender_id", "sms_username", "sms_password",
    "sms_api_url", "admin_phone_numbers",
    "admin_emails", "resend_api_key", "alert_email_from",
    "detailed_retention_days", "incident_history_retention_days",
    "retention_run_hour_utc", "enable_retention_cleanup",
}

SECRET_FIELDS = {"sms_password", "resend_api_key"}


def _mask(value):
    if not value:
        return ""
    s = str(value)
    return "•" * min(len(s), 8)


def _read(db: Session):
    ensure_retention_schema(db)
    row = db.execute(text("SELECT * FROM settings WHERE id = 1")).mappings().first()
    if not row:
        db.execute(text("""
            INSERT INTO settings (id, day_close_time, auto_generate_reports, polling_interval,
                                  heartbeat_timeout_seconds, backup_check_time)
            VALUES (1, '00:00:00', TRUE, 30, 120, '07:00:00')
        """))
        db.commit()
        row = db.execute(text("SELECT * FROM settings WHERE id = 1")).mappings().first()
    return dict(row)


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    data = _read(db)
    # Never return raw secrets — only a masked indicator and a boolean.
    for f in SECRET_FIELDS:
        if f in data:
            data[f"{f}_set"] = bool(data[f])
            data[f] = _mask(data[f])
    return data


@router.put("")
def update_settings(payload: dict, db: Session = Depends(get_db)):
    fields, params = [], {}
    for key, value in (payload or {}).items():
        if key not in ALLOWED_FIELDS:
            continue
        # Empty string on a secret means "keep existing value".
        if key in SECRET_FIELDS and (value is None or value == ""):
            continue
        fields.append(f"{key} = :{key}")
        params[key] = value

    if fields:
        db.execute(text(f"UPDATE settings SET {', '.join(fields)} WHERE id = 1"), params)
        db.commit()

    return get_settings(db)


class TestSmsRequest(BaseModel):
    to: str


@router.post("/sms/test")
def send_test_sms(req: TestSmsRequest, db: Session = Depends(get_db)):
    if not req.to:
        raise HTTPException(400, "Recipient phone number is required")
    from app.services.sms_service import send_test_sms as _send
    return _send(db, req.to)


class TestEmailRequest(BaseModel):
    to: str


@router.post("/email/test")
def send_test_email(req: TestEmailRequest, db: Session = Depends(get_db)):
    if not req.to:
        raise HTTPException(400, "Recipient email is required")
    from app.services.email_service import send_test_email as _send
    return _send(db, req.to)
