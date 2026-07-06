-- =========================================================
-- Medisoft v4 upgrades — Operational Audit Log
-- Run:  mysql -u root -p medisoft_central < backend/sql/upgrades_v4.sql
-- =========================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    action       VARCHAR(64)  NOT NULL,          -- e.g. agent.restart_mysql, sms.resend, backup.update
    target_type  VARCHAR(32)  NULL,              -- health_center | sms | backup | system
    target_id    VARCHAR(64)  NULL,              -- foss_id / sms_id / etc.
    target_name  VARCHAR(255) NULL,              -- friendly label (HC name, phone…)
    actor        VARCHAR(64)  NULL,              -- username / "system"
    outcome      ENUM('success','failure','pending') NOT NULL DEFAULT 'success',
    details      TEXT         NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created (created_at),
    INDEX idx_action  (action),
    INDEX idx_target  (target_type, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
