"""Compute a 0-100 health score for a health center.

Inputs are a dict-like row with the following optional fields:
    status, internet_status, mysql_status,
    io_running, sql_running, seconds_behind,
    cpu_usage, ram_usage, disk_usage,
    last_seen (datetime or ISO string).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _up(value) -> bool:
    return str(value or "").upper() in ("YES", "ON", "RUNNING", "ONLINE", "OK")


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_time(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def compute_health_score(row: dict[str, Any]) -> int:
    score = 100.0

    # Reachability (30 pts total)
    if not _up(row.get("internet_status")):
        score -= 15
    if not _up(row.get("mysql_status")):
        score -= 15

    # Replication (30 pts total)
    if not _up(row.get("io_running")):
        score -= 15
    if not _up(row.get("sql_running")):
        score -= 15

    # Replication lag (up to 15 pts)
    lag = row.get("seconds_behind")
    if lag is not None:
        lag = _num(lag)
        if lag > 300:
            score -= 15
        elif lag > 60:
            score -= 8
        elif lag > 15:
            score -= 3

    # Resource pressure (up to 15 pts)
    for key, weight in (("cpu_usage", 5), ("ram_usage", 5), ("disk_usage", 5)):
        v = _num(row.get(key))
        if v >= 95:
            score -= weight
        elif v >= 85:
            score -= weight * 0.6

    # Heartbeat freshness (up to 10 pts)
    ls = _parse_time(row.get("last_seen"))
    if ls is None:
        score -= 10
    else:
        age = datetime.utcnow() - ls.replace(tzinfo=None)
        if age > timedelta(minutes=10):
            score -= 10
        elif age > timedelta(minutes=5):
            score -= 5

    return max(0, min(100, int(round(score))))
