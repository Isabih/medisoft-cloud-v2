#!/usr/bin/env bash
set -euo pipefail

# Medisoft Guardian Monitoring Backend v4 installer/upgrade.
# Run this inside the backend directory on the CLOUD server.

BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_CANDIDATES=(medisoft-guardian-v3-backend medisoft-guardian-v4-backend medisoft-guardian-backend)
DB_NAME="medisoft_guardian"
PORT="${PORT:-8005}"
HOST="${HOST:-127.0.0.1}"

cd "$BACKEND_DIR"
echo "=================================================="
echo " MEDISOFT GUARDIAN MONITORING BACKEND v4"
echo "=================================================="

read -s -p "Enter MySQL root password: " MYSQL_ROOT_PASSWORD
echo

echo "Stopping old standalone cloud collectors..."
for s in medisoft-cloud-replica-collector medisoft-cloud-replica-collector-v2 medisoft-cloud-replica-collector-v3 medisoft-cloud-collector-v4; do
  sudo systemctl stop "$s" 2>/dev/null || true
  sudo systemctl disable "$s" 2>/dev/null || true
  sudo rm -f "/etc/systemd/system/$s.service" 2>/dev/null || true
done
sudo systemctl daemon-reload

echo "Creating/updating .env..."
SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
if [ -f .env ]; then
  cp .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
fi
python3 - <<PY
from pathlib import Path
p=Path('.env')
lines={}
if p.exists():
    for raw in p.read_text().splitlines():
        if '=' in raw and not raw.strip().startswith('#'):
            k,v=raw.split('=',1); lines[k]=v
lines['DATABASE_URL']='mysql+pymysql://root:${MYSQL_ROOT_PASSWORD}@127.0.0.1:3306/${DB_NAME}'
lines.setdefault('SECRET_KEY','${SECRET}')
lines.setdefault('ENVIRONMENT','production')
lines.setdefault('DEBUG','false')
lines.setdefault('AUTO_CREATE_TABLES','true')
lines.setdefault('RETENTION_DAYS','7')
lines.setdefault('ENABLE_CLOUD_ADMIN_COMMANDS','false')
lines.setdefault('CORS_ORIGINS','["http://100.115.244.88","http://100.115.244.88/v3","http://localhost:5173","http://127.0.0.1:5173","http://localhost:8080","http://127.0.0.1:8080"]')
p.write_text('\n'.join(f'{k}={v}' for k,v in lines.items())+'\n')
PY
chmod 600 .env

echo "Installing Python dependencies..."
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "Running Monitoring v4 in-place migration..."
venv/bin/python - <<'PY'
from app.core.database import SessionLocal
from app.services.monitoring_v4 import migrate_monitoring_v4, collect_once

db = SessionLocal()
try:
    migrate_monitoring_v4(db)
finally:
    db.close()
print('Migration completed.')
try:
    print(collect_once())
except Exception as exc:
    print('Initial collection warning:', exc)
PY

SERVICE_FOUND=""
for s in "${SERVICE_CANDIDATES[@]}"; do
  if systemctl list-unit-files | grep -q "^$s.service"; then SERVICE_FOUND="$s"; break; fi
done

if [ -z "$SERVICE_FOUND" ]; then
  SERVICE_FOUND="medisoft-guardian-v4-backend"
  echo "Creating backend service: $SERVICE_FOUND"
  sudo tee "/etc/systemd/system/$SERVICE_FOUND.service" >/dev/null <<EOF
[Unit]
Description=Medisoft Guardian Backend v4
After=network-online.target mysql.service
Wants=network-online.target

[Service]
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$BACKEND_DIR/venv/bin/python run.py
Restart=always
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_FOUND"
fi

echo "Restarting backend service: $SERVICE_FOUND"
sudo systemctl restart "$SERVICE_FOUND"
sleep 5
sudo systemctl status "$SERVICE_FOUND" --no-pager || true

echo "=================================================="
echo "DONE ✅"
echo "Health: curl http://127.0.0.1:$PORT/api/v1/monitoring-v4/health"
echo "Collect now: curl -X POST http://127.0.0.1:$PORT/api/v1/monitoring-v4/collect-now | jq"
echo "Gasetsa: curl http://100.115.244.88/v3/api/v1/monitoring-v4/center-complete/625 | jq"
echo "=================================================="
