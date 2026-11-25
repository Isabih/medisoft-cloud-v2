"""Additive central_monitoring migration; preview by default."""
import argparse
from sqlalchemy import inspect, text
from app.core.config import settings
from app.core.database import engine

CREATES = {
    "sms_logs": "CREATE TABLE IF NOT EXISTS sms_logs (\n  id              VARCHAR(36) PRIMARY KEY,\n  to_number       VARCHAR(30) NOT NULL,\n  recipient_role  VARCHAR(20) NOT NULL DEFAULT 'admin',\n  center_id       VARCHAR(36) NULL,\n  center_name     VARCHAR(255) NULL,\n  message         TEXT NOT NULL,\n  status          VARCHAR(20) NOT NULL DEFAULT 'pending',\n  provider_message_id VARCHAR(100) NULL,\n  error           TEXT NULL,\n  sent_at         DATETIME DEFAULT CURRENT_TIMESTAMP,\n  delivered_at    DATETIME NULL,\n  INDEX idx_sms_sent_at (sent_at),\n  INDEX idx_sms_center  (center_id)\n)",
    "ai_diagnoses": "CREATE TABLE IF NOT EXISTS ai_diagnoses (\n  id          VARCHAR(36) PRIMARY KEY,\n  center_id   VARCHAR(36) NOT NULL,\n  fingerprint VARCHAR(64) NOT NULL,\n  root_cause  TEXT NOT NULL,\n  fix_steps   JSON NOT NULL,\n  severity    VARCHAR(20) NOT NULL,\n  auto_healable TINYINT(1) DEFAULT 0,\n  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,\n  INDEX idx_ai_center (center_id),\n  INDEX idx_ai_fp (fingerprint)\n)",
    "admin_notifications": "CREATE TABLE IF NOT EXISTS admin_notifications (\n  id           VARCHAR(36) PRIMARY KEY,\n  alert_id     VARCHAR(36) NULL,\n  channel      VARCHAR(20) NOT NULL,   \n  recipient    VARCHAR(120) NOT NULL,\n  status       VARCHAR(20) NOT NULL DEFAULT 'sent',\n  sent_at      DATETIME DEFAULT CURRENT_TIMESTAMP,\n  INDEX idx_an_alert (alert_id),\n  INDEX idx_an_sent  (sent_at)\n)",
    "source_reports": "CREATE TABLE IF NOT EXISTS source_reports (\n    foss_id              VARCHAR(64)   NOT NULL PRIMARY KEY,\n    health_center_name   VARCHAR(255),\n    db_name              VARCHAR(128),\n    channel_name         VARCHAR(128),\n    hostname             VARCHAR(128),\n    mysql_status         VARCHAR(32),\n    internet_status      VARCHAR(32),\n    cloud_connection     VARCHAR(32),\n    vpn_status           VARCHAR(32),\n    cpu_usage            DECIMAL(5,2)  DEFAULT 0,\n    ram_usage            DECIMAL(5,2)  DEFAULT 0,\n    disk_usage           DECIMAL(5,2)  DEFAULT 0,\n    database_size_mb     DECIMAL(12,2) DEFAULT 0,\n    source_config_ok     TINYINT(1)    DEFAULT 0,\n    connected_replicas   INT           DEFAULT 0,\n    replica_hosts        TEXT,\n    io_running           VARCHAR(8),\n    sql_running          VARCHAR(8),\n    local_row_count      BIGINT        DEFAULT 0,\n    local_latest_time    DATETIME      NULL,\n    sent_at              DATETIME      NULL,\n    received_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP\n                                       ON UPDATE CURRENT_TIMESTAMP,\n    INDEX idx_received_at (received_at),\n    INDEX idx_health_center_name (health_center_name)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "audit_logs": "CREATE TABLE IF NOT EXISTS audit_logs (\n    id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,\n    action       VARCHAR(64)  NOT NULL,          \n    target_type  VARCHAR(32)  NULL,              \n    target_id    VARCHAR(64)  NULL,              \n    target_name  VARCHAR(255) NULL,              \n    actor        VARCHAR(64)  NULL,              \n    outcome      ENUM('success','failure','pending') NOT NULL DEFAULT 'success',\n    details      TEXT         NULL,\n    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    INDEX idx_created (created_at),\n    INDEX idx_action  (action),\n    INDEX idx_target  (target_type, target_id)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "center_timeline_events": "CREATE TABLE IF NOT EXISTS center_timeline_events (\n    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n    center_id    VARCHAR(36) NOT NULL,\n    center_name  VARCHAR(255) NULL,\n    event_type   VARCHAR(50) NOT NULL,\n    severity     VARCHAR(20) NOT NULL DEFAULT 'info',\n    title        VARCHAR(255) NOT NULL,\n    message      TEXT NULL,\n    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    INDEX idx_tl_center_time (center_id, created_at),\n    INDEX idx_tl_type (event_type)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "agent_versions": "CREATE TABLE IF NOT EXISTS agent_versions (\n    id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,\n    version      VARCHAR(50) NOT NULL,\n    channel      VARCHAR(20) NOT NULL DEFAULT 'stable',\n    download_url VARCHAR(500) NULL,\n    sha256       VARCHAR(128) NULL,\n    notes        TEXT NULL,\n    is_current   TINYINT(1) NOT NULL DEFAULT 0,\n    released_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    UNIQUE KEY uq_agent_version (version, channel)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "database_integrity_checks": "CREATE TABLE IF NOT EXISTS database_integrity_checks (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n    center_id VARCHAR(36) NOT NULL,\n    center_name VARCHAR(255) NULL,\n    foss_id VARCHAR(64) NULL,\n    database_name VARCHAR(255) NOT NULL,\n    local_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,\n    cloud_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,\n    size_difference_mb DECIMAL(12,2) NOT NULL DEFAULT 0,\n    local_rows_count BIGINT NOT NULL DEFAULT 0,\n    cloud_rows_count BIGINT NOT NULL DEFAULT 0,\n    rows_difference BIGINT NOT NULL DEFAULT 0,\n    local_table_count INT NOT NULL DEFAULT 0,\n    cloud_table_count INT NOT NULL DEFAULT 0,\n    latest_local_time DATETIME NULL,\n    latest_cloud_time DATETIME NULL,\n    data_health_score TINYINT UNSIGNED NOT NULL DEFAULT 0,\n    integrity_status VARCHAR(30) NOT NULL DEFAULT 'unknown',\n    probable_cause TEXT NULL,\n    recommended_fix TEXT NULL,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    INDEX idx_dic_center_time (center_id, created_at),\n    INDEX idx_dic_db_time (database_name, created_at),\n    INDEX idx_dic_status (integrity_status)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "database_integrity_table_checks": "CREATE TABLE IF NOT EXISTS database_integrity_table_checks (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n    check_id BIGINT UNSIGNED NOT NULL,\n    table_name VARCHAR(255) NOT NULL,\n    local_rows_count BIGINT NOT NULL DEFAULT 0,\n    cloud_rows_count BIGINT NOT NULL DEFAULT 0,\n    rows_difference BIGINT NOT NULL DEFAULT 0,\n    local_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,\n    cloud_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,\n    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    INDEX idx_ditc_check (check_id),\n    INDEX idx_ditc_table (table_name)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "alert_incidents": "CREATE TABLE IF NOT EXISTS alert_incidents (\n            id VARCHAR(36) NOT NULL PRIMARY KEY,\n            health_center_id VARCHAR(64) NOT NULL,\n            health_center_name VARCHAR(255) NULL,\n            incident_type VARCHAR(50) NOT NULL,\n            active_key VARCHAR(160) NULL,\n            status VARCHAR(20) NOT NULL DEFAULT 'active',\n            first_detected_at DATETIME NOT NULL,\n            confirmed_at DATETIME NULL,\n            last_detected_at DATETIME NOT NULL,\n            resolved_at DATETIME NULL,\n            last_admin_sms_at DATETIME NULL,\n            last_hc_sms_at DATETIME NULL,\n            last_admin_email_at DATETIME NULL,\n            last_hc_email_at DATETIME NULL,\n            admin_sms_rounds INT NOT NULL DEFAULT 0,\n            hc_sms_rounds INT NOT NULL DEFAULT 0,\n            admin_email_rounds INT NOT NULL DEFAULT 0,\n            hc_email_rounds INT NOT NULL DEFAULT 0,\n            last_reason TEXT NULL,\n            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n            UNIQUE KEY uq_alert_incidents_active_key (active_key),\n            KEY idx_alert_incidents_center_status (health_center_id, incident_type, status)\n        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "alert_deliveries": "CREATE TABLE IF NOT EXISTS alert_deliveries (\n            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n            incident_id VARCHAR(36) NOT NULL,\n            health_center_id VARCHAR(64) NOT NULL,\n            incident_type VARCHAR(50) NOT NULL,\n            channel VARCHAR(20) NOT NULL,\n            audience VARCHAR(30) NOT NULL,\n            recipient VARCHAR(255) NOT NULL,\n            message TEXT NOT NULL,\n            success TINYINT(1) NOT NULL DEFAULT 0,\n            provider_response TEXT NULL,\n            attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\n            KEY idx_alert_deliveries_incident (incident_id),\n            KEY idx_alert_deliveries_center_time (health_center_id, attempted_at)\n        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
    "replication_io_incidents": "CREATE TABLE IF NOT EXISTS replication_io_incidents (\n          foss_id VARCHAR(64) PRIMARY KEY,\n          state VARCHAR(20) NOT NULL,\n          diagnosis_json LONGTEXT NOT NULL,\n          opened_at DATETIME NULL,\n          last_checked DATETIME NOT NULL,\n          healthy_streak INT NOT NULL DEFAULT 0,\n          recovery_pending TINYINT NOT NULL DEFAULT 0,\n          recovery_emailed_at DATETIME NULL\n        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
}
COLUMNS = {
    "settings": {
        "sms_provider": "VARCHAR(32)  NOT NULL DEFAULT 'intouch'",
        "sms_sender_id": "VARCHAR(64)  NULL",
        "sms_username": "VARCHAR(128) NULL",
        "sms_password": "VARCHAR(255) NULL",
        "sms_api_url": "VARCHAR(255) NOT NULL DEFAULT 'https://intouchsms.co.rw'",
        "admin_phone_numbers": "TEXT     NULL",
        "admin_emails": "TEXT NULL",
        "resend_api_key": "VARCHAR(255) NULL",
        "alert_email_from": "VARCHAR(255) NULL"
    },
    "sms_logs": {
        "sender": "VARCHAR(64) NULL AFTER to_number"
    },
    "health_centers": {
        "phone_role_1": "VARCHAR(50) NULL",
        "phone_role_2": "VARCHAR(50) NULL",
        "latitude": "DECIMAL(10,7) NULL",
        "longitude": "DECIMAL(10,7) NULL",
        "agent_version": "VARCHAR(50) NULL",
        "agent_last_report": "DATETIME NULL",
        "health_score": "TINYINT UNSIGNED NULL"
    },
    "source_reports": {
        "seconds_behind": "FLOAT NULL",
        "last_io_error": "TEXT NULL",
        "last_sql_error": "TEXT NULL",
        "agent_version": "VARCHAR(50) NULL",
        "local_table_count": "INT NOT NULL DEFAULT 0",
        "local_table_summary_json": "JSON NULL"
    },
    "monitored_databases": {
        "cloud_rows_count": "BIGINT NOT NULL DEFAULT 0",
        "cloud_size_mb": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "local_rows_count": "BIGINT NOT NULL DEFAULT 0",
        "local_size_mb": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "local_table_count": "INT NOT NULL DEFAULT 0",
        "cloud_table_count": "INT NOT NULL DEFAULT 0",
        "rows_difference": "BIGINT NOT NULL DEFAULT 0",
        "size_difference_mb": "DECIMAL(12,2) NOT NULL DEFAULT 0",
        "latest_local_time": "DATETIME NULL",
        "latest_cloud_time": "DATETIME NULL",
        "data_health_score": "TINYINT UNSIGNED NULL",
        "integrity_status": "VARCHAR(30) NOT NULL DEFAULT 'unknown'",
        "integrity_summary": "TEXT NULL",
        "last_integrity_check": "DATETIME NULL"
    }
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-cloud", action="store_true")
    args = parser.parse_args()
    if any((settings.auto_create_tables, settings.enable_background_collectors,
            settings.allow_runtime_schema_migrations)):
        raise SystemExit("Startup safety flags must all be false.")
    if engine.dialect.name != "mysql" or engine.url.database != "central_monitoring":
        raise SystemExit("Wrong database.")
    with engine.connect() as conn:
        if conn.execute(text("SELECT DATABASE()")).scalar() != "central_monitoring":
            raise SystemExit("Wrong active database.")
        inspector = inspect(conn)
        existing = set(inspector.get_table_names())
        plan = []
        for name, ddl in CREATES.items():
            if name not in existing:
                plan.append(ddl)
        for name, columns in COLUMNS.items():
            if name not in existing and name not in CREATES:
                raise SystemExit("Missing prerequisite: " + name)
            actual = {c["name"] for c in inspector.get_columns(name)} if name in existing else set()
            for col, definition in columns.items():
                if col not in actual:
                    plan.append(f"ALTER TABLE `{name}` ADD COLUMN `{col}` {definition}")
        for ddl in plan:
            print(ddl + ";")
        print("Planned statements:", len(plan))
        if not args.apply_cloud:
            print("Preview only.")
            return
        for ddl in plan:
            conn.execute(text(ddl))
        conn.commit()
        print("Applied additive migration. Remote action queue intentionally deferred.")

if __name__ == "__main__":
    main()
