"""
Prometheus exporter for Medisoft. Grafana points its Prometheus
data source at this endpoint via prometheus.yml scrape config.

Mount in app.main:
    from app.routers.metrics_prometheus import router as metrics_router
    app.include_router(metrics_router)  # no /api/v1 prefix
"""
from fastapi import APIRouter, Response, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import get_db

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(db: Session = Depends(get_db)):
    lines = []

    def metric(name, help_text, mtype, samples):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        lines.extend(samples)

    # heartbeat freshness per center (seconds since last heartbeat)
    rows = db.execute(text(
        "SELECT id, name, "
        "  TIMESTAMPDIFF(SECOND, last_seen, NOW()) AS age_s, "
        "  COALESCE(cpu_usage,0) AS cpu, COALESCE(ram_usage,0) AS ram, "
        "  COALESCE(disk_usage,0) AS disk, status "
        "FROM health_centers"
    )).mappings().all()

    metric("medisoft_heartbeat_age_seconds", "Seconds since last heartbeat", "gauge",
           [f'medisoft_heartbeat_age_seconds{{center="{r["name"]}",id="{r["id"]}"}} {r["age_s"] or 0}'
            for r in rows])
    metric("medisoft_cpu_usage_percent", "CPU usage %", "gauge",
           [f'medisoft_cpu_usage_percent{{center="{r["name"]}"}} {r["cpu"]}' for r in rows])
    metric("medisoft_ram_usage_percent", "RAM usage %", "gauge",
           [f'medisoft_ram_usage_percent{{center="{r["name"]}"}} {r["ram"]}' for r in rows])
    metric("medisoft_disk_usage_percent", "Disk usage %", "gauge",
           [f'medisoft_disk_usage_percent{{center="{r["name"]}"}} {r["disk"]}' for r in rows])
    metric("medisoft_center_online", "1 if online, 0 otherwise", "gauge",
           [f'medisoft_center_online{{center="{r["name"]}"}} {1 if r["status"]=="online" else 0}'
            for r in rows])

    # replication lag
    rep = db.execute(text(
        "SELECT hc.name, rs.center_id, rs.io_running, rs.sql_running, "
        "       COALESCE(rs.seconds_behind, -1) AS lag "
        "FROM replication_status rs "
        "JOIN (SELECT center_id, MAX(checked_at) AS mx FROM replication_status GROUP BY center_id) m "
        "  ON m.center_id = rs.center_id AND m.mx = rs.checked_at "
        "JOIN health_centers hc ON hc.id = rs.center_id"
    )).mappings().all()
    metric("medisoft_replication_lag_seconds", "Replica seconds behind master", "gauge",
           [f'medisoft_replication_lag_seconds{{center="{r["name"]}"}} {r["lag"]}' for r in rep])
    metric("medisoft_replication_io_running", "1 if IO thread Yes", "gauge",
           [f'medisoft_replication_io_running{{center="{r["name"]}"}} {1 if r["io_running"]=="Yes" else 0}'
            for r in rep])
    metric("medisoft_replication_sql_running", "1 if SQL thread Yes", "gauge",
           [f'medisoft_replication_sql_running{{center="{r["name"]}"}} {1 if r["sql_running"]=="Yes" else 0}'
            for r in rep])



    # Database integrity / local-vs-cloud drift (v1.1)
    integ = db.execute(text(
        "SELECT hc.name, md.database_name, COALESCE(md.data_health_score,0) AS score, "
        "COALESCE(md.rows_difference,0) AS rows_diff, COALESCE(md.size_difference_mb,0) AS size_diff, "
        "COALESCE(md.drift_detected,0) AS drift "
        "FROM monitored_databases md JOIN health_centers hc ON hc.id=md.health_center_id"
    )).mappings().all()
    metric("medisoft_database_integrity_score", "Local vs cloud database integrity score", "gauge",
           [f'medisoft_database_integrity_score{{center="{r["name"]}",database="{r["database_name"]}"}} {r["score"]}' for r in integ])
    metric("medisoft_database_rows_difference", "Local rows minus cloud rows for monitored check table", "gauge",
           [f'medisoft_database_rows_difference{{center="{r["name"]}",database="{r["database_name"]}"}} {r["rows_diff"]}' for r in integ])
    metric("medisoft_database_size_difference_mb", "Local DB size minus cloud DB size in MB", "gauge",
           [f'medisoft_database_size_difference_mb{{center="{r["name"]}",database="{r["database_name"]}"}} {r["size_diff"]}' for r in integ])
    metric("medisoft_database_drift_detected", "1 if database drift is detected", "gauge",
           [f'medisoft_database_drift_detected{{center="{r["name"]}",database="{r["database_name"]}"}} {1 if r["drift"] else 0}' for r in integ])

    # SMS counters (last 24h)
    sms_today = db.execute(text(
        "SELECT status, COUNT(*) AS c FROM sms_logs "
        "WHERE sent_at > NOW() - INTERVAL 1 DAY GROUP BY status"
    )).mappings().all()
    metric("medisoft_sms_24h_total", "SMS counts (last 24h) per status", "counter",
           [f'medisoft_sms_24h_total{{status="{r["status"]}"}} {r["c"]}' for r in sms_today])

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
