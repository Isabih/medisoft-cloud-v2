-- ============================================================
-- Medisoft Cloud — Upgrades v2
-- Run with: mysql -u root -p medisoft_central < upgrades_v2.sql
-- ============================================================

-- 1. SMS logs
CREATE TABLE IF NOT EXISTS sms_logs (
  id              VARCHAR(36) PRIMARY KEY,
  to_number       VARCHAR(30) NOT NULL,
  recipient_role  VARCHAR(20) NOT NULL DEFAULT 'admin',
  center_id       VARCHAR(36) NULL,
  center_name     VARCHAR(255) NULL,
  message         TEXT NOT NULL,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  provider_message_id VARCHAR(100) NULL,
  error           TEXT NULL,
  sent_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
  delivered_at    DATETIME NULL,
  INDEX idx_sms_sent_at (sent_at),
  INDEX idx_sms_center  (center_id)
);

-- 2. AI diagnosis cache (avoid spamming the LLM)
CREATE TABLE IF NOT EXISTS ai_diagnoses (
  id          VARCHAR(36) PRIMARY KEY,
  center_id   VARCHAR(36) NOT NULL,
  fingerprint VARCHAR(64) NOT NULL,
  root_cause  TEXT NOT NULL,
  fix_steps   JSON NOT NULL,
  severity    VARCHAR(20) NOT NULL,
  auto_healable TINYINT(1) DEFAULT 0,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_ai_center (center_id),
  INDEX idx_ai_fp (fingerprint)
);

-- 3. Admin notification audit (which alert went to which admin)
CREATE TABLE IF NOT EXISTS admin_notifications (
  id           VARCHAR(36) PRIMARY KEY,
  alert_id     VARCHAR(36) NULL,
  channel      VARCHAR(20) NOT NULL,   -- 'sms', 'email'
  recipient    VARCHAR(120) NOT NULL,
  status       VARCHAR(20) NOT NULL DEFAULT 'sent',
  sent_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_an_alert (alert_id),
  INDEX idx_an_sent  (sent_at)
);
