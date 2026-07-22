#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Fix InTouch SMS Final ==="
read -s -p "Enter MySQL root password: " MYSQL_ROOT_PASSWORD
echo

echo "=== Backup sms_service.py ==="
cp "$BACKEND/app/services/sms_service.py" "$BACKEND/app/services/sms_service.py.bak_$(date +%F_%H%M%S)"

echo "=== Fix sms_logs schema safely ==="
mysql -u root -p"$MYSQL_ROOT_PASSWORD" medisoft_guardian <<'SQL'
SET @db='medisoft_guardian';

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='sender'),
  'ALTER TABLE sms_logs ADD COLUMN sender VARCHAR(100) NULL',
  'SELECT "sender exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='recipient_role'),
  'ALTER TABLE sms_logs ADD COLUMN recipient_role VARCHAR(50) NULL',
  'SELECT "recipient_role exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='center_id'),
  'ALTER TABLE sms_logs ADD COLUMN center_id VARCHAR(36) NULL',
  'SELECT "center_id exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='center_name'),
  'ALTER TABLE sms_logs ADD COLUMN center_name VARCHAR(255) NULL',
  'SELECT "center_name exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='provider_message_id'),
  'ALTER TABLE sms_logs ADD COLUMN provider_message_id VARCHAR(255) NULL',
  'SELECT "provider_message_id exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='sms_logs' AND column_name='error'),
  'ALTER TABLE sms_logs ADD COLUMN error TEXT NULL',
  'SELECT "error exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='sms_timeout_seconds'),
  'ALTER TABLE settings ADD COLUMN sms_timeout_seconds INT NOT NULL DEFAULT 30',
  'SELECT "sms_timeout_seconds exists"'
); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE settings
SET sms_api_url='https://www.intouchsms.co.rw/api/sendsms/.json',
    sms_timeout_seconds=30
WHERE id=1;
SQL

echo "=== Replace sms_service.py with correct InTouch Basic Auth/form-data version ==="
cat > "$BACKEND/app/services/sms_service.py" <<'PY'
"""
Medisoft Guardian SMS Service
Provider: InTouch SMS Rwanda
Endpoint: https://www.intouchsms.co.rw/api/sendsms/.json

Important:
InTouch requires form-data + HTTP Basic Auth:
requests.post(url, data={recipients,message,sender}, auth=(username,password))
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session


DEFAULT_API_URL = "https://www.intouchsms.co.rw/api/sendsms/.json"


def _settings(db: Session) -> Dict[str, Any]:
    row = db.execute(text("SELECT * FROM settings WHERE id=1 LIMIT 1")).mappings().first()
    return dict(row or {})


def _table_columns(db: Session, table_name: str):
    rows = db.execute(text("""
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table
    """), {"table": table_name}).mappings().all()
    return {r["COLUMN_NAME"] for r in rows}


def _log_sms(
    db: Session,
    *,
    to_number: str,
    sender: str,
    recipient_role: str,
    center_id: Optional[str],
    center_name: Optional[str],
    message: str,
    status: str,
    provider_message_id: Optional[str] = None,
    error: Optional[str] = None,
):
    cols = _table_columns(db, "sms_logs")

    values = {
        "id": str(uuid.uuid4()),
        "to_number": to_number,
        "sender": sender,
        "recipient_role": recipient_role,
        "center_id": center_id,
        "center_name": center_name,
        "message": message,
        "status": status,
        "provider_message_id": provider_message_id,
        "error": error,
        "sent_at": datetime.utcnow(),
        "created_at": datetime.utcnow(),
    }

    insert_cols = [c for c in values.keys() if c in cols]
    placeholders = [f":{c}" for c in insert_cols]

    if not insert_cols:
        return

    db.execute(
        text(f"""
            INSERT INTO sms_logs ({", ".join(insert_cols)})
            VALUES ({", ".join(placeholders)})
        """),
        {c: values[c] for c in insert_cols},
    )
    db.commit()


def _is_success(status_code: int, body: str) -> bool:
    b = (body or "").lower()

    failure_words = [
        "exceed your account balance",
        "insufficient",
        "no credit",
        "failed",
        "failure",
        "error",
        "invalid",
        "missing",
        "unauthorized",
        "not allowed",
    ]

    if status_code < 200 or status_code >= 300:
        return False

    return not any(w in b for w in failure_words)


def send_sms(
    db: Session,
    to: str,
    message: str,
    recipient_role: str = "admin",
    center_id: Optional[str] = None,
    center_name: Optional[str] = None,
) -> Dict[str, Any]:
    s = _settings(db)

    api_url = s.get("sms_api_url") or DEFAULT_API_URL
    username = s.get("sms_username")
    password = s.get("sms_password")
    sender = s.get("sms_sender_id") or "MEDISOFT"
    timeout = int(s.get("sms_timeout_seconds") or 30)

    if not username or not password:
        result = {
            "success": False,
            "http_status": None,
            "gateway_response": "SMS username or password is missing",
            "reason": "SMS username or password is missing",
        }
        _log_sms(
            db,
            to_number=to,
            sender=sender,
            recipient_role=recipient_role,
            center_id=center_id,
            center_name=center_name,
            message=message,
            status="failed",
            error=result["reason"],
        )
        return result

    try:
        response = requests.post(
            api_url,
            data={
                "recipients": to,
                "message": message,
                "sender": sender,
            },
            auth=(username, password),
            timeout=timeout,
        )

        body = response.text or ""
        success = _is_success(response.status_code, body)

        _log_sms(
            db,
            to_number=to,
            sender=sender,
            recipient_role=recipient_role,
            center_id=center_id,
            center_name=center_name,
            message=message,
            status="sent" if success else "failed",
            provider_message_id=str(response.status_code),
            error=None if success else body,
        )

        return {
            "success": success,
            "http_status": response.status_code,
            "gateway_response": body,
            "reason": "SMS sent successfully" if success else body,
        }

    except Exception as e:
        err = str(e)
        _log_sms(
            db,
            to_number=to,
            sender=sender,
            recipient_role=recipient_role,
            center_id=center_id,
            center_name=center_name,
            message=message,
            status="failed",
            error=err,
        )
        return {
            "success": False,
            "http_status": None,
            "gateway_response": err,
            "reason": f"Could not reach SMS gateway: {err}",
        }


def send_test_sms(db: Session, to: str) -> Dict[str, Any]:
    return send_sms(
        db=db,
        to=to,
        message="[MEDISOFT] Test SMS — your InTouch gateway is configured correctly.",
        recipient_role="test",
        center_id=None,
        center_name="Settings Test",
    )
PY

echo "=== Restart backend ==="
sudo systemctl restart medisoft-guardian-v4-backend
sleep 3

echo "=== Test settings ==="
curl -s http://127.0.0.1:8004/api/v1/settings | jq '.sms_api_url, .sms_username, .sms_sender_id, .sms_timeout_seconds'

echo "=== Test SMS directly ==="
read -p "Enter phone number to test SMS: " TEST_PHONE

curl -s -X POST http://127.0.0.1:8004/api/v1/settings/sms/test \
  -H "Content-Type: application/json" \
  -d "{\"to\":\"$TEST_PHONE\"}" | jq

echo "=== Latest SMS log ==="
mysql -u root -p"$MYSQL_ROOT_PASSWORD" medisoft_guardian -e "
SELECT to_number, sender, recipient_role, status, provider_message_id, error, sent_at
FROM sms_logs
ORDER BY sent_at DESC
LIMIT 3\G
"

echo "DONE ✅"
echo "If you see account balance / credits error, integration is correct and only SMS credits are missing."
