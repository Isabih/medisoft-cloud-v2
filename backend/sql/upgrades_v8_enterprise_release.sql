-- =========================================================
-- Medisoft Guardian Cloud v1.0 Enterprise release schema
-- Run after all previous upgrades.
-- =========================================================

ALTER TABLE health_centers
  ADD COLUMN IF NOT EXISTS latitude DECIMAL(10,7) NULL,
  ADD COLUMN IF NOT EXISTS longitude DECIMAL(10,7) NULL,
  ADD COLUMN IF NOT EXISTS agent_version VARCHAR(50) NULL,
  ADD COLUMN IF NOT EXISTS agent_last_report DATETIME NULL,
  ADD COLUMN IF NOT EXISTS health_score TINYINT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS phone_role_1 VARCHAR(50) NULL,
  ADD COLUMN IF NOT EXISTS phone_role_2 VARCHAR(50) NULL;

ALTER TABLE settings
  ADD COLUMN IF NOT EXISTS admin_emails TEXT NULL,
  ADD COLUMN IF NOT EXISTS resend_api_key VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS alert_email_from VARCHAR(255) NULL;

ALTER TABLE source_reports
  ADD COLUMN IF NOT EXISTS seconds_behind FLOAT NULL,
  ADD COLUMN IF NOT EXISTS last_io_error TEXT NULL,
  ADD COLUMN IF NOT EXISTS last_sql_error TEXT NULL,
  ADD COLUMN IF NOT EXISTS agent_version VARCHAR(50) NULL;

CREATE TABLE IF NOT EXISTS center_timeline_events (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    center_id    VARCHAR(36) NOT NULL,
    center_name  VARCHAR(255) NULL,
    event_type   VARCHAR(50) NOT NULL,
    severity     VARCHAR(20) NOT NULL DEFAULT 'info',
    title        VARCHAR(255) NOT NULL,
    message      TEXT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tl_center_time (center_id, created_at),
    INDEX idx_tl_type (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_versions (
    id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    version      VARCHAR(50) NOT NULL,
    channel      VARCHAR(20) NOT NULL DEFAULT 'stable',
    download_url VARCHAR(500) NULL,
    sha256       VARCHAR(128) NULL,
    notes        TEXT NULL,
    is_current   TINYINT(1) NOT NULL DEFAULT 0,
    released_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_agent_version (version, channel)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO settings (id, day_close_time, auto_generate_reports, polling_interval, heartbeat_timeout_seconds, backup_check_time)
VALUES (1, '00:00:00', TRUE, 30, 180, '07:00:00')
ON DUPLICATE KEY UPDATE id=id;
