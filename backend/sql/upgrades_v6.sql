-- =========================================================
-- Medisoft v6 upgrades — SMS source/sender column
-- Run:  mysql -u root -p medisoft_central < backend/sql/upgrades_v6.sql
-- =========================================================

ALTER TABLE sms_logs
  ADD COLUMN IF NOT EXISTS sender VARCHAR(64) NULL AFTER to_number;
