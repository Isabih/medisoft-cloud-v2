"""
Medisoft Guardian retention service.

Production rule:
- Keep detailed monitoring/raw heartbeat data for a short window, default 7 days.
- Before deleting raw records, roll failures into compact incident_history rows.
- Keep incident history much longer so reports can answer: how many times did a centre/database go offline in 3 months?
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

DEFAULT_DETAILED_DAYS = 7
DEFAULT_INCIDENT_DAYS = 365

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS incident_history (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        unique_key VARCHAR(255) NOT NULL UNIQUE,
        center_id VARCHAR(64) NULL,
        foss_id VARCHAR(64) NULL,
        center_name VARCHAR(255) NULL,
        database_name VARCHAR(128) NULL,
        channel_name VARCHAR(128) NULL,
        source_table VARCHAR(128) NOT NULL,
        event_type VARCHAR(80) NOT NULL,
        severity VARCHAR(32) NOT NULL DEFAULT 'warning',
        started_at DATETIME NOT NULL,
        ended_at DATETIME NULL,
        duration_seconds BIGINT NULL,
        occurrence_count INT NOT NULL DEFAULT 1,
        root_cause TEXT NULL,
        recommended_fix TEXT NULL,
        first_aid_action VARCHAR(128) NULL,
        resolved BOOLEAN NOT NULL DEFAULT FALSE,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_incident_started (started_at),
        INDEX idx_incident_foss (foss_id),
        INDEX idx_incident_channel (channel_name),
        INDEX idx_incident_event (event_type),
        INDEX idx_incident_severity (severity)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS retention_runs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at DATETIME NULL,
        detailed_retention_days INT NOT NULL,
        incident_retention_days INT NOT NULL,
        incidents_upserted INT NOT NULL DEFAULT 0,
        rows_deleted INT NOT NULL DEFAULT 0,
        status VARCHAR(32) NOT NULL DEFAULT 'running',
        message TEXT NULL,
        INDEX idx_retention_started (started_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

SETTINGS_COLUMNS = {
    "detailed_retention_days": "INT NOT NULL DEFAULT 7",
    "incident_history_retention_days": "INT NOT NULL DEFAULT 365",
    "retention_run_hour_utc": "INT NOT NULL DEFAULT 2",
    "enable_retention_cleanup": "BOOLEAN NOT NULL DEFAULT TRUE",
}


def _table_exists(db, table_name: str) -> bool:
    return bool(db.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = :table
    """), {"table": table_name}).scalar() or 0)


def _column_exists(db, table_name: str, column_name: str) -> bool:
    return bool(db.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = :table AND column_name = :col
    """), {"table": table_name, "col": column_name}).scalar() or 0)


def ensure_retention_schema(db):
    for sql in SCHEMA_SQL:
        db.execute(text(sql))
    if _table_exists(db, "settings"):
        for col, ddl in SETTINGS_COLUMNS.items():
            if not _column_exists(db, "settings", col):
                db.execute(text(f"ALTER TABLE settings ADD COLUMN {col} {ddl}"))
    db.commit()


def get_retention_settings(db):
    ensure_retention_schema(db)
    detailed = DEFAULT_DETAILED_DAYS
    incident = DEFAULT_INCIDENT_DAYS
    enabled = True
    try:
        row = db.execute(text("""
            SELECT detailed_retention_days, incident_history_retention_days, enable_retention_cleanup
            FROM settings WHERE id = 1
        """)).mappings().first()
        if row:
            detailed = int(row.get("detailed_retention_days") or DEFAULT_DETAILED_DAYS)
            incident = int(row.get("incident_history_retention_days") or DEFAULT_INCIDENT_DAYS)
            enabled = bool(row.get("enable_retention_cleanup"))
    except Exception:
        logger.exception("Could not read retention settings; using defaults")
    return max(1, detailed), max(30, incident), enabled


def _exec_optional(db, sql: str, params: dict) -> int:
    """Execute SQL only when all referenced source tables exist; ignore schema drift safely."""
    try:
        res = db.execute(text(sql), params)
        return res.rowcount or 0
    except Exception as exc:
        logger.info("Retention optional SQL skipped/failed: %s", exc)
        return 0


def rollup_incidents(db, detailed_days: int) -> int:
    """Copy old detailed failures into compact incident_history rows before deleting raw data."""
    params = {"detailed_days": detailed_days}
    total = 0

    # Local/source agent reported failures.
    if _table_exists(db, "source_agent_reports"):
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('source:', foss_id, ':', COALESCE(channel_name,''), ':MYSQL_OFFLINE:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'source_agent_reports', 'MYSQL_OFFLINE',
                'critical', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Local MySQL was reported offline or unhealthy by the local agent.',
                'Check MySQL service, disk space, and local server resources. First Aid: restart MySQL if approved.',
                'restart_mysql', FALSE
            FROM source_agent_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(mysql_status,'')) NOT IN ('ok','yes','on','online','running','up','healthy')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('source:', foss_id, ':', COALESCE(channel_name,''), ':SQL_THREAD_OFF:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'source_agent_reports', 'SQL_THREAD_OFF',
                'critical', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Replica SQL thread was not running. Common causes: duplicate key, missing row, bad transaction, or manual stop.',
                'Open the SQL error, confirm the cause, then use First Aid restart replica/SQL only for this health centre channel.',
                'restart_replica', FALSE
            FROM source_agent_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(sql_running,'')) NOT IN ('yes','on','running')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('source:', foss_id, ':', COALESCE(channel_name,''), ':IO_THREAD_OFF:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'source_agent_reports', 'IO_THREAD_OFF',
                'critical', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Replica IO thread was not running or connecting. Common causes: VPN/network issue, wrong source credentials, or source MySQL unreachable.',
                'Check Tailscale connectivity, source MySQL port, and replica credentials. First Aid: restart replica/IO after network is healthy.',
                'restart_replica', FALSE
            FROM source_agent_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(io_running,'')) NOT IN ('yes','on','running')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('source:', foss_id, ':', COALESCE(channel_name,''), ':AGENT_CLOUD_CONNECTION:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'source_agent_reports', 'AGENT_CLOUD_CONNECTION_PROBLEM',
                'warning', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Local agent reported difficulty reaching the cloud backend.',
                'Check Tailscale route, backend API health, firewall, and DNS/IP configuration.',
                'refresh_status', FALSE
            FROM source_agent_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(cloud_connection,'')) NOT IN ('ok','yes','on','online','connected','healthy')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)

    # Cloud replica observations.
    if _table_exists(db, "cloud_replica_reports"):
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('cloud:', foss_id, ':', COALESCE(channel_name,''), ':SQL_THREAD_OFF:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'cloud_replica_reports', 'CLOUD_SQL_THREAD_OFF',
                'critical', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Cloud replica SQL thread was off for this channel.',
                'Review Last_SQL_Error on the cloud replica channel, then run a channel-specific safe repair only if approved.',
                'restart_cloud_channel', FALSE
            FROM cloud_replica_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(sql_running,'')) NOT IN ('yes','on','running')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, database_name, channel_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('cloud:', foss_id, ':', COALESCE(channel_name,''), ':IO_THREAD_OFF:', DATE(created_at)),
                foss_id, MAX(db_name), MAX(channel_name), 'cloud_replica_reports', 'CLOUD_IO_THREAD_OFF',
                'critical', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Cloud replica IO thread was off or connecting for this channel.',
                'Check VPN/Tailscale reachability to the source server and MySQL replica credentials.',
                'restart_cloud_channel', FALSE
            FROM cloud_replica_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(io_running,'')) NOT IN ('yes','on','running')
            GROUP BY foss_id, COALESCE(channel_name,''), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)

    # Local status reports / database comparison drift.
    if _table_exists(db, "local_status_reports"):
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, center_id, center_name, source_table, event_type,
                severity, started_at, ended_at, duration_seconds, occurrence_count,
                root_cause, recommended_fix, first_aid_action, resolved
            )
            SELECT
                CONCAT('local_status:', COALESCE(center_id, center_name), ':DATABASE_DRIFT:', DATE(created_at)),
                MAX(center_id), MAX(center_name), 'local_status_reports', 'DATABASE_DRIFT',
                'warning', MIN(created_at), MAX(created_at), TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                'Local-vs-cloud database comparison was not healthy.',
                'Check row counts, latest update time, replication filter, and whether the selected database/channel mapping is correct.',
                'run_diagnostics', FALSE
            FROM local_status_reports
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(compare_status,'')) NOT IN ('ok','healthy','matched','sync','synced')
            GROUP BY COALESCE(center_id, center_name), DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)

    # AI diagnosis rollup: preserve important diagnoses without keeping every raw row forever.
    if _table_exists(db, "hybrid_diagnoses"):
        total += _exec_optional(db, """
            INSERT INTO incident_history (
                unique_key, foss_id, source_table, event_type, severity, started_at, ended_at,
                duration_seconds, occurrence_count, root_cause, recommended_fix, resolved
            )
            SELECT
                CONCAT('diagnosis:', foss_id, ':', diagnosis_code, ':', DATE(created_at)),
                foss_id, 'hybrid_diagnoses', diagnosis_code, MAX(severity), MIN(created_at), MAX(created_at),
                TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)), COUNT(*),
                MAX(probable_cause), MAX(summary), FALSE
            FROM hybrid_diagnoses
            WHERE created_at < DATE_SUB(NOW(), INTERVAL :detailed_days DAY)
              AND LOWER(COALESCE(severity,'')) NOT IN ('info','healthy','ok')
            GROUP BY foss_id, diagnosis_code, DATE(created_at)
            ON DUPLICATE KEY UPDATE
                ended_at = VALUES(ended_at), occurrence_count = VALUES(occurrence_count), updated_at = NOW()
        """, params)

    return total


def purge_old_monitoring_data(force: bool = False):
    db = SessionLocal()
    run_id = None
    try:
        detailed_days, incident_days, enabled = get_retention_settings(db)
        if not enabled and not force:
            logger.info("Retention cleanup disabled in settings")
            return {"status": "disabled", "rows_deleted": 0, "incidents_upserted": 0}

        res = db.execute(text("""
            INSERT INTO retention_runs (detailed_retention_days, incident_retention_days)
            VALUES (:detailed, :incident)
        """), {"detailed": detailed_days, "incident": incident_days})
        db.commit()
        run_id = res.lastrowid

        incidents = rollup_incidents(db, detailed_days)
        deleted = 0

        purge_plan = [
            ("heartbeat_logs", "received_at"),
            ("database_metrics", "date"),
            ("replication_status", "checked_at"),
            ("source_agent_reports", "created_at"),
            ("cloud_replica_reports", "created_at"),
            ("local_status_reports", "created_at"),
            ("hybrid_diagnoses", "created_at"),
            ("replication_guardian_events", "created_at"),
        ]
        for table, col in purge_plan:
            if not _table_exists(db, table) or not _column_exists(db, table, col):
                continue
            if table == "database_metrics":
                sql = f"DELETE FROM {table} WHERE {col} < DATE_SUB(CURDATE(), INTERVAL :days DAY)"
            else:
                sql = f"DELETE FROM {table} WHERE {col} < DATE_SUB(NOW(), INTERVAL :days DAY)"
            deleted += _exec_optional(db, sql, {"days": detailed_days})

        # Keep resolved alerts only for detailed window, but active/unresolved alerts remain.
        if _table_exists(db, "alerts") and _column_exists(db, "alerts", "resolved_at"):
            deleted += _exec_optional(db, """
                DELETE FROM alerts
                WHERE resolved_at IS NOT NULL AND resolved_at < DATE_SUB(NOW(), INTERVAL :days DAY)
            """, {"days": detailed_days})

        # Keep long-term incidents according to incident retention.
        deleted += _exec_optional(db, """
            DELETE FROM incident_history
            WHERE started_at < DATE_SUB(NOW(), INTERVAL :days DAY)
        """, {"days": incident_days})

        db.execute(text("""
            UPDATE retention_runs
            SET finished_at = NOW(), status = 'success', rows_deleted = :deleted,
                incidents_upserted = :incidents,
                message = 'Detailed monitoring records purged after compact incident rollup.'
            WHERE id = :run_id
        """), {"deleted": deleted, "incidents": incidents, "run_id": run_id})
        db.commit()
        logger.info("Retention sweep success: deleted=%s incidents=%s", deleted, incidents)
        return {"status": "success", "rows_deleted": deleted, "incidents_upserted": incidents}
    except Exception as exc:
        db.rollback()
        logger.exception("Retention sweep failed")
        if run_id:
            try:
                db.execute(text("""
                    UPDATE retention_runs
                    SET finished_at = NOW(), status = 'failed', message = :msg
                    WHERE id = :run_id
                """), {"msg": str(exc)[:1000], "run_id": run_id})
                db.commit()
            except Exception:
                db.rollback()
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()


def start_retention_scheduler():
    db = SessionLocal()
    try:
        detailed_days, incident_days, enabled = get_retention_settings(db)
        hour = 2
        try:
            hour = int(db.execute(text("SELECT retention_run_hour_utc FROM settings WHERE id = 1")).scalar() or 2)
        except Exception:
            pass
    finally:
        db.close()

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(purge_old_monitoring_data, "cron", hour=hour, minute=0,
                  id="medisoft-retention", replace_existing=True)
    sched.start()
    logger.info("Retention scheduler started (daily %02d:00 UTC, detailed=%s days, incidents=%s days, enabled=%s)",
                hour, detailed_days, incident_days, enabled)
    return sched
