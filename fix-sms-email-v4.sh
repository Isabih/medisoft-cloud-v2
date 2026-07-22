#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Medisoft SMS + Email Fix v4 ==="
read -s -p "Enter MySQL root password: " MYSQL_ROOT_PASSWORD
echo

cp "$BACKEND/app/main.py" "$BACKEND/app/main.py.bak_sms_email_$(date +%F_%H%M%S)"

echo "=== Updating database schema ==="
mysql -u root -p"$MYSQL_ROOT_PASSWORD" medisoft_guardian <<'SQL'
ALTER TABLE settings ADD COLUMN sms_enabled TINYINT(1) NOT NULL DEFAULT 1;
ALTER TABLE settings ADD COLUMN sms_api_url VARCHAR(500) NULL DEFAULT 'https://www.intouchsms.co.rw/api/sendsms/.json';
ALTER TABLE settings ADD COLUMN sms_timeout_seconds INT NOT NULL DEFAULT 30;
ALTER TABLE settings ADD COLUMN email_enabled TINYINT(1) NOT NULL DEFAULT 1;
SQL
echo "Schema updated. Ignore duplicate-column errors if already added."

cat > "$BACKEND/app/routers/notifications_v4.py" <<'PY'
import uuid
import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/settings", tags=["notifications-v4"])


class SmsTestRequest(BaseModel):
    to: str


class EmailTestRequest(BaseModel):
    to: str


def get_settings(db: Session):
    row = db.execute(text("SELECT * FROM settings WHERE id=1")).mappings().first()
    if not row:
        db.execute(text("INSERT INTO settings (id) VALUES (1)"))
        db.commit()
        row = db.execute(text("SELECT * FROM settings WHERE id=1")).mappings().first()
    return dict(row)


def log_sms(db: Session, to_number, role, center_id, center_name, message, status, error=None, provider_message_id=None):
    db.execute(text("""
        INSERT INTO sms_logs (
            id, to_number, recipient_role, center_id, center_name,
            message, status, provider_message_id, error, sent_at
        )
        VALUES (
            :id, :to_number, :role, :center_id, :center_name,
            :message, :status, :provider_message_id, :error, NOW()
        )
    """), {
        "id": str(uuid.uuid4()),
        "to_number": to_number,
        "role": role,
        "center_id": center_id,
        "center_name": center_name,
        "message": message,
        "status": status,
        "provider_message_id": provider_message_id,
        "error": error,
    })
    db.commit()


@router.get("")
def read_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("")
def update_settings(payload: dict, db: Session = Depends(get_db)):
    current = get_settings(db)

    allowed = set(current.keys())
    allowed.discard("id")

    updates = {k: v for k, v in payload.items() if k in allowed}

    if not updates:
        return get_settings(db)

    set_sql = ", ".join([f"{k}=:{k}" for k in updates.keys()])
    updates["id"] = 1

    db.execute(text(f"UPDATE settings SET {set_sql} WHERE id=:id"), updates)
    db.commit()

    return get_settings(db)


@router.post("/sms/test")
def test_sms(payload: SmsTestRequest, db: Session = Depends(get_db)):
    s = get_settings(db)

    api_url = s.get("sms_api_url") or "https://www.intouchsms.co.rw/api/sendsms/.json"
    username = s.get("sms_username")
    password = s.get("sms_password")
    sender = s.get("sms_sender_id") or "MEDISOFT"
    timeout = int(s.get("sms_timeout_seconds") or 30)

    if not username or not password:
        raise HTTPException(status_code=400, detail="SMS username or password is missing")

    message = "Medisoft Guardian test SMS"

    try:
        r = requests.post(
            api_url,
            data={
                "recipients": payload.to,
                "message": message,
                "sender": sender,
            },
            auth=(username, password),
            timeout=timeout,
        )

        body = r.text

        success = r.status_code == 200 and not any(x in body.lower() for x in [
            "exceed your account balance",
            "insufficient",
            "failed",
            "error",
            "invalid",
        ])

        status = "sent" if success else "failed"

        log_sms(
            db=db,
            to_number=payload.to,
            role="test",
            center_id=None,
            center_name="Settings Test",
            message=message,
            status=status,
            error=None if success else body,
            provider_message_id=str(r.status_code),
        )

        return {
            "success": success,
            "http_status": r.status_code,
            "gateway_response": body,
            "reason": "SMS sent successfully" if success else body,
        }

    except Exception as e:
        log_sms(
            db=db,
            to_number=payload.to,
            role="test",
            center_id=None,
            center_name="Settings Test",
            message=message,
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Could not reach SMS gateway: {str(e)}")


@router.post("/email/test")
def test_email(payload: EmailTestRequest, db: Session = Depends(get_db)):
    s = get_settings(db)

    api_key = s.get("resend_api_key")
    sender = s.get("alert_email_from") or "alerts@medisoft.rw"

    if not api_key:
        raise HTTPException(status_code=400, detail="Resend API key is missing")

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender,
                "to": [payload.to],
                "subject": "Medisoft Guardian Test Email",
                "html": "<p>Medisoft Guardian email integration is working.</p>",
            },
            timeout=30,
        )

        ok = 200 <= r.status_code < 300

        return {
            "success": ok,
            "http_status": r.status_code,
            "resend_response": r.text,
            "reason": "Email sent successfully" if ok else r.text,
        }

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Resend email gateway: {str(e)}")
PY

echo "=== Register notification router ==="
python3 - <<'PY'
from pathlib import Path

p = Path("/opt/medisoft-guardian-v3/backend/app/main.py")
s = p.read_text()

if "notifications_v4" not in s:
    s = s.replace(
        "import app.routers.auth as auth",
        "import app.routers.auth as auth\nimport app.routers.notifications_v4 as notifications_v4"
    )

if "app.include_router(notifications_v4.router" not in s:
    s = s.replace(
        "app.include_router(auth.router, prefix=settings.api_v1_prefix)",
        "app.include_router(auth.router, prefix=settings.api_v1_prefix)\napp.include_router(notifications_v4.router, prefix=settings.api_v1_prefix)"
    )

p.write_text(s)
PY

echo "=== Restart backend ==="
sudo systemctl restart medisoft-guardian-v4-backend
sleep 3

echo "=== Test settings endpoint ==="
curl -s http://127.0.0.1:8004/api/v1/settings | jq '.sms_api_url, .sms_username, .sms_sender_id, .alert_email_from'

echo "DONE ✅"
echo "Now Settings page should save SMS API URL and show exact gateway response."
