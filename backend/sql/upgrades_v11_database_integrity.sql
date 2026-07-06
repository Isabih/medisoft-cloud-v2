-- =========================================================
-- Medisoft Guardian Cloud v1.1 Enterprise
-- Database Integrity & Drift Health
-- Run after all previous upgrades.
-- =========================================================

ALTER TABLE source_reports
  ADD COLUMN IF NOT EXISTS local_table_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS local_table_summary_json JSON NULL;

ALTER TABLE monitored_databases
  ADD COLUMN IF NOT EXISTS cloud_rows_count BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cloud_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS local_rows_count BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS local_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS local_table_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cloud_table_count INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rows_difference BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS size_difference_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS latest_local_time DATETIME NULL,
  ADD COLUMN IF NOT EXISTS latest_cloud_time DATETIME NULL,
  ADD COLUMN IF NOT EXISTS data_health_score TINYINT UNSIGNED NULL,
  ADD COLUMN IF NOT EXISTS integrity_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS integrity_summary TEXT NULL,
  ADD COLUMN IF NOT EXISTS last_integrity_check DATETIME NULL;

CREATE TABLE IF NOT EXISTS database_integrity_checks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    center_id VARCHAR(36) NOT NULL,
    center_name VARCHAR(255) NULL,
    foss_id VARCHAR(64) NULL,
    database_name VARCHAR(255) NOT NULL,
    local_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
    cloud_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
    size_difference_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
    local_rows_count BIGINT NOT NULL DEFAULT 0,
    cloud_rows_count BIGINT NOT NULL DEFAULT 0,
    rows_difference BIGINT NOT NULL DEFAULT 0,
    local_table_count INT NOT NULL DEFAULT 0,
    cloud_table_count INT NOT NULL DEFAULT 0,
    latest_local_time DATETIME NULL,
    latest_cloud_time DATETIME NULL,
    data_health_score TINYINT UNSIGNED NOT NULL DEFAULT 0,
    integrity_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
    probable_cause TEXT NULL,
    recommended_fix TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dic_center_time (center_id, created_at),
    INDEX idx_dic_db_time (database_name, created_at),
    INDEX idx_dic_status (integrity_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS database_integrity_table_checks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    check_id BIGINT UNSIGNED NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    local_rows_count BIGINT NOT NULL DEFAULT 0,
    cloud_rows_count BIGINT NOT NULL DEFAULT 0,
    rows_difference BIGINT NOT NULL DEFAULT 0,
    local_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
    cloud_size_mb DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ditc_check (check_id),
    INDEX idx_ditc_table (table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
