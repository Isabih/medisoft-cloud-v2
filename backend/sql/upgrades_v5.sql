-- =========================================================
-- Medisoft v5 upgrades — Configurable SMS provider (Intouch Rwanda)
-- Run:  mysql -u root -p medisoft_central < backend/sql/upgrades_v5.sql
-- =========================================================

ALTER TABLE settings
  ADD COLUMN IF NOT EXISTS sms_provider     VARCHAR(32)  NOT NULL DEFAULT 'intouch',
  ADD COLUMN IF NOT EXISTS sms_sender_id    VARCHAR(64)  NULL,
  ADD COLUMN IF NOT EXISTS sms_username     VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS sms_password     VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS sms_api_url      VARCHAR(255) NOT NULL DEFAULT 'https://intouchsms.co.rw',
  ADD COLUMN IF NOT EXISTS admin_phone_numbers TEXT     NULL;
