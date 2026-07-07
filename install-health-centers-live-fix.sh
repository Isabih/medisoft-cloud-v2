#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/medisoft-guardian-v3"
BACKEND_DIR="$APP_ROOT/backend"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Monitoring v4 Health Centers Live Fix ==="

if [ ! -d "$BACKEND_DIR/app/routers" ]; then
  echo "ERROR: Backend directory not found: $BACKEND_DIR/app/routers"
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
sudo cp "$BACKEND_DIR/app/routers/health_centers.py" "$BACKEND_DIR/app/routers/health_centers.py.bak_$TS"

echo "Installing fixed health_centers.py..."
sudo cp "$SRC_DIR/backend/app/routers/health_centers.py" "$BACKEND_DIR/app/routers/health_centers.py"
sudo chown medisoft:medisoft "$BACKEND_DIR/app/routers/health_centers.py" || true

echo "Restarting backend..."
sudo systemctl restart medisoft-guardian-v4-backend
sleep 3
sudo systemctl status medisoft-guardian-v4-backend --no-pager || true

echo
echo "Testing /health-centers merged fields..."
curl -s http://127.0.0.1:8004/api/v1/health-centers | jq '.[0] | {name, status, internet_status, mysql_status, io:.replication.io_running, sql:.replication.sql_running, db_size_mb:.data_size_mb, head:.phone_contact_1, anydesk:.anydesk_id, rustdesk:.rustdesk_id, last_seen, last_sync, backup:.last_backup}' || true

echo
echo "If frontend still shows old data, rebuild frontend:"
echo "cd $APP_ROOT && npm run build -- --base=/v3/ && sudo systemctl restart medisoft-guardian-v3-frontend && sudo systemctl reload nginx"
echo "DONE ✅"
