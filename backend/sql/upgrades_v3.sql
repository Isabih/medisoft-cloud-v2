-- =========================================================
-- Medisoft v3 upgrades — Local Agent + Guardian integration
-- Run:  mysql -u root -p medisoft_central < backend/sql/upgrades_v3.sql
-- =========================================================

-- Rolling per-agent snapshot (latest replaces previous via PK = foss_id)
CREATE TABLE IF NOT EXISTS source_reports (
    foss_id              VARCHAR(64)   NOT NULL PRIMARY KEY,
    health_center_name   VARCHAR(255),
    db_name              VARCHAR(128),
    channel_name         VARCHAR(128),
    hostname             VARCHAR(128),
    mysql_status         VARCHAR(32),
    internet_status      VARCHAR(32),
    cloud_connection     VARCHAR(32),
    vpn_status           VARCHAR(32),
    cpu_usage            DECIMAL(5,2)  DEFAULT 0,
    ram_usage            DECIMAL(5,2)  DEFAULT 0,
    disk_usage           DECIMAL(5,2)  DEFAULT 0,
    database_size_mb     DECIMAL(12,2) DEFAULT 0,
    source_config_ok     TINYINT(1)    DEFAULT 0,
    connected_replicas   INT           DEFAULT 0,
    replica_hosts        TEXT,
    io_running           VARCHAR(8),
    sql_running          VARCHAR(8),
    local_row_count      BIGINT        DEFAULT 0,
    local_latest_time    DATETIME      NULL,
    sent_at              DATETIME      NULL,
    received_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_received_at (received_at),
    INDEX idx_health_center_name (health_center_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Queued remote actions (consumed by the agent on next poll)
CREATE TABLE IF NOT EXISTS agent_actions (
    id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    foss_id     VARCHAR(64)  NOT NULL,
    action      VARCHAR(64)  NOT NULL,
    params      TEXT         NULL,
    status      ENUM('pending','dispatched','done','failed') NOT NULL DEFAULT 'pending',
    requested_by VARCHAR(64) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dispatched_at DATETIME   NULL,
    result      TEXT         NULL,
    INDEX idx_foss_pending (foss_id, status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
