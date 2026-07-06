-- Medisoft Guardian Cloud v1.2+ retention and incident history upgrade
-- Detailed monitoring data is kept short-term; incident_history preserves long-term operational history.

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @db = DATABASE();
SET @sql = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='detailed_retention_days') = 0,
  'ALTER TABLE settings ADD COLUMN detailed_retention_days INT NOT NULL DEFAULT 7',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='incident_history_retention_days') = 0,
  'ALTER TABLE settings ADD COLUMN incident_history_retention_days INT NOT NULL DEFAULT 365',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='retention_run_hour_utc') = 0,
  'ALTER TABLE settings ADD COLUMN retention_run_hour_utc INT NOT NULL DEFAULT 2',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='enable_retention_cleanup') = 0,
  'ALTER TABLE settings ADD COLUMN enable_retention_cleanup BOOLEAN NOT NULL DEFAULT TRUE',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
