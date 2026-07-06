from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.services.health_score import compute_health_score

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/centers-live")
def centers_live(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
            hc.id AS center_id,
            hc.name,
            hc.province,
            hc.district,
            hc.database_name,
            hc.foss_id,
            hc.status,
            hc.internet_status,
            hc.mysql_status,
            hc.cloud_connection,
            hc.last_seen,
            hc.cpu_usage,
            hc.ram_usage,
            hc.disk_usage,
            hc.risk_score,
            hc.latitude,
            hc.longitude,
            hc.agent_version,
            hc.health_score,
            hc.phone_number_1, hc.phone_contact_1, hc.phone_role_1,
            hc.phone_number_2, hc.phone_contact_2, hc.phone_role_2,
            hc.anydesk_id, hc.rustdesk_id,
            COALESCE(md.drift_detected, 0) AS drift_detected,
            md.data_health_score AS data_health_score,
            md.integrity_status AS integrity_status,
            md.local_rows_count AS local_rows_count,
            md.cloud_rows_count AS cloud_rows_count,
            md.rows_difference AS rows_difference,
            md.local_size_mb AS local_size_mb,
            md.cloud_size_mb AS cloud_size_mb,
            md.size_difference_mb AS size_difference_mb,
            md.local_table_count AS local_table_count,
            md.cloud_table_count AS cloud_table_count,
            md.latest_local_time AS latest_local_time,
            md.latest_cloud_time AS latest_cloud_time,
            md.integrity_summary AS integrity_summary,
            (
                SELECT rs.io_running
                FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC
                LIMIT 1
            ) AS replica_io,
            (
                SELECT rs.sql_running
                FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC
                LIMIT 1
            ) AS replica_sql,
            (
                SELECT rs.seconds_behind
                FROM replication_status rs
                WHERE rs.center_id = hc.id
                ORDER BY rs.checked_at DESC
                LIMIT 1
            ) AS seconds_behind,
            (
                SELECT DATE_FORMAT(b.created_at, '%Y-%m-%d %H:%i:%s')
                FROM backups b
                WHERE b.center_id = hc.id
                ORDER BY b.created_at DESC
                LIMIT 1
            ) AS last_backup,
            (
                SELECT b.status
                FROM backups b
                WHERE b.center_id = hc.id
                ORDER BY b.created_at DESC
                LIMIT 1
            ) AS backup_status,
            (
                SELECT COUNT(*)
                FROM alerts a
                WHERE a.center_id = hc.id
                  AND a.resolved_at IS NULL
            ) AS unresolved_alerts
        FROM health_centers hc
        LEFT JOIN monitored_databases md
            ON md.health_center_id = hc.id
           AND md.database_name = hc.database_name
        ORDER BY hc.name
    """)).mappings().all()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("health_score") is None:
            d["health_score"] = compute_health_score(d)
        result.append(d)
    return result


@router.get("/kpis")
def dashboard_kpis(db: Session = Depends(get_db)):
    total_centers = db.execute(text("SELECT COUNT(*) FROM health_centers")).scalar() or 0
    online = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE status = 'online'")).scalar() or 0
    partial = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE status = 'partial'")).scalar() or 0
    offline = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE status = 'offline'")).scalar() or 0

    critical_alerts = db.execute(text("""
        SELECT COUNT(*) FROM alerts
        WHERE severity = 'critical' AND resolved_at IS NULL
    """)).scalar() or 0

    warning_alerts = db.execute(text("""
        SELECT COUNT(*) FROM alerts
        WHERE severity = 'warning' AND resolved_at IS NULL
    """)).scalar() or 0

    high_lag_centers = db.execute(text("""
        SELECT COUNT(*) FROM (
          SELECT center_id, MAX(checked_at) mx FROM replication_status GROUP BY center_id
        ) latest
        JOIN replication_status rs ON rs.center_id=latest.center_id AND rs.checked_at=latest.mx
        WHERE COALESCE(rs.seconds_behind,0) >= 300
    """)).scalar() or 0
    high_ram_centers = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE COALESCE(ram_usage,0) >= 90")).scalar() or 0
    high_disk_centers = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE COALESCE(disk_usage,0) >= 90")).scalar() or 0
    high_drift_databases = db.execute(text("""
        SELECT COUNT(*) FROM monitored_databases
        WHERE COALESCE(drift_detected,0)=1 OR COALESCE(data_health_score,100)<90
    """)).scalar() or 0

    return {
        "total_centers": total_centers,
        "online": online,
        "partial": partial,
        "offline": offline,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "missing_backups": 0,
        "high_lag_centers": high_lag_centers,
        "high_ram_centers": high_ram_centers,
        "high_disk_centers": high_disk_centers,
        "high_drift_databases": high_drift_databases,
    }


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    total_centers = db.execute(text("SELECT COUNT(*) FROM health_centers")).scalar() or 0
    online_centers = db.execute(text("SELECT COUNT(*) FROM health_centers WHERE status='online' OR (internet_status='online' AND mysql_status='online')")).scalar() or 0
    offline_centers = max(total_centers - online_centers, 0)

    replication_healthy = db.execute(text("""
        SELECT COUNT(*)
        FROM (
            SELECT hc.id,
                   (SELECT rs.io_running FROM replication_status rs WHERE rs.center_id = hc.id ORDER BY rs.checked_at DESC LIMIT 1) AS io_running,
                   (SELECT rs.sql_running FROM replication_status rs WHERE rs.center_id = hc.id ORDER BY rs.checked_at DESC LIMIT 1) AS sql_running
            FROM health_centers hc
        ) x
        WHERE COALESCE(io_running, 'No') IN ('Yes','ON')
          AND COALESCE(sql_running, 'No') IN ('Yes','ON')
    """)).scalar() or 0
    replication_broken = max(total_centers - replication_healthy, 0)

    active_emergencies = db.execute(text("SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL AND severity='critical'")) .scalar() or 0
    backups_successful_today = db.execute(text("SELECT COUNT(*) FROM backups WHERE status='success' AND DATE(created_at)=CURRENT_DATE")).scalar() or 0
    guardian_auto_heals_today = db.execute(text("SELECT COUNT(*) FROM replication_guardian_events WHERE DATE(created_at)=CURRENT_DATE AND event_type IN ('heal','manual_repair') AND status IN ('success','started')")).scalar() or 0

    return {
        "total_centers": total_centers,
        "online_centers": online_centers,
        "offline_centers": offline_centers,
        "replication_healthy": replication_healthy,
        "replication_broken": replication_broken,
        "active_emergencies": active_emergencies,
        "backups_successful_today": backups_successful_today,
        "guardian_auto_heals_today": guardian_auto_heals_today,
    }


@router.get("/sync-activity")
def sync_activity(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT DATE(received_at) AS day, COUNT(*) AS heartbeat_count
        FROM heartbeat_logs
        WHERE received_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY DATE(received_at)
        ORDER BY day
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/alerts")
def dashboard_alerts(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT id, severity, type, type AS title, message,
               center_name AS health_center_name,
               NULL AS channel_name,
               CASE WHEN resolved_at IS NULL THEN 'active' ELSE 'resolved' END AS status,
               created_at
        FROM alerts
        ORDER BY resolved_at IS NULL DESC, created_at DESC
        LIMIT 100
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/unregistered-dbs")
def unregistered_dbs(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN (
            'mysql', 'information_schema', 'performance_schema', 'sys', 'central_monitoring'
        )
        AND schema_name NOT IN (
            SELECT database_name FROM health_centers
        )
        ORDER BY schema_name
    """)).mappings().all()

    return [dict(r) for r in rows]
