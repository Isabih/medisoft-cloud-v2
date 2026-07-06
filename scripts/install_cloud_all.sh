#!/usr/bin/env bash
# =========================================================
# Medisoft Guardian Cloud v1.0 Enterprise - cloud installer
# Installs backend + frontend + nginx on Ubuntu 22.04/24.04.
# Run from cloned project root: sudo bash install.sh
# =========================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
WEB_ROOT="/var/www/medisoft-guardian-cloud"
SERVICE_NAME="medisoft-guardian-backend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
DB_NAME="${DB_NAME:-medisoft_central}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
SERVER_NAME="${SERVER_NAME:-_}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Medisoft@12345}"

log(){ printf "\033[1;36m[guardian]\033[0m %s\n" "$*"; }
fail(){ printf "\033[1;31m[guardian]\033[0m %s\n" "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "Run as root: sudo bash install.sh"

if [[ -z "${DB_PASS:-}" ]]; then
  read -r -s -p "MySQL password for ${DB_USER}@${DB_HOST}: " DB_PASS; echo
fi
if [[ -z "${SECRET_KEY:-}" ]]; then
  SECRET_KEY="$(openssl rand -hex 32 2>/dev/null || date +%s%N)"
fi

log "1/8 Installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip build-essential pkg-config default-libmysqlclient-dev mysql-client nginx curl git unzip ca-certificates openssl

if ! command -v node >/dev/null || [[ "$(node -v | sed 's/^v//' | cut -d. -f1)" -lt 18 ]]; then
  log "Installing Node.js 20"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

log "2/8 Preparing database ${DB_NAME}"
export MYSQL_PWD="$DB_PASS"
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

log "3/8 Installing backend dependencies"
python3 -m venv "$BACKEND_DIR/.venv"
"$BACKEND_DIR/.venv/bin/pip" install --upgrade pip wheel
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

log "4/8 Writing backend environment"
cat > "$BACKEND_DIR/.env" <<EOF
APP_NAME=Medisoft Guardian Cloud v1.0 Enterprise
DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
SECRET_KEY=${SECRET_KEY}
API_V1_PREFIX=/api/v1
BACKEND_HOST=127.0.0.1
BACKEND_PORT=${BACKEND_PORT}
CORS_ORIGINS=*
AUTO_CREATE_TABLES=true
RETENTION_DAYS=7
RESEND_API_KEY=${RESEND_API_KEY:-}
ALERT_EMAIL_FROM=${ALERT_EMAIL_FROM:-}
ADMIN_EMAILS=${ADMIN_EMAILS:-}
INTOUCH_USERNAME=${INTOUCH_USERNAME:-}
INTOUCH_PASSWORD=${INTOUCH_PASSWORD:-}
INTOUCH_SENDER_ID=${INTOUCH_SENDER_ID:-MEDISOFT}
ADMIN_PHONE_NUMBERS=${ADMIN_PHONE_NUMBERS:-}
EOF
chmod 600 "$BACKEND_DIR/.env"

log "5/8 Applying SQL upgrades"
for f in "$BACKEND_DIR"/sql/upgrades*.sql; do
  [[ -f "$f" ]] || continue
  log "Applying $(basename "$f")"
  mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" < "$f" || log "Warning: $(basename "$f") had non-fatal statements. Continuing."
done

log "Creating default admin user (${ADMIN_USER})"
"$BACKEND_DIR/.venv/bin/python" - <<PY
import uuid
from passlib.context import CryptContext
from sqlalchemy import create_engine, text
url = "mysql+pymysql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
engine = create_engine(url)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
with engine.begin() as c:
    c.execute(text("""
        INSERT INTO users (id, username, password_hash, role, email, created_at)
        VALUES (:id, :u, :p, 'admin', NULL, NOW())
        ON DUPLICATE KEY UPDATE role='admin'
    """), {"id": str(uuid.uuid4()), "u": "${ADMIN_USER}", "p": pwd.hash("${ADMIN_PASSWORD}")})
PY

log "6/8 Building frontend"
cd "$REPO_ROOT"
npm install --no-audit --no-fund
npm run build
mkdir -p "$WEB_ROOT"
rm -rf "$WEB_ROOT"/*
cp -r "$REPO_ROOT/dist/"* "$WEB_ROOT/"
chown -R www-data:www-data "$WEB_ROOT"

log "7/8 Installing backend systemd service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Medisoft Guardian Cloud Backend
After=network.target mysql.service

[Service]
Type=simple
WorkingDirectory=${BACKEND_DIR}
EnvironmentFile=${BACKEND_DIR}/.env
ExecStart=${BACKEND_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

log "8/8 Configuring nginx"
cat > /etc/nginx/sites-available/medisoft-guardian <<EOF
server {
    listen 80 default_server;
    server_name ${SERVER_NAME};
    root ${WEB_ROOT};
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /metrics {
        proxy_pass http://127.0.0.1:${BACKEND_PORT}/metrics;
        proxy_set_header Host \$host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 3600s;
    }

    location / { try_files \$uri /index.html; }
}
EOF
ln -sf /etc/nginx/sites-available/medisoft-guardian /etc/nginx/sites-enabled/medisoft-guardian
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

log "Running post-install health check"
sleep 3
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" >/dev/null && log "Backend OK" || log "Backend not responding yet; check journalctl."

log "============================================================"
log "Medisoft Guardian Cloud v1.0 Enterprise installed."
log "Open: http://<server-ip-or-domain>/"
log "Login: ${ADMIN_USER} / ${ADMIN_PASSWORD}"
log "Backend logs: journalctl -u ${SERVICE_NAME} -f"
log "Local agent installer: local-agent-install.sh"
log "============================================================"
