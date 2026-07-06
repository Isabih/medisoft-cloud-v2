-- Upgrades v7: Operations Center, per-center timeline, agent versioning,
-- Rwanda geo coordinates, contact role labels (Titulaire / Comptable / ...).

-- ------------------------------------------------------------------
-- 1. Health center extensions
-- ------------------------------------------------------------------
ALTER TABLE health_centers
    ADD COLUMN IF NOT EXISTS phone_role_1 VARCHAR(50) NULL AFTER phone_contact_1,
    ADD COLUMN IF NOT EXISTS phone_role_2 VARCHAR(50) NULL AFTER phone_contact_2,
    ADD COLUMN IF NOT EXISTS latitude  DECIMAL(10, 7) NULL,
    ADD COLUMN IF NOT EXISTS longitude DECIMAL(10, 7) NULL,
    ADD COLUMN IF NOT EXISTS agent_version VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS agent_last_report DATETIME NULL,
    ADD COLUMN IF NOT EXISTS health_score TINYINT UNSIGNED NULL;

-- ------------------------------------------------------------------
-- 2. Timeline events (per health center)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS center_timeline_events (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    center_id    VARCHAR(36) NOT NULL,
    center_name  VARCHAR(255) NULL,
    event_type   VARCHAR(50) NOT NULL,      -- heartbeat|replication|sms|repair|alert|note
    severity     VARCHAR(20) NOT NULL DEFAULT 'info',  -- info|warning|critical|success
    title        VARCHAR(255) NOT NULL,
    message      TEXT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tl_center_time (center_id, created_at),
    INDEX idx_tl_type (event_type)
);

-- ------------------------------------------------------------------
-- 3. Agent version registry (cloud-managed release channel)
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_versions (
    id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    version      VARCHAR(50) NOT NULL,
    channel      VARCHAR(20) NOT NULL DEFAULT 'stable',   -- stable|beta
    download_url VARCHAR(500) NULL,
    sha256       VARCHAR(128) NULL,
    notes        TEXT NULL,
    is_current   TINYINT(1) NOT NULL DEFAULT 0,
    released_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_agent_version (version, channel)
);
