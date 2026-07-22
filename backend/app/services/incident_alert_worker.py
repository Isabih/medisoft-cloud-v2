from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

import requests
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger("incident-alert-worker")

HC_MAX_ROUNDS = 3          # 2 phones x 3 rounds = 6 SMS maximum
SQL_ADMIN_MAX_ROUNDS = 5
REPEAT_AFTER = timedelta(hours=1)
IO_CONFIRM_AFTER = timedelta(minutes=10)
SQL_CONFIRM_AFTER = timedelta(minutes=2)
STALE_AFTER = timedelta(minutes=10)


def now() -> datetime:
    return datetime.utcnow()


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def is_on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return normalize(value) in {"1", "on", "yes", "true", "running", "online", "connected", "healthy", "ok", "up", "active"}


def is_off(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    return normalize(value) in {
        "0", "off", "offline", "false", "no", "down",
        "failed", "stopped", "unreachable", "disconnected",
        "not connected", "not_connected"
    }


def first(row: dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default


def parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def split_values(value: Any) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for item in re.split(r"[,;\n]+", str(value)):
        cleaned = item.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def clean_phone(value: Any) -> str:
    return re.sub(r"[^\d+]", "", str(value or ""))


def ensure_schema(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_incidents (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            health_center_id VARCHAR(64) NOT NULL,
            health_center_name VARCHAR(255) NULL,
            incident_type VARCHAR(50) NOT NULL,
            active_key VARCHAR(160) NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            first_detected_at DATETIME NOT NULL,
            confirmed_at DATETIME NULL,
            last_detected_at DATETIME NOT NULL,
            resolved_at DATETIME NULL,
            last_admin_sms_at DATETIME NULL,
            last_hc_sms_at DATETIME NULL,
            last_admin_email_at DATETIME NULL,
            last_hc_email_at DATETIME NULL,
            admin_sms_rounds INT NOT NULL DEFAULT 0,
            hc_sms_rounds INT NOT NULL DEFAULT 0,
            admin_email_rounds INT NOT NULL DEFAULT 0,
            hc_email_rounds INT NOT NULL DEFAULT 0,
            last_reason TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_alert_incidents_active_key (active_key),
            KEY idx_alert_incidents_center_status (health_center_id, incident_type, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_deliveries (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            incident_id VARCHAR(36) NOT NULL,
            health_center_id VARCHAR(64) NOT NULL,
            incident_type VARCHAR(50) NOT NULL,
            channel VARCHAR(20) NOT NULL,
            audience VARCHAR(30) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            success TINYINT(1) NOT NULL DEFAULT 0,
            provider_response TEXT NULL,
            attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_alert_deliveries_incident (incident_id),
            KEY idx_alert_deliveries_center_time (health_center_id, attempted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    db.commit()


def settings(db: Session) -> dict[str, Any]:
    row = db.execute(text("SELECT * FROM settings ORDER BY id LIMIT 1")).mappings().first()
    return dict(row or {})


def sms_success(result: Any) -> bool:
    if result is True:
        return True
    if isinstance(result, dict):
        if result.get("success") is True:
            return True
        return normalize(result.get("status")) in {"sent", "success", "ok"}
    return False


def send_sms_existing(db: Session, recipient: str, message: str) -> tuple[bool, str]:
    try:
        from app.services.sms_service import send_sms
    except Exception as exc:
        return False, f"Could not import sms_service.send_sms: {exc}"

    attempts = [
        lambda: send_sms(db, recipient, message),
        lambda: send_sms(recipient, message, db),
        lambda: send_sms(db=db, to_number=recipient, message=message),
        lambda: send_sms(db=db, recipient=recipient, message=message),
        lambda: send_sms(to_number=recipient, message=message, db=db),
        lambda: send_sms(phone_number=recipient, message=message, db=db),
    ]
    last_error = ""
    for attempt in attempts:
        try:
            result = attempt()
            return sms_success(result), json.dumps(result, default=str)
        except TypeError as exc:
            last_error = str(exc)
        except Exception as exc:
            return False, str(exc)
    return False, f"Unsupported send_sms signature: {last_error}"


def send_email_resend(cfg: dict[str, Any], recipient: str, subject: str, body: str) -> tuple[bool, str]:
    api_key = str(cfg.get("resend_api_key") or "").strip()
    sender = str(cfg.get("alert_email_from") or "").strip()
    if not api_key or not sender:
        return False, "Resend API key or sender email is missing"
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": sender, "to": [recipient], "subject": subject, "text": body},
            timeout=30,
        )
        return response.ok, response.text[:2000]
    except Exception as exc:
        return False, str(exc)


def record_delivery(db: Session, incident: dict[str, Any], channel: str, audience: str, recipient: str, message: str, success: bool, response: str) -> None:
    db.execute(text("""
        INSERT INTO alert_deliveries (
            incident_id, health_center_id, incident_type, channel,
            audience, recipient, message, success, provider_response
        ) VALUES (
            :incident_id, :health_center_id, :incident_type, :channel,
            :audience, :recipient, :message, :success, :provider_response
        )
    """), {
        "incident_id": incident["id"], "health_center_id": incident["health_center_id"],
        "incident_type": incident["incident_type"], "channel": channel,
        "audience": audience, "recipient": recipient, "message": message,
        "success": 1 if success else 0, "provider_response": response,
    })


def deliver_sms(db: Session, incident: dict[str, Any], recipients: list[str], message: str, audience: str) -> bool:
    any_success = False
    for recipient in recipients:
        phone = clean_phone(recipient)
        if not phone:
            continue
        success, response = send_sms_existing(db, phone, message)
        record_delivery(db, incident, "sms", audience, phone, message, success, response)
        any_success = any_success or success
    db.commit()
    return any_success


def deliver_email(db: Session, cfg: dict[str, Any], incident: dict[str, Any], recipients: list[str], subject: str, message: str, audience: str) -> bool:
    any_success = False
    for recipient in recipients:
        email = recipient.strip()
        if not email:
            continue
        success, response = send_email_resend(cfg, email, subject, message)
        record_delivery(db, incident, "email", audience, email, message, success, response)
        any_success = any_success or success
    db.commit()
    return any_success


def get_incident(db: Session, hc_id: str, hc_name: str, incident_type: str, reason: str) -> dict[str, Any]:
    active_key = f"{hc_id}:{incident_type}"
    row = db.execute(text("SELECT * FROM alert_incidents WHERE active_key=:active_key LIMIT 1 FOR UPDATE"), {"active_key": active_key}).mappings().first()
    current = now()
    if row:
        db.execute(text("UPDATE alert_incidents SET last_detected_at=:t, last_reason=:r WHERE id=:id"), {"t": current, "r": reason, "id": row["id"]})
        db.commit()
        return dict(db.execute(text("SELECT * FROM alert_incidents WHERE id=:id"), {"id": row["id"]}).mappings().first())

    incident_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO alert_incidents (
            id, health_center_id, health_center_name, incident_type,
            active_key, status, first_detected_at, last_detected_at, last_reason
        ) VALUES (
            :id, :hc, :name, :type, :active_key, 'active', :t, :t, :reason
        )
    """), {"id": incident_id, "hc": hc_id, "name": hc_name, "type": incident_type, "active_key": active_key, "t": current, "reason": reason})
    db.commit()
    return dict(db.execute(text("SELECT * FROM alert_incidents WHERE id=:id"), {"id": incident_id}).mappings().first())


def update_incident(db: Session, incident_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {"confirmed_at", "last_admin_sms_at", "last_hc_sms_at", "last_admin_email_at", "last_hc_email_at", "admin_sms_rounds", "hc_sms_rounds", "admin_email_rounds", "hc_email_rounds", "last_reason"}
    chosen = {k: v for k, v in fields.items() if k in allowed}
    if chosen:
        assignments = ", ".join(f"{key}=:{key}" for key in chosen)
        chosen["id"] = incident_id
        db.execute(text(f"UPDATE alert_incidents SET {assignments} WHERE id=:id"), chosen)
        db.commit()
    return dict(db.execute(text("SELECT * FROM alert_incidents WHERE id=:id"), {"id": incident_id}).mappings().first())


def resolve_type(db: Session, hc_id: str, incident_type: str) -> None:
    db.execute(text("""
        UPDATE alert_incidents
        SET status='resolved', resolved_at=:t, active_key=NULL
        WHERE health_center_id=:hc AND incident_type=:type AND status='active'
    """), {"t": now(), "hc": hc_id, "type": incident_type})
    db.commit()


def resolve_other_incidents(db: Session, hc_id: str, keep_type: str) -> None:
    db.execute(text("""
        UPDATE alert_incidents
        SET status='resolved', resolved_at=:t, active_key=NULL
        WHERE health_center_id=:hc AND status='active' AND incident_type<>:keep
    """), {"t": now(), "hc": hc_id, "keep": keep_type})
    db.commit()


def elapsed(last_sent: Any, interval: timedelta) -> bool:
    parsed = parse_dt(last_sent)
    return parsed is None or now() - parsed >= interval


def confirmed(incident: dict[str, Any], wait: timedelta) -> bool:
    first_detected = parse_dt(incident.get("first_detected_at")) or now()
    return now() - first_detected >= wait


def hc_contacts(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    phones = [
        clean_phone(first(row, ["phone_number_1", "phone1", "primary_phone"])),
        clean_phone(first(row, ["phone_number_2", "phone2", "secondary_phone"])),
    ]
    emails = [
        str(first(row, ["email_1", "email1", "primary_email"], "") or "").strip(),
        str(first(row, ["email_2", "email2", "secondary_email"], "") or "").strip(),
    ]
    return [v for v in phones if v], [v for v in emails if v]


def admin_contacts(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    return split_values(cfg.get("admin_phone_numbers") or cfg.get("admin_numbers")), split_values(cfg.get("admin_emails"))


def state_from_row(row: dict[str, Any]) -> dict[str, Any]:
    internet_raw = first(row, ["internet_status", "internet_online", "network_status", "connectivity_status"])
    io_raw = first(row, ["io_status", "io_running", "slave_io_running", "replica_io_running", "replication_io_status"])
    sql_raw = first(row, ["sql_status", "sql_running", "slave_sql_running", "replica_sql_running", "replication_sql_status"])
    mysql_raw = first(row, ["mysql_status", "database_status"])
    server_raw = first(row, ["cloud_connection"])
    last_seen = parse_dt(first(row, ["last_seen", "agent_last_report", "last_report_at", "updated_at", "last_checked"]))
    stale = bool(last_seen and now() - last_seen > STALE_AFTER)
    internet_off = is_off(internet_raw) or stale
    io_off = is_off(io_raw)
    sql_off = is_off(sql_raw)
    server_unreachable = stale or internet_off or is_off(server_raw) or is_off(mysql_raw)
    reason = str(first(row, ["last_error", "replication_error", "last_io_error", "last_sql_error", "error_message"], "") or "").strip()
    return {"internet_off": internet_off, "io_off": io_off, "sql_off": sql_off, "server_unreachable": server_unreachable, "last_seen": last_seen, "reason": reason}


def admin_detail(row: dict[str, Any], state: dict[str, Any]) -> str:
    parts = [
        f"Health center: {row.get('name') or row.get('id')}",
        f"FOSS ID: {row.get('foss_id') or 'unknown'}",
        f"Database: {row.get('database_name') or 'unknown'}",
        f"Channel: {row.get('replication_channel') or 'unknown'}",
        f"Host: {row.get('source_host') or 'unknown'}",
        f"Internet: {'OFF' if state['internet_off'] else 'ON'}",
        f"MySQL: {row.get('mysql_status') or 'unknown'}",
        f"Cloud: {row.get('cloud_connection') or 'unknown'}",
        f"IO: {'OFF' if state['io_off'] else 'ON'}",
        f"SQL: {'OFF' if state['sql_off'] else 'ON'}",
    ]
    if state.get("last_seen"):
        parts.append(f"Last seen: {state['last_seen']}")
    if state.get("reason"):
        parts.append(f"Reason: {state['reason']}")
    return ". ".join(parts)


def process_center(db: Session, cfg: dict[str, Any], row: dict[str, Any]) -> None:
    hc_id = str(row.get("id"))
    hc_name = str(row.get("name") or hc_id)
    state = state_from_row(row)
    admin_phones, admin_emails = admin_contacts(cfg)
    hc_phones, hc_emails = hc_contacts(row)
    detail = admin_detail(row, state)

    # Priority 1: internet OFF + IO OFF, one alert only to each recipient.
    if state["internet_off"] and state["io_off"]:
        resolve_other_incidents(db, hc_id, "INTERNET_IO_OFF")
        incident = get_incident(db, hc_id, hc_name, "INTERNET_IO_OFF", detail)
        admin_message = f"MEDISOFT CRITICAL: {hc_name} internet and replication IO are OFF. {detail}"
        hc_message = "MEDISOFT ALERT: Your server is not communicating with Medisoft Cloud. Please reconnect the server and check internet, server power, MySQL, and network equipment."

        if int(incident["admin_sms_rounds"] or 0) < 1:
            if deliver_sms(db, incident, admin_phones, admin_message, "admin"):
                incident = update_incident(db, incident["id"], admin_sms_rounds=1, last_admin_sms_at=now())
            if deliver_email(db, cfg, incident, admin_emails, f"Medisoft critical alert - {hc_name}", admin_message, "admin"):
                incident = update_incident(db, incident["id"], admin_email_rounds=1, last_admin_email_at=now())

        if int(incident["hc_sms_rounds"] or 0) < 1:
            if deliver_sms(db, incident, hc_phones, hc_message, "health_center"):
                incident = update_incident(db, incident["id"], hc_sms_rounds=1, last_hc_sms_at=now())
            if hc_emails and deliver_email(db, cfg, incident, hc_emails, f"Medisoft connectivity alert - {hc_name}", hc_message, "health_center"):
                update_incident(db, incident["id"], hc_email_rounds=1, last_hc_email_at=now())
        return

    resolve_type(db, hc_id, "INTERNET_IO_OFF")

    # Priority 2: SQL OFF, admin every hour, maximum 5 rounds.
    if state["sql_off"]:
        incident = get_incident(db, hc_id, hc_name, "SQL_OFF", detail)
        if confirmed(incident, SQL_CONFIRM_AFTER):
            round_no = int(incident["admin_sms_rounds"] or 0) + 1
            message = f"MEDISOFT SQL ALERT {round_no}/{SQL_ADMIN_MAX_ROUNDS}: {hc_name} SQL thread is OFF. {detail}"
            if int(incident["admin_sms_rounds"] or 0) < SQL_ADMIN_MAX_ROUNDS and elapsed(incident.get("last_admin_sms_at"), REPEAT_AFTER):
                if deliver_sms(db, incident, admin_phones, message, "admin"):
                    incident = update_incident(db, incident["id"], admin_sms_rounds=round_no, last_admin_sms_at=now(), confirmed_at=incident.get("confirmed_at") or now())
                if deliver_email(db, cfg, incident, admin_emails, f"Medisoft SQL alert {round_no}/{SQL_ADMIN_MAX_ROUNDS} - {hc_name}", message, "admin"):
                    update_incident(db, incident["id"], admin_email_rounds=min(int(incident.get("admin_email_rounds") or 0) + 1, SQL_ADMIN_MAX_ROUNDS), last_admin_email_at=now())
    else:
        resolve_type(db, hc_id, "SQL_OFF")

    # Priority 3: IO OFF while internet ON, admin once after 10 minutes.
    if state["io_off"] and not state["internet_off"]:
        incident = get_incident(db, hc_id, hc_name, "IO_OFF", detail)
        if confirmed(incident, IO_CONFIRM_AFTER) and int(incident["admin_sms_rounds"] or 0) < 1:
            message = f"MEDISOFT IO ALERT: {hc_name} replication IO has been OFF for at least 10 minutes. {detail}"
            if deliver_sms(db, incident, admin_phones, message, "admin"):
                incident = update_incident(db, incident["id"], admin_sms_rounds=1, last_admin_sms_at=now(), confirmed_at=incident.get("confirmed_at") or now())
            if deliver_email(db, cfg, incident, admin_emails, f"Medisoft IO alert - {hc_name}", message, "admin"):
                update_incident(db, incident["id"], admin_email_rounds=1, last_admin_email_at=now())
    else:
        resolve_type(db, hc_id, "IO_OFF")

    # Priority 4: general server outage, 3 rounds to two HC phones = 6 SMS max.
    if state["server_unreachable"]:
        incident = get_incident(db, hc_id, hc_name, "SERVER_UNREACHABLE", detail)
        if int(incident["hc_sms_rounds"] or 0) < HC_MAX_ROUNDS and elapsed(incident.get("last_hc_sms_at"), REPEAT_AFTER):
            round_no = int(incident["hc_sms_rounds"] or 0) + 1
            hc_message = f"MEDISOFT ALERT {round_no}/{HC_MAX_ROUNDS}: Your health-center server is unreachable. Please check internet, server power, MySQL service, and network equipment."
            admin_message = f"MEDISOFT SERVER ALERT {round_no}/{HC_MAX_ROUNDS}: {hc_name} is unreachable. {detail}"
            if deliver_sms(db, incident, hc_phones, hc_message, "health_center"):
                incident = update_incident(db, incident["id"], hc_sms_rounds=round_no, last_hc_sms_at=now())
            if deliver_sms(db, incident, admin_phones, admin_message, "admin"):
                incident = update_incident(db, incident["id"], admin_sms_rounds=min(int(incident.get("admin_sms_rounds") or 0) + 1, HC_MAX_ROUNDS), last_admin_sms_at=now())
            if deliver_email(db, cfg, incident, admin_emails, f"Medisoft server alert {round_no}/{HC_MAX_ROUNDS} - {hc_name}", admin_message, "admin"):
                incident = update_incident(db, incident["id"], admin_email_rounds=min(int(incident.get("admin_email_rounds") or 0) + 1, HC_MAX_ROUNDS), last_admin_email_at=now())
            if hc_emails and deliver_email(db, cfg, incident, hc_emails, f"Medisoft connectivity alert {round_no}/{HC_MAX_ROUNDS}", hc_message, "health_center"):
                update_incident(db, incident["id"], hc_email_rounds=min(int(incident.get("hc_email_rounds") or 0) + 1, HC_MAX_ROUNDS), last_hc_email_at=now())
    else:
        resolve_type(db, hc_id, "SERVER_UNREACHABLE")


def run_once() -> None:
    db = SessionLocal()
    try:
        ensure_schema(db)
        cfg = settings(db)
        rows = db.execute(text("SELECT * FROM health_centers")).mappings().all()
        LOG.info("Evaluating %d registered health centers", len(rows))
        for raw in rows:
            try:
                process_center(db, cfg, dict(raw))
            except Exception:
                db.rollback()
                LOG.exception("Alert evaluation failed for health center %s", raw.get("name") or raw.get("id"))
    finally:
        db.close()


if __name__ == "__main__":
    run_once()
