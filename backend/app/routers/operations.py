"""Operations Center — high-level, single-pane-of-glass metrics."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.health_score import compute_health_score

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/summary")
def operations_summary(db: Session = Depends(get_db)):
    def scalar(sql: str, **params) -> int:
        return int(db.execute(text(sql), params).scalar() or 0)

    total = scalar("SELECT COUNT(*) FROM health_centers")
    online = scalar(
        "SELECT COUNT(*) FROM health_centers "
        "WHERE status='online' OR (internet_status='online' AND mysql_status='online')"
    )
    offline = max(total - online, 0)

    # Replication threads (latest snapshot per center)
    repl_rows = db.execute(text(
        """
        SELECT
            (SELECT rs.io_running FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC LIMIT 1) AS io_running,
            (SELECT rs.sql_running FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC LIMIT 1) AS sql_running,
            (SELECT rs.seconds_behind FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC LIMIT 1) AS seconds_behind
        FROM health_centers hc
        """
    )).mappings().all()

    def is_up(v):
        return str(v or "").upper() in ("YES", "ON", "RUNNING")

    io_running = sum(1 for r in repl_rows if is_up(r["io_running"]))
    sql_running = sum(1 for r in repl_rows if is_up(r["sql_running"]))
    io_failed = max(total - io_running, 0)
    sql_failed = max(total - sql_running, 0)

    lags = [int(r["seconds_behind"]) for r in repl_rows if r["seconds_behind"] is not None]
    avg_lag = round(sum(lags) / len(lags), 1) if lags else 0

    alerts_today = scalar(
        "SELECT COUNT(*) FROM alerts WHERE DATE(created_at)=CURRENT_DATE"
    )
    critical_open = scalar(
        "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL AND severity='critical'"
    )
    dbs_monitored = scalar("SELECT COUNT(*) FROM monitored_databases")

    return {
        "total_centers": total,
        "online": online,
        "offline": offline,
        "sql_running": sql_running,
        "sql_failed": sql_failed,
        "io_running": io_running,
        "io_failed": io_failed,
        "alerts_today": alerts_today,
        "critical_open": critical_open,
        "databases_monitored": dbs_monitored,
        "avg_replication_lag_seconds": avg_lag,
    }


@router.get("/map")
def operations_map(db: Session = Depends(get_db)):
    """Geo positions + health status for the Rwanda map view."""
    rows = db.execute(text(
        """
        SELECT hc.id, hc.name, hc.province, hc.district,
               hc.latitude, hc.longitude, hc.status,
               hc.internet_status, hc.mysql_status,
               hc.cpu_usage, hc.ram_usage, hc.disk_usage,
               hc.last_seen, hc.health_score,
               (SELECT rs.io_running  FROM replication_status rs
                    WHERE rs.center_id=hc.id ORDER BY rs.checked_at DESC LIMIT 1) AS io_running,
               (SELECT rs.sql_running FROM replication_status rs
                    WHERE rs.center_id=hc.id ORDER BY rs.checked_at DESC LIMIT 1) AS sql_running,
               (SELECT rs.seconds_behind FROM replication_status rs
                    WHERE rs.center_id=hc.id ORDER BY rs.checked_at DESC LIMIT 1) AS seconds_behind
        FROM health_centers hc
        """
    )).mappings().all()

    out = []
    for r in rows:
        d = dict(r)
        score = d.get("health_score")
        if score is None:
            score = compute_health_score(d)
        d["health_score"] = int(score)
        if score >= 85:
            d["health_status"] = "healthy"
        elif score >= 60:
            d["health_status"] = "warning"
        elif score >= 30:
            d["health_status"] = "critical"
        else:
            d["health_status"] = "offline"
        out.append(d)
    return out
