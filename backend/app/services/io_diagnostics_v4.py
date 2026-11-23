"""Evidence-based, read-only MySQL replication IO diagnostics and recovery email.

No replication commands or database modifications beyond the dedicated incident
metadata table. The source TCP probe runs from the cloud collector, not the agent.
"""
from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import socket
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import text

log = logging.getLogger(__name__)
FRESHNESS = timedelta(minutes=10)


def _fresh(local):
    if not local:
        return False
    stamp = local.get("created_at") or local.get("received_at")
    if isinstance(stamp, str):
        try:
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return False
    return isinstance(stamp, datetime) and timedelta(0) <= datetime.utcnow() - stamp <= FRESHNESS


def _state(value):
    v = str(value or "").strip().lower()
    if v in ("yes", "on", "online", "running", "connected", "ok"):
        return "online"
    if v in ("no", "off", "offline", "stopped", "failed", "disconnected"):
        return "offline"
    if v == "connecting":
        return "connecting"
    return "unknown"


def _probe(host, port):
    if not host or not isinstance(port, int) or not 1 <= port <= 65535:
        return {"status": "unknown", "detail": "Source host/port unavailable"}
    try:
        with socket.create_connection((host, port), timeout=2):
            return {"status": "reachable", "detail": "TCP handshake succeeded"}
    except (OSError, TimeoutError) as exc:
        # Do not put raw hostnames or exception internals into facility-facing UI.
        return {"status": "unreachable", "detail": type(exc).__name__}


def diagnose(repl, local=None, probe=None):
    """Pure decision function: distinguish direct evidence from possible causes."""
    raw = repl.get("raw") or {}
    io = _state(repl.get("io_running"))
    errno = raw.get("Last_IO_Errno") or raw.get("Last_IO_Error_Number")
    try:
        errno = int(errno or 0)
    except (ValueError, TypeError):
        errno = 0
    error = str(repl.get("last_io_error") or "")[:1500]
    agent_fresh = _fresh(local)
    checks = {
        "agent": "online" if agent_fresh else "unknown",
        "internet": _state(local.get("internet_status")) if agent_fresh else "unknown",
        "vpn": _state(local.get("vpn_status")) if agent_fresh else "unknown",
        "source_mysql": _state(local.get("mysql_status")) if agent_fresh else "unknown",
        "source_tcp": (probe or {}).get("status", "unknown"),
        "cloud_replica": "observed" if raw else "unknown",
    }
    code, confidence, reason, solution = (
        "unconfirmed", "unknown", "No verified root cause yet",
        "Review the replica IO error and collect fresh source and network checks."
    )
    if not raw:
        code, reason, solution = (
            "replica_status_unavailable", "Replica status query did not return usable evidence",
            "Check cloud MySQL permissions and whether the configured channel exists."
        )
    elif io == "online":
        code, confidence, reason, solution = (
            "io_running", "confirmed", "Replica IO thread is running",
            "No IO repair required. Verify SQL thread and replication lag separately."
        )
    elif errno in (1045,):
        code, confidence, reason, solution = (
            "authentication_rejected", "confirmed", "Source MySQL rejected replication authentication",
            "Verify replication account credentials and allowed source-host grants; do not reset the channel."
        )
    elif errno in (1044, 1227):
        code, confidence, reason, solution = (
            "replication_privilege_error", "confirmed", "MySQL reported insufficient privileges",
            "Review the replication account's required privileges and the source MySQL error log."
        )
    elif errno in (1236,):
        code, confidence, reason, solution = (
            "binlog_error", "confirmed", "MySQL reported a binary-log or replication-position error",
            "Preserve channel state and logs; escalate for controlled binlog/GTID investigation."
        )
    elif errno in (2003, 2005, 2006, 2013):
        code, confidence, reason, solution = (
            "mysql_connection_error", "confirmed", f"MySQL reported source connection error {errno}",
            "Verify source host, MySQL port, Tailscale path, firewall and source MySQL listener."
        )
    elif checks["source_tcp"] == "unreachable":
        code, confidence, reason, solution = (
            "source_tcp_unreachable", "confirmed", "Cloud cannot establish a TCP connection to the configured source MySQL port",
            "Check the source MySQL listener, firewall and VPN route. Inspect the IO error for the precise failure."
        )
    elif checks["vpn"] == "offline":
        code, confidence, reason, solution = (
            "vpn_reported_down", "likely", "Fresh source agent reports VPN disconnected",
            "Check Tailscale on both peers and verify reachability to the configured replication source."
        )
    elif checks["source_mysql"] == "offline":
        code, confidence, reason, solution = (
            "source_mysql_reported_down", "likely", "Fresh source agent reports MySQL stopped",
            "Check the source MySQL service and logs, then test the configured source port from cloud."
        )
    elif checks["internet"] == "offline":
        code, confidence, reason, solution = (
            "internet_reported_down", "likely", "Fresh source agent reports internet unavailable",
            "Check gateway and ISP; separately verify whether the Tailscale source path still works."
        )
    elif io == "connecting":
        code, confidence, reason, solution = (
            "connecting_unconfirmed", "unknown", "IO thread is connecting, but current checks do not establish why",
            "Inspect MySQL IO state/error, TLS, credentials, DNS and source-side connection logs."
        )
    elif io == "offline":
        code, confidence, reason, solution = (
            "io_off_unconfirmed", "unknown", "IO thread is off; no confirmed cause found",
            "Inspect Last_IO_Errno, Last_IO_Error and whether the channel was intentionally stopped."
        )
    return {
        "io_state": io, "cause_code": code, "confidence": confidence,
        "reason": reason, "suggested_solution": solution, "checks": checks,
        "mysql_error_number": errno or None, "mysql_error": error,
        "source_port": raw.get("Source_Port") or raw.get("Master_Port"),
        "io_state_detail": raw.get("Replica_IO_State") or raw.get("Slave_IO_State"),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def _ensure_table(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS replication_io_incidents (
          foss_id VARCHAR(64) PRIMARY KEY,
          state VARCHAR(20) NOT NULL,
          diagnosis_json LONGTEXT NOT NULL,
          opened_at DATETIME NULL,
          last_checked DATETIME NOT NULL,
          healthy_streak INT NOT NULL DEFAULT 0,
          recovery_pending TINYINT NOT NULL DEFAULT 0,
          recovery_emailed_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))


def _send_recovery(center, opened_at):
    recipients = [x.strip() for x in os.getenv("MEDISOFT_RECOVERY_EMAIL_TO", "").split(",") if x.strip()]
    host = os.getenv("MEDISOFT_SMTP_HOST", "")
    sender = os.getenv("MEDISOFT_SMTP_FROM", "")
    if not (recipients and host and sender):
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = "Medisoft replication IO recovered: " + str(center.get("name", "Health center"))[:100]
    msg.set_content(
        f"Facility: {center.get('name')}\nFOSAID: {center.get('foss_id')}\n"
        f"Channel: {center.get('replication_channel')}\n"
        f"Incident opened (UTC): {opened_at}\n"
        "Recovery: replica IO was observed running in two consecutive collector checks.\n"
        "Check SQL thread and lag separately before declaring full replication health.\n"
    )
    port = int(os.getenv("MEDISOFT_SMTP_PORT", "587"))
    timeout = 10
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    with smtp:
        if port != 465:
            smtp.starttls(context=ssl.create_default_context())
        user = os.getenv("MEDISOFT_SMTP_USER", "")
        password = os.getenv("MEDISOFT_SMTP_PASSWORD", "")
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
    return True


def record_diagnosis(db, center, repl, local=None):
    """Persist incident and send one recovery email after two confirmed healthy polls.

    Called after collector writes its report; no replica configuration is changed.
    """
    raw = repl.get("raw") or {}
    port = raw.get("Source_Port") or raw.get("Master_Port") or 3306
    try:
        port = int(port)
    except (ValueError, TypeError):
        port = 0
    # Probe only the host configured by MySQL, never user-supplied API input.
    probe = _probe(repl.get("source_host"), port) if raw and _state(repl.get("io_running")) != "online" else None
    diagnosis = diagnose(repl, local, probe)
    _ensure_table(db)
    foss_id = center["foss_id"]
    existing = db.execute(text(
        "SELECT * FROM replication_io_incidents WHERE foss_id=:f FOR UPDATE"
    ), {"f": foss_id}).mappings().first()
    now = datetime.utcnow()
    healthy = diagnosis["io_state"] == "online" and bool(raw)
    if not existing:
        # Baseline healthy states are not incidents and do not trigger emails.
        state = "healthy" if healthy else "active"
        db.execute(text("""
            INSERT INTO replication_io_incidents
            (foss_id, state, diagnosis_json, opened_at, last_checked, healthy_streak)
            VALUES (:f,:s,:d,:o,:n,:h)
        """), {"f": foss_id, "s": state, "d": json.dumps(diagnosis),
                "o": None if healthy else now, "n": now, "h": 1 if healthy else 0})
        return diagnosis
    streak = int(existing["healthy_streak"] or 0) + 1 if healthy else 0
    state = "healthy" if healthy and streak >= 2 else "recovering" if healthy else "active"
    pending = bool(existing["recovery_pending"])
    opened_at = existing["opened_at"]
    if state == "healthy" and existing["state"] in ("active", "recovering"):
        pending = bool(opened_at)
    if not healthy and existing["state"] == "healthy":
        opened_at = now
        pending = False
    db.execute(text("""
        UPDATE replication_io_incidents SET
          state=:s, diagnosis_json=:d, opened_at=:o, last_checked=:n,
          healthy_streak=:h, recovery_pending=:p
        WHERE foss_id=:f
    """), {"f": foss_id, "s": state, "d": json.dumps(diagnosis), "o": opened_at,
            "n": now, "h": streak, "p": int(pending)})
    if pending and state == "healthy":
        try:
            if _send_recovery(center, opened_at):
                db.execute(text("""
                    UPDATE replication_io_incidents SET recovery_pending=0,
                      recovery_emailed_at=:n WHERE foss_id=:f
                """), {"n": now, "f": foss_id})
        except Exception:
            log.exception("Recovery email failed for facility %s; will retry", foss_id)
    return diagnosis
