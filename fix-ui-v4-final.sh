#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== 1) Fix SMS Logs blank page API check ==="
curl -i http://127.0.0.1:8004/api/v1/sms/logs || true

echo
echo "=== 2) Check SMS logs table ==="
mysql -u root -p medisoft_guardian -e "
DESCRIBE sms_logs;
SELECT COUNT(*) AS total FROM sms_logs;
"

echo
echo "=== 3) Check reports endpoint ==="
curl -i "http://127.0.0.1:8004/api/v1/reports/operational?from=2026-07-01&to=2026-07-08" || true

echo
echo "=== 4) Check Grafana datasource/dashboard ==="
curl -s http://127.0.0.1:3000/api/health || true
curl -s http://127.0.0.1:3000/api/search | head -c 1000 || true

echo
echo "=== 5) Check frontend API mapping ==="
grep -R "fetchSmsLogs\|fetchOperationalReport\|refetchInterval\|grafana" -n "$APP/src" | head -80

echo
echo "=== 6) Backend logs ==="
journalctl -u medisoft-guardian-v4-backend -n 120 --no-pager

echo
echo "DONE: send me the output above."
