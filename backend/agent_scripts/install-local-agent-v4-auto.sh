#!/usr/bin/env bash
set -euo pipefail

# Medisoft Local Agent v4 auto installer.
# Usage: sudo bash install-local-agent-v4-auto.sh [BACKEND_BASE_URL]
# Example: sudo bash install-local-agent-v4-auto.sh http://100.115.244.88/v3

BACKEND="${1:-${BACKEND:-http://100.115.244.88/v3}}"
SERVICE="medisoft-local-agent"
DIR="/opt/medisoft-local-agent-v4"

echo "=================================================="
echo " MEDISOFT LOCAL AGENT v4 AUTO INSTALLER"
echo "=================================================="
echo "Backend: $BACKEND"

# Detect MySQL credentials. Ask only if passwordless root does not work.
MYSQL_USER="root"
MYSQL_PASS=""
MYSQL_CMD=(mysql -u root)
if ! mysql -u root -N -e "SELECT 1" >/dev/null 2>&1; then
  read -p "MySQL user [root]: " MYSQL_USER
  MYSQL_USER=${MYSQL_USER:-root}
  read -s -p "MySQL password: " MYSQL_PASS
  echo
  MYSQL_CMD=(mysql -u "$MYSQL_USER" -p"$MYSQL_PASS")
fi

FOSS_ID="$("${MYSQL_CMD[@]}" -N -e "SELECT @@server_id" 2>/dev/null | head -1 || true)"
TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"

# Ask backend for registered centers and match by FOSS ID or Tailscale/source host.
DETECTED_JSON="$(python3 - <<PY || true
import json, urllib.request, sys
backend='$BACKEND'.rstrip('/')
foss='$FOSS_ID'
tail='$TAILSCALE_IP'
try:
    with urllib.request.urlopen(backend + '/api/v1/monitoring-v4/registered-centers', timeout=8) as r:
        centers=json.loads(r.read().decode())
except Exception:
    centers=[]
match=None
for c in centers:
    if str(c.get('foss_id','')) == str(foss):
        match=c; break
for c in centers:
    if not match and tail and str(c.get('source_host','')).startswith(tail):
        match=c; break
print(json.dumps(match or {}))
PY
)"

read_json() { python3 - <<PY
import json
obj=json.loads('''$DETECTED_JSON''' or '{}')
print(obj.get('$1','') or '')
PY
}

DB_NAME="$(read_json database_name)"
CHANNEL="$(read_json replication_channel)"
HC_NAME="$(read_json name)"
REGISTERED_FOSS="$(read_json foss_id)"
if [ -n "$REGISTERED_FOSS" ]; then FOSS_ID="$REGISTERED_FOSS"; fi

# Fallback DB detection: choose largest non-system schema.
if [ -z "$DB_NAME" ]; then
  DB_NAME="$("${MYSQL_CMD[@]}" -N -e "SELECT table_schema FROM information_schema.tables WHERE table_schema NOT IN ('mysql','sys','performance_schema','information_schema') GROUP BY table_schema ORDER BY SUM(data_length+index_length) DESC LIMIT 1" 2>/dev/null | head -1 || true)"
fi
CHANNEL="${CHANNEL:-$DB_NAME}"
HC_NAME="${HC_NAME:-$(echo "$DB_NAME" | tr '[:lower:]' '[:upper:]')}"

if [ -z "$FOSS_ID" ] || [ -z "$DB_NAME" ]; then
  echo "Could not auto-detect FOSS ID or database."
  echo "FOSS_ID='$FOSS_ID' DB_NAME='$DB_NAME'"
  exit 1
fi

echo "Detected:"
echo "  FOSS ID      : $FOSS_ID"
echo "  Health Center: $HC_NAME"
echo "  Database     : $DB_NAME"
echo "  Channel      : $CHANNEL"
echo "  Tailscale IP : ${TAILSCALE_IP:-not detected}"
echo "  MySQL User   : $MYSQL_USER"
echo "  Backend      : $BACKEND"

sudo systemctl stop "$SERVICE" 2>/dev/null || true
sudo rm -rf "$DIR"
sudo mkdir -p "$DIR"

cat > "$DIR/local_agent.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, date, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

import psutil
import pymysql
import requests

FOSS_ID = os.getenv('FOSS_ID', '')
HC_NAME = os.getenv('HC_NAME', '')
DB_NAME = os.getenv('DB_NAME', '')
CHANNEL = os.getenv('CHANNEL', DB_NAME)
BACKEND = os.getenv('BACKEND', '').rstrip('/')
MYSQL_USER = os.getenv('MYSQL_USER', 'root')
MYSQL_PASS = os.getenv('MYSQL_PASS', '')
INTERVAL = int(os.getenv('INTERVAL', '60'))

last_payload = {}
last_status = {"ok": False, "message": "not sent yet"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def value(row: Any, *keys: str, default: Any = None) -> Any:
    if not row:
        return default
    d = dict(row)
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k in d:
            return d[k]
        if str(k).lower() in lower:
            return lower[str(k).lower()]
    return default


def norm_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace('T', ' ').replace('Z', '')).replace(tzinfo=None)
        except Exception:
            return None
    return None


def mysql_conn(database: Optional[str] = None):
    kwargs = dict(host='127.0.0.1', user=MYSQL_USER, password=MYSQL_PASS, cursorclass=pymysql.cursors.DictCursor, autocommit=True, connect_timeout=5, read_timeout=20, write_timeout=20)
    if database:
        kwargs['database'] = database
    return pymysql.connect(**kwargs)


def tailscale_ip() -> Optional[str]:
    try:
        out = subprocess.check_output('tailscale ip -4 2>/dev/null', shell=True, text=True).strip()
        return out.splitlines()[0] if out else None
    except Exception:
        return None


def db_stats() -> dict:
    stats = {"size_mb": 0.0, "table_count": 0, "rows_count": 0, "latest_time": None, "table_summary": []}
    try:
        conn = mysql_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ROUND(COALESCE(SUM(data_length+index_length),0)/1024/1024,2) AS size_mb,
                       COUNT(*) AS table_count
                FROM information_schema.tables WHERE table_schema=%s
            """, (DB_NAME,))
            row = cur.fetchone() or {}
            stats['size_mb'] = float(value(row, 'size_mb', 'SIZE_MB', default=0) or 0)
            stats['table_count'] = int(value(row, 'table_count', 'TABLE_COUNT', default=0) or 0)
            cur.execute("""
                SELECT table_name AS t, ROUND((data_length+index_length)/1024/1024,2) AS size_mb
                FROM information_schema.tables
                WHERE table_schema=%s
                ORDER BY (data_length+index_length) DESC
                LIMIT 25
            """, (DB_NAME,))
            tables = cur.fetchall()
        latest_values = []
        total_rows = 0
        summary = []
        time_cols = ['updated_at','date_updated','modified_at','created_at','date_created','created','date','visit_date']
        for tr in tables:
            table = value(tr, 't', 'T', 'table_name', 'TABLE_NAME')
            if not table:
                continue
            rows = 0
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) AS c FROM `{DB_NAME}`.`{table}`")
                    rows = int(value(cur.fetchone(), 'c', 'C', default=0) or 0)
                    total_rows += rows
            except Exception:
                pass
            summary.append({"table": table, "rows": rows, "size_mb": float(value(tr, 'size_mb', 'SIZE_MB', default=0) or 0)})
            for col in time_cols:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""SELECT COUNT(*) AS c FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s""", (DB_NAME, table, col))
                        exists = int(value(cur.fetchone(), 'c', 'C', default=0) or 0)
                    if exists:
                        with conn.cursor() as cur:
                            cur.execute(f"SELECT MAX(`{col}`) AS latest FROM `{DB_NAME}`.`{table}`")
                            d = norm_dt(value(cur.fetchone(), 'latest', 'LATEST'))
                            if d:
                                latest_values.append(d)
                except Exception:
                    pass
        conn.close()
        stats['rows_count'] = total_rows
        stats['latest_time'] = max(latest_values).strftime('%Y-%m-%d %H:%M:%S') if latest_values else None
        stats['table_summary'] = summary
    except Exception as exc:
        stats['error'] = str(exc)
    return stats


def mysql_status() -> tuple[str, bool]:
    try:
        c = mysql_conn(DB_NAME)
        c.close()
        return 'online', True
    except Exception:
        return 'offline', False


def source_status() -> tuple[bool, int, list[str]]:
    try:
        conn = mysql_conn()
        with conn.cursor() as cur:
            cur.execute('SHOW PROCESSLIST')
            rows = cur.fetchall()
        conn.close()
        hosts = []
        for r in rows:
            user = str(value(r, 'User', 'USER', default='')).lower()
            command = str(value(r, 'Command', 'COMMAND', default='')).lower()
            host = str(value(r, 'Host', 'HOST', default=''))
            state = str(value(r, 'State', 'STATE', default='')).lower()
            if user == 'replica' or 'binlog' in command or 'source' in state or 'master' in state:
                if host:
                    hosts.append(host)
        return True, len(hosts), hosts
    except Exception:
        return False, 0, []


def collect() -> dict:
    mstat, mrunning = mysql_status()
    stats = db_stats()
    src_ok, connected, hosts = source_status()
    disk = shutil.disk_usage('/')
    ts_ip = tailscale_ip()
    payload = {
        'foss_id': FOSS_ID,
        'server_id': FOSS_ID,
        'health_center_name': HC_NAME,
        'db_name': DB_NAME,
        'database_name': DB_NAME,
        'channel_name': CHANNEL,
        'hostname': socket.gethostname(),
        'tailscale_ip': ts_ip,
        'local_server_reachable': True,
        'mysql_status': mstat,
        'mysql_running': mrunning,
        'internet_status': 'online',
        'cloud_connection': 'online',
        'vpn_status': 'online' if ts_ip else 'offline',
        'cpu_usage': psutil.cpu_percent(interval=1),
        'ram_usage': psutil.virtual_memory().percent,
        'disk_usage': round((disk.used / disk.total) * 100, 2),
        'disk_total_gb': round(disk.total / 1024 / 1024 / 1024, 2),
        'disk_free_gb': round(disk.free / 1024 / 1024 / 1024, 2),
        'database_size_mb': stats['size_mb'],
        'local_size_mb': stats['size_mb'],
        'local_table_count': stats['table_count'],
        'local_rows_count': stats['rows_count'],
        'local_row_count': stats['rows_count'],
        'local_latest_time': stats['latest_time'],
        'local_table_summary_json': stats['table_summary'],
        'source_config_ok': src_ok,
        'connected_replicas': connected,
        'replica_hosts': hosts,
        'io_running': 'Source',
        'sql_running': 'Source',
        'seconds_behind': None,
        'last_io_error': '',
        'last_sql_error': '',
        'agent_version': 'local-agent-v4',
        'sent_at': now_iso(),
        'timestamp': now_iso(),
    }
    return payload


def sender_loop():
    global last_payload, last_status
    while True:
        payload = collect()
        last_payload = payload
        try:
            r = requests.post(f'{BACKEND}/api/v1/hybrid/source-report', json=payload, timeout=20)
            last_status = {'ok': r.status_code < 300, 'status_code': r.status_code, 'text': r.text[:500], 'last_sent_at': now_iso()}
            print(json.dumps({'heartbeat': r.status_code, 'foss_id': FOSS_ID, 'rows': payload['local_rows_count'], 'size_mb': payload['local_size_mb']}), flush=True)
        except Exception as exc:
            last_status = {'ok': False, 'error': str(exc), 'last_sent_at': now_iso()}
            print(json.dumps({'error': str(exc)}), flush=True)
        time.sleep(INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/live'):
            data = last_payload or collect()
        elif self.path.startswith('/status'):
            data = {'status': last_status, 'last_payload': last_payload}
        else:
            data = {'ok': True, 'service': 'medisoft-local-agent-v4'}
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    threading.Thread(target=sender_loop, daemon=True).start()
    HTTPServer(('0.0.0.0', 5055), Handler).serve_forever()
PY

cat > "$DIR/.env" <<EOF
FOSS_ID=$FOSS_ID
HC_NAME=$HC_NAME
DB_NAME=$DB_NAME
CHANNEL=$CHANNEL
BACKEND=$BACKEND
MYSQL_USER=$MYSQL_USER
MYSQL_PASS=$MYSQL_PASS
INTERVAL=60
EOF
sudo chmod 600 "$DIR/.env"

python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --upgrade pip
"$DIR/venv/bin/pip" install pymysql requests psutil

sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null <<EOF
[Unit]
Description=Medisoft Local Agent v4
After=network-online.target mysql.service
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/venv/bin/python $DIR/local_agent.py
Restart=always
RestartSec=10
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl restart "$SERVICE"
sleep 5
sudo systemctl status "$SERVICE" --no-pager || true

echo "=================================================="
echo "DONE ✅"
echo "Logs: sudo journalctl -u $SERVICE -f"
echo "Live: curl http://127.0.0.1:5055/live | jq"
echo "Status: curl http://127.0.0.1:5055/status | jq"
echo "=================================================="
