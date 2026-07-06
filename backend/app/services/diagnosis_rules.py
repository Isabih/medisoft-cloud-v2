from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


def _up(v: Any) -> bool:
    return str(v or "").strip().lower() in {"yes", "on", "online", "running", "ok", "connected"}


def _num(v: Any, default: float = 0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _age_minutes(value: Any) -> float | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        return max(0, (datetime.utcnow() - dt.replace(tzinfo=None)).total_seconds() / 60)
    except Exception:
        return None


def diagnose_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic AI-style diagnosis used when external AI is not configured.

    This gives production-safe explanations, cause, first-aid, and supported dashboard actions.
    """
    center = ctx.get("center") or {}
    repl = ctx.get("replication") or {}
    extra = ctx.get("extra") or {}

    mysql = center.get("mysql_status") or extra.get("mysql_status")
    internet = center.get("internet_status") or extra.get("internet_status")
    cloud = center.get("cloud_connection") or extra.get("cloud_connection")
    io = repl.get("io_running") or extra.get("io_running")
    sql = repl.get("sql_running") or extra.get("sql_running")
    lag = repl.get("seconds_behind") if repl.get("seconds_behind") is not None else extra.get("seconds_behind")
    disk = center.get("disk_usage") if center.get("disk_usage") is not None else extra.get("disk_usage")
    ram = center.get("ram_usage") if center.get("ram_usage") is not None else extra.get("ram_usage")
    cpu = center.get("cpu_usage") if center.get("cpu_usage") is not None else extra.get("cpu_usage")
    last_seen = center.get("last_seen") or extra.get("last_seen")
    io_err = str(repl.get("last_io_error") or extra.get("last_io_error") or "")
    sql_err = str(repl.get("last_sql_error") or extra.get("last_sql_error") or "")

    supported_actions: List[dict] = []
    first_aid: List[str] = []

    age = _age_minutes(last_seen)
    if age is None or age > 3 or not _up(cloud):
        first_aid = [
            "Call the health centre contact and confirm the local server has power.",
            "Check internet/VPN on the local server.",
            "Check the local agent service: systemctl status medisoft-local-agent.",
            "Run journalctl -u medisoft-local-agent -f to see why it is not posting.",
            "After connectivity returns, the local agent should resend cached reports automatically.",
        ]
        return {
            "root_cause": "The local server is not reaching the cloud backend, so live data is stale or missing.",
            "fix_steps": first_aid,
            "severity": "critical",
            "auto_healable": False,
            "confidence": 0.9,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": supported_actions,
            "future_version_actions": ["Remote network reset", "Remote VPN re-authentication"],
        }

    if not _up(mysql):
        supported_actions.append({"key": "restart-mysql", "label": "Restart MySQL", "available_now": True})
        first_aid = [
            "Use First Aid → Restart MySQL from the dashboard.",
            "If it fails, open remote access and run: systemctl status mysql.",
            "Check disk space, because MySQL often stops when storage is full.",
            "Check MySQL error log: /var/log/mysql/error.log.",
        ]
        return {
            "root_cause": "Local MySQL is offline or not accepting connections.",
            "fix_steps": first_aid,
            "severity": "critical",
            "auto_healable": True,
            "confidence": 0.92,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": supported_actions,
            "future_version_actions": ["Automatic MySQL log collection"],
        }

    if _num(disk) >= 90:
        first_aid = [
            "Free disk space immediately; MySQL replication can stop when the disk is full.",
            "Remove old backups/logs only after confirming they are not needed.",
            "Check large tables and binary logs.",
            "After freeing space, restart MySQL and restart replica if SQL/IO is stopped.",
        ]
        supported_actions.extend([
            {"key": "restart-mysql", "label": "Restart MySQL", "available_now": True},
            {"key": "restart-replica", "label": "Restart Replica", "available_now": True},
        ])
        return {
            "root_cause": "Disk usage is critically high and may block MySQL writes or replication.",
            "fix_steps": first_aid,
            "severity": "critical",
            "auto_healable": False,
            "confidence": 0.85,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": supported_actions,
            "future_version_actions": ["Safe log cleanup from dashboard", "Backup pruning policy"],
        }

    if not _up(io):
        supported_actions.extend([
            {"key": "start-replica", "label": "Start Replica", "available_now": True},
            {"key": "restart-replica", "label": "Restart Replica", "available_now": True},
        ])
        if "connect" in io_err.lower() or "lost" in io_err.lower() or "timeout" in io_err.lower():
            cause = "Replica IO is stopped because the local server cannot reliably connect to the source/cloud MySQL host."
        else:
            cause = "Replica IO thread is stopped, so new changes are not being downloaded."
        first_aid = [
            "Use First Aid → Start Replica or Restart Replica from the dashboard.",
            "Check network/VPN between this centre and the replica source.",
            "Check MySQL replication user/password if the error mentions authentication.",
            "Check Last IO Error for the exact source connection problem.",
        ]
        return {
            "root_cause": cause,
            "fix_steps": first_aid,
            "severity": "critical",
            "auto_healable": True,
            "confidence": 0.88,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": supported_actions,
            "future_version_actions": ["Auto verify source host reachability"],
        }

    if not _up(sql):
        supported_actions.extend([
            {"key": "start-replica", "label": "Start Replica", "available_now": True},
            {"key": "restart-replica", "label": "Restart Replica", "available_now": True},
        ])
        lower_err = sql_err.lower()
        if "duplicate" in lower_err or "1062" in lower_err:
            cause = "Replica SQL stopped due to duplicate key conflict, usually caused by data already existing locally."
            extra_steps = [
                "Confirm the duplicate table/key from Last SQL Error before skipping anything.",
                "Use repair only after confirming the duplicate is safe to skip.",
            ]
        else:
            cause = "Replica SQL thread is stopped, so downloaded changes are not being applied."
            extra_steps = ["Check Last SQL Error before running any destructive repair."]
        first_aid = [
            "Use First Aid → Start Replica or Restart Replica from the dashboard.",
            *extra_steps,
            "If it repeats, inspect the exact failing table and transaction.",
        ]
        return {
            "root_cause": cause,
            "fix_steps": first_aid,
            "severity": "critical",
            "auto_healable": True,
            "confidence": 0.9,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": supported_actions,
            "future_version_actions": ["Guided duplicate-key repair wizard"],
        }

    if lag is not None and _num(lag) > 300:
        first_aid = [
            "Replication is running but delayed; check internet speed and server load.",
            "Check whether a large transaction or heavy report is running locally.",
            "If delay keeps growing, check MySQL processlist and disk IO.",
        ]
        return {
            "root_cause": "Replication is alive but lag is high, meaning the centre is behind the source database.",
            "fix_steps": first_aid,
            "severity": "warning",
            "auto_healable": False,
            "confidence": 0.78,
            "first_aid_actions": first_aid,
            "supported_dashboard_actions": [],
            "future_version_actions": ["Processlist analysis", "Replication throttle detection"],
        }

    if _num(cpu) > 90 or _num(ram) > 90:
        return {
            "root_cause": "The server is reachable but under high CPU/RAM pressure.",
            "fix_steps": [
                "Check running processes on the local server.",
                "Avoid heavy local reports during sync hours.",
                "Restart only the affected service if the server becomes slow.",
            ],
            "severity": "warning",
            "auto_healable": False,
            "confidence": 0.7,
            "first_aid_actions": ["Check top/htop", "Check MySQL processlist"],
            "supported_dashboard_actions": [],
            "future_version_actions": ["Remote process viewer"],
        }

    return {
        "root_cause": "No critical issue detected; local server, MySQL, IO, and SQL appear healthy.",
        "fix_steps": ["Continue monitoring.", "Review timeline if users report missing data."],
        "severity": "info",
        "auto_healable": False,
        "confidence": 0.95,
        "first_aid_actions": [],
        "supported_dashboard_actions": [],
        "future_version_actions": [],
    }
