#!/bin/bash
set -euo pipefail

# =========================================================
# MEDISOFT LOCAL AGENT INSTALLER
# Enterprise Production Installer
# =========================================================

APP_NAME="medisoft-local-agent"
APP_USER="medisoft-agent"

APP_DIR="/opt/medisoft-local-agent"

SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

DEFAULT_BACKEND_URL="https://YOUR-CLOUD-DOMAIN.rw"
DEFAULT_VPN_INTERFACE="tailscale0"

MONITOR_USER="monitor"

echo
echo "========================================================="
echo "         MEDISOFT LOCAL AGENT INSTALLER"
echo "========================================================="
echo

# =========================================================
# ROOT CHECK
# =========================================================

if [[ "$EUID" -ne 0 ]]; then
    echo "Please run as root."
    exit 1
fi

# =========================================================
# INSTALL REQUIREMENTS
# =========================================================

echo "[1/14] Installing requirements..."

apt update

apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    mysql-client \
    curl \
    jq \
    net-tools \
    sqlite3

# =========================================================
# CREATE SYSTEM USER
# =========================================================

echo "[2/14] Creating service user..."

if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd -r -s /usr/sbin/nologin "$APP_USER"
fi

# =========================================================
# INPUTS
# =========================================================

echo
read -r -p "Backend URL [$DEFAULT_BACKEND_URL]: " API_BASE_URL
API_BASE_URL="${API_BASE_URL:-$DEFAULT_BACKEND_URL}"

echo
read -r -p "VPN Interface [$DEFAULT_VPN_INTERFACE]: " VPN_INTERFACE
VPN_INTERFACE="${VPN_INTERFACE:-$DEFAULT_VPN_INTERFACE}"

echo
read -r -s -p "MySQL ROOT Password: " MYSQL_ROOT_PASS
echo

echo
read -r -s -p "Monitoring User Password: " MONITOR_PASS
echo

MYSQL=(mysql -u root "-p$MYSQL_ROOT_PASS" -N)

# =========================================================
# BACKEND CHECK
# =========================================================

echo
echo "[3/14] Checking backend..."

if curl -fsS --max-time 5 "$API_BASE_URL/api/v1/health" >/dev/null 2>&1; then
    echo "Backend reachable."
else
    echo "WARNING: Backend not reachable now."
fi

# =========================================================
# DISCOVER DATABASES
# =========================================================

echo
echo "[4/14] Discovering databases..."

mapfile -t DBS < <("${MYSQL[@]}" -e "SHOW DATABASES;" | grep -vE '^(information_schema|performance_schema|mysql|sys)$')

if [[ ${#DBS[@]} -eq 0 ]]; then
    echo "No databases found."
    exit 1
fi

TMP_FILE="$(mktemp)"

for DBNAME in "${DBS[@]}"; do

    TABLE_EXISTS="$("${MYSQL[@]}" -e "
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema='${DBNAME}'
    AND table_name='address';
    " 2>/dev/null || true)"

    if [[ "$TABLE_EXISTS" != "1" ]]; then
        continue
    fi

    FOSS_ID="$("${MYSQL[@]}" -e "
        SELECT fosaid
        FROM \`${DBNAME}\`.address
        WHERE fosaid IS NOT NULL
        LIMIT 1;
    " 2>/dev/null || true)"

    CENTER_NAME="$("${MYSQL[@]}" -e "
        SELECT village
        FROM \`${DBNAME}\`.address
        WHERE village IS NOT NULL
        LIMIT 1;
    " 2>/dev/null || true)"

    if [[ -n "${FOSS_ID:-}" ]]; then

        CHANNEL="${DBNAME%%_*}"

        [[ -z "$CHANNEL" ]] && CHANNEL="$DBNAME"

        echo "${DBNAME}|${CHANNEL}|${FOSS_ID}|${CENTER_NAME}" >> "$TMP_FILE"
    fi
done

if [[ ! -s "$TMP_FILE" ]]; then
    echo "No valid health center databases found."
    exit 1
fi

echo
echo "Detected databases:"
echo

i=1

while IFS='|' read -r DB CH FOSS CENTER; do
    echo "$i) DB=$DB | CHANNEL=$CH | FOSS_ID=$FOSS | CENTER=$CENTER"
    i=$((i+1))
done < "$TMP_FILE"

echo
read -r -p "Select database number: " PICK

LINE="$(sed -n "${PICK}p" "$TMP_FILE")"

if [[ -z "$LINE" ]]; then
    echo "Invalid selection."
    exit 1
fi

IFS='|' read -r SELECTED_DB SELECTED_CHANNEL SELECTED_FOSS SELECTED_CENTER <<< "$LINE"

HOSTNAME_NOW="$(hostname)"

DEFAULT_CENTER_NAME="${SELECTED_CENTER:-${SELECTED_CHANNEL^^} Health Center}"

echo
read -r -p "Health Center Name [$DEFAULT_CENTER_NAME]: " HEALTH_CENTER_NAME
HEALTH_CENTER_NAME="${HEALTH_CENTER_NAME:-$DEFAULT_CENTER_NAME}"

echo
echo "========================================================="
echo "Detected Configuration"
echo "========================================================="
echo "Database       : $SELECTED_DB"
echo "Channel        : $SELECTED_CHANNEL"
echo "FOSS_ID        : $SELECTED_FOSS"
echo "Center Name    : $HEALTH_CENTER_NAME"
echo "Hostname       : $HOSTNAME_NOW"
echo "VPN Interface  : $VPN_INTERFACE"
echo "Backend URL    : $API_BASE_URL"
echo "========================================================="
echo

read -r -p "Continue? (yes/no): " CONFIRM

if [[ ! "$CONFIRM" =~ ^(yes|y|Y)$ ]]; then
    echo "Cancelled."
    exit 0
fi

# =========================================================
# CREATE MYSQL USER
# =========================================================

echo
echo "[5/14] Creating monitoring user..."

"${MYSQL[@]}" <<SQL

CREATE USER IF NOT EXISTS '$MONITOR_USER'@'localhost'
IDENTIFIED WITH mysql_native_password BY '$MONITOR_PASS';

ALTER USER '$MONITOR_USER'@'localhost'
IDENTIFIED WITH mysql_native_password BY '$MONITOR_PASS';

GRANT SELECT ON *.* TO '$MONITOR_USER'@'localhost';
GRANT PROCESS ON *.* TO '$MONITOR_USER'@'localhost';
GRANT REPLICATION CLIENT ON *.* TO '$MONITOR_USER'@'localhost';

FLUSH PRIVILEGES;

SQL

# =========================================================
# APP DIRECTORY
# =========================================================

echo
echo "[6/14] Preparing application directory..."

mkdir -p "$APP_DIR"

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# =========================================================
# PYTHON AGENT
# =========================================================

echo
echo "[7/14] Writing local agent..."

cat > "$APP_DIR/local_agent.py" <<'PY'
#!/usr/bin/env python3

import json
import os
import socket
import sqlite3
import subprocess
import time
from datetime import datetime

import psutil
import pymysql
import requests

from pymysql.cursors import DictCursor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# ENV
# =====================================================

API_BASE_URL = os.getenv("API_BASE_URL")

FOSS_ID = os.getenv("FOSS_ID")
HEALTH_CENTER_NAME = os.getenv("HEALTH_CENTER_NAME")

DB_NAME = os.getenv("DB_NAME")
CHANNEL_NAME = os.getenv("CHANNEL_NAME")

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

VPN_INTERFACE = os.getenv("VPN_INTERFACE", "tailscale0")

REPORT_INTERVAL_SECONDS = int(os.getenv("REPORT_INTERVAL_SECONDS", "60"))

CHECK_TABLE_NAME = os.getenv("CHECK_TABLE_NAME", "address")
CHECK_TIME_COLUMN = os.getenv("CHECK_TIME_COLUMN", "updated_at")

CACHE_DB = os.getenv("CACHE_DB", "/opt/medisoft-local-agent/cache.db")

# =====================================================
# HTTP SESSION
# =====================================================

session = requests.Session()

retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504]
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("http://", adapter)
session.mount("https://", adapter)

# =====================================================
# SQLITE CACHE
# =====================================================

def init_cache():
    conn = sqlite3.connect(CACHE_DB)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS failed_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payload TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def cache_payload(payload):

    conn = sqlite3.connect(CACHE_DB)

    conn.execute(
        "INSERT INTO failed_reports(payload) VALUES(?)",
        (json.dumps(payload),)
    )

    conn.commit()
    conn.close()

def resend_cached():

    conn = sqlite3.connect(CACHE_DB)

    rows = conn.execute(
        "SELECT id, payload FROM failed_reports ORDER BY id ASC LIMIT 100"
    ).fetchall()

    for row in rows:

        row_id = row[0]
        payload = json.loads(row[1])

        try:

            r = session.post(
                API_BASE_URL + "/api/v1/hybrid/source-report",
                json=payload,
                timeout=10
            )

            if r.status_code < 400:
                conn.execute(
                    "DELETE FROM failed_reports WHERE id=?",
                    (row_id,)
                )
                conn.commit()

        except Exception:
            pass

    conn.close()

# =====================================================
# HELPERS
# =====================================================

def now():
    return datetime.utcnow().isoformat() + "Z"

def mysql_conn(database=None):

    kwargs = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "cursorclass": DictCursor,
        "autocommit": True,
        "connect_timeout": 5,
    }

    if database:
        kwargs["database"] = database

    return pymysql.connect(**kwargs)

def query(conn, sql, args=None):

    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()

def query_value(conn, sql, args=None, default=None):

    with conn.cursor() as cur:

        cur.execute(sql, args or ())

        row = cur.fetchone()

        if not row:
            return default

        return list(row.values())[-1]

# =====================================================
# CHECKS
# =====================================================

def mysql_status():

    try:
        conn = mysql_conn()
        conn.close()
        return "online"
    except Exception:
        return "offline"

def internet_status():

    try:
        session.get("https://google.com", timeout=5)
        return "online"
    except Exception:
        return "offline"

def cloud_connection():

    try:
        session.get(API_BASE_URL + "/api/v1/health", timeout=5)
        return "online"
    except Exception:
        return "offline"

def vpn_status():

    try:

        stats = psutil.net_if_stats()

        if VPN_INTERFACE in stats:
            if stats[VPN_INTERFACE].isup:
                return "online"

        return "offline"

    except Exception:
        return "unknown"

# =====================================================
# RESOURCES
# =====================================================

def resources():

    return {
        "cpu_usage": psutil.cpu_percent(interval=1),
        "ram_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
    }

# =====================================================
# DB SIZE
# =====================================================

def database_size_mb():

    try:

        conn = mysql_conn()

        sql = """
        SELECT ROUND(SUM(data_length + index_length)/1024/1024,2)
        FROM information_schema.tables
        WHERE table_schema=%s
        """

        size = query_value(conn, sql, (DB_NAME,), 0)

        conn.close()

        return float(size or 0)

    except Exception:
        return 0

# =====================================================
# LOCAL DATA STATUS
# =====================================================

def local_data_status():

    try:

        conn = mysql_conn(DB_NAME)

        rows = query_value(
            conn,
            f"SELECT COUNT(*) FROM `{CHECK_TABLE_NAME}`",
            default=0
        )

        latest = query_value(
            conn,
            f"SELECT MAX(`{CHECK_TIME_COLUMN}`) FROM `{CHECK_TABLE_NAME}`",
            default=None
        )

        conn.close()

        return {
            "local_row_count": int(rows or 0),
            "local_latest_time": latest.isoformat() if latest else None
        }

    except Exception:

        return {
            "local_row_count": 0,
            "local_latest_time": None
        }

# =====================================================
# SOURCE CONFIG
# =====================================================

def source_config():

    result = {
        "source_config_ok": False,
        "connected_replicas": 0,
        "replica_hosts": [],
        "io_running": "No",
        "sql_running": "No",
        "seconds_behind": None,
        "last_io_error": "",
        "last_sql_error": "",
    }

    try:

        conn = mysql_conn()

        server_id = str(query_value(conn, "SHOW VARIABLES LIKE 'server_id'", default="0"))
        log_bin = str(query_value(conn, "SHOW VARIABLES LIKE 'log_bin'", default="OFF")).upper()
        binlog_format = str(query_value(conn, "SHOW VARIABLES LIKE 'binlog_format'", default="")).upper()

        rows = query(conn, """
            SELECT HOST
            FROM information_schema.PROCESSLIST
            WHERE USER IN ('replica','repl','replication')
        """)

        replicas = [r["HOST"] for r in rows if r.get("HOST")]

        source_ok = (
            server_id != "0"
            and log_bin == "ON"
            and binlog_format in ("ROW", "MIXED")
        )

        result.update({
            "source_config_ok": source_ok,
            "connected_replicas": len(replicas),
            "replica_hosts": replicas,
        })

        repl = []
        try:
            repl = query(conn, "SHOW REPLICA STATUS")
        except Exception:
            try:
                repl = query(conn, "SHOW SLAVE STATUS")
            except Exception:
                repl = []

        if repl:
            repl_row = repl[0]
            result.update({
                "io_running": repl_row.get("Replica_IO_Running") or repl_row.get("Slave_IO_Running") or "No",
                "sql_running": repl_row.get("Replica_SQL_Running") or repl_row.get("Slave_SQL_Running") or "No",
                "seconds_behind": repl_row.get("Seconds_Behind_Source") if repl_row.get("Seconds_Behind_Source") is not None else repl_row.get("Seconds_Behind_Master"),
                "last_io_error": repl_row.get("Last_IO_Error", "") or "",
                "last_sql_error": repl_row.get("Last_SQL_Error", "") or "",
            })

        conn.close()

    except Exception:
        pass

    return result

# =====================================================
# AUTO HEAL
# =====================================================

def mysql_exec(sql):
    cmd = ["mysql", "-u", MYSQL_USER, f"-p{MYSQL_PASSWORD}", "-e", sql]
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f"mysql exited {p.returncode}")
    return p.stdout.strip()

def auto_heal(action):

    try:
        if action == "restart_mysql":
            subprocess.run(["systemctl", "restart", "mysql"], timeout=45, check=True)
            return True, "mysql restarted"

        if action == "start_replica":
            return True, mysql_exec("START REPLICA;") or "replica started"

        if action == "stop_replica":
            return True, mysql_exec("STOP REPLICA;") or "replica stopped"

        if action == "restart_replica":
            mysql_exec("STOP REPLICA;")
            mysql_exec("START REPLICA;")
            return True, "replica restarted"

        if action == "reset_replica":
            # Safe reset: reset connection metadata only after stopping; does not drop local data.
            mysql_exec("STOP REPLICA;")
            mysql_exec("RESET REPLICA;")
            return True, "replica reset; manual CHANGE REPLICATION SOURCE may be required"

        return False, "unknown action"

    except Exception as exc:
        return False, str(exc)

def report_action_result(action_id, success, result):
    if not action_id:
        return
    try:
        session.post(
            API_BASE_URL + f"/api/v1/agent/{FOSS_ID}/actions/{action_id}/result",
            json={"status": "done" if success else "failed", "result": result[:2000]},
            timeout=10,
        )
    except Exception:
        pass

# =====================================================
# PAYLOAD
# =====================================================

def payload():

    res = resources()

    freshness = local_data_status()

    source = source_config()

    return {

        "foss_id": FOSS_ID,
        "health_center_name": HEALTH_CENTER_NAME,

        "db_name": DB_NAME,
        "channel_name": CHANNEL_NAME,

        "hostname": socket.gethostname(),

        "mysql_status": mysql_status(),
        "internet_status": internet_status(),
        "cloud_connection": cloud_connection(),
        "vpn_status": vpn_status(),

        "cpu_usage": res["cpu_usage"],
        "ram_usage": res["ram_usage"],
        "disk_usage": res["disk_usage"],

        "database_size_mb": database_size_mb(),

        "source_config_ok": source["source_config_ok"],
        "connected_replicas": source["connected_replicas"],
        "replica_hosts": source["replica_hosts"],

        "io_running": source["io_running"],
        "sql_running": source["sql_running"],
        "seconds_behind": source.get("seconds_behind"),
        "last_io_error": source.get("last_io_error", ""),
        "last_sql_error": source.get("last_sql_error", ""),
        "agent_version": os.getenv("AGENT_VERSION", "1.0.0"),

        "local_row_count": freshness["local_row_count"],
        "local_latest_time": freshness["local_latest_time"],

        "sent_at": now(),
    }

# =====================================================
# SEND
# =====================================================

def send():

    data = payload()

    try:

        r = session.post(
            API_BASE_URL + "/api/v1/hybrid/source-report",
            json=data,
            timeout=10
        )

        if r.status_code >= 400:
            cache_payload(data)

        try:

            response = r.json()

            action = response.get("action")
            action_id = response.get("action_id")

            if action:
                success, result = auto_heal(action)
                report_action_result(action_id, success, result)
                print("FIRST AID:", result)

        except Exception:
            pass

        print(json.dumps({
            "time": now(),
            "status": r.status_code,
            "response": r.text[:150]
        }))

    except Exception as exc:

        cache_payload(data)

        print(json.dumps({
            "time": now(),
            "error": str(exc)
        }))

# =====================================================
# MAIN
# =====================================================

print("Medisoft Local Agent Started")

init_cache()

while True:

    resend_cached()

    send()

    time.sleep(REPORT_INTERVAL_SECONDS)
PY

chmod +x "$APP_DIR/local_agent.py"

# =========================================================
# ENV FILE
# =========================================================

echo
echo "[8/14] Writing environment..."

cat > "$APP_DIR/.env" <<EOF
API_BASE_URL=${API_BASE_URL}

FOSS_ID=${SELECTED_FOSS}
HEALTH_CENTER_NAME=${HEALTH_CENTER_NAME}

DB_NAME=${SELECTED_DB}
CHANNEL_NAME=${SELECTED_CHANNEL}

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=${MONITOR_USER}
MYSQL_PASSWORD=${MONITOR_PASS}

VPN_INTERFACE=${VPN_INTERFACE}

REPORT_INTERVAL_SECONDS=60
AGENT_VERSION=1.0.0

CHECK_TABLE_NAME=address
CHECK_TIME_COLUMN=updated_at

CACHE_DB=${APP_DIR}/cache.db
EOF

chmod 600 "$APP_DIR/.env"

# =========================================================
# PYTHON VENV
# =========================================================

echo
echo "[9/14] Preparing Python environment..."

python3 -m venv "$APP_DIR/venv"

source "$APP_DIR/venv/bin/activate"

pip install --upgrade pip

pip install \
    psutil \
    pymysql \
    requests

# =========================================================
# OWNERSHIP
# =========================================================

echo
echo "[10/14] Setting permissions..."

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# =========================================================
# SYSTEMD
# =========================================================

echo
echo "[11/14] Creating service..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Medisoft Local Monitoring Agent
After=network.target mysql.service

[Service]
Type=simple

User=root
Group=root

WorkingDirectory=${APP_DIR}

EnvironmentFile=${APP_DIR}/.env

ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/local_agent.py

Restart=always
RestartSec=5

# Runs as root so dashboard First Aid actions can restart MySQL/replication.
# Keep this server accessible only by trusted Medisoft admins.

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# =========================================================
# ENABLE SERVICE
# =========================================================

echo
echo "[12/14] Starting service..."

systemctl daemon-reload

systemctl enable ${APP_NAME}

systemctl restart ${APP_NAME}

# =========================================================
# LOGROTATE
# =========================================================

echo
echo "[13/14] Configuring log rotation..."

cat > /etc/logrotate.d/${APP_NAME} <<EOF
/var/log/${APP_NAME}.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF

# =========================================================
# DONE
# =========================================================

echo
echo "[14/14] DONE"
echo
echo "========================================================="
echo " INSTALLED SUCCESSFULLY"
echo "========================================================="
echo "Database      : $SELECTED_DB"
echo "Channel       : $SELECTED_CHANNEL"
echo "FOSS_ID       : $SELECTED_FOSS"
echo "Center        : $HEALTH_CENTER_NAME"
echo "VPN Interface : $VPN_INTERFACE"
echo "========================================================="
echo
echo "Useful commands:"
echo
echo "systemctl status ${APP_NAME}"
echo "journalctl -u ${APP_NAME} -f"
echo
echo "Backend:"
echo "curl ${API_BASE_URL}/api/v1/health"
echo
echo "Monitoring:"
echo "curl ${API_BASE_URL}/api/v1/hybrid/source-reports"
echo
echo "========================================================="
echo

rm -f "$TMP_FILE"