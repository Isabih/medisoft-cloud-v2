#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Medisoft SMS + Email Fix v4 SAFE ==="
read -s -p "Enter MySQL root password: " MYSQL_ROOT_PASSWORD
echo

echo "=== Updating database schema safely ==="
mysql -u root -p"$MYSQL_ROOT_PASSWORD" medisoft_guardian <<'SQL'
SET @db='medisoft_guardian';

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='sms_enabled'),
  'ALTER TABLE settings ADD COLUMN sms_enabled TINYINT(1) NOT NULL DEFAULT 1',
  'SELECT "sms_enabled exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='sms_api_url'),
  'ALTER TABLE settings ADD COLUMN sms_api_url VARCHAR(500) NULL DEFAULT "https://www.intouchsms.co.rw/api/sendsms/.json"',
  'SELECT "sms_api_url exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='sms_timeout_seconds'),
  'ALTER TABLE settings ADD COLUMN sms_timeout_seconds INT NOT NULL DEFAULT 30',
  'SELECT "sms_timeout_seconds exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db AND table_name='settings' AND column_name='email_enabled'),
  'ALTER TABLE settings ADD COLUMN email_enabled TINYINT(1) NOT NULL DEFAULT 1',
  'SELECT "email_enabled exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE settings
SET sms_api_url='https://www.intouchsms.co.rw/api/sendsms/.json',
    sms_timeout_seconds=30,
    sms_enabled=1,
    email_enabled=1
WHERE id=1;
SQL
