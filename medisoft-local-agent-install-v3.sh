#!/usr/bin/env bash
set -euo pipefail
VERSION="3.0"
APP_NAME="medisoft-local-agent"
APP_DIR="/opt/medisoft-local-agent"
ENV_FILE="$APP_DIR/.env"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
DEFAULT_BACKEND_URL="http://100.115.244.88:8000"
DEFAULT_VPN_INTERFACE="tailscale0"
MONITOR_USER="medisoft_monitor"

[[ "$EUID" -eq 0 ]] || { echo "Run with sudo/root"; exit 1; }

echo "=================================================="
echo " MEDISOFT LOCAL AGENT INSTALLER v$VERSION"
echo " Monitoring + heartbeat + local First Aid only"
echo " It does NOT create replication, dump DB, or configure cloud"
echo "=================================================="

apt update
apt install -y curl jq python3 python3-venv python3-pip mysql-client sqlite3 net-tools

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Installing Tailscale..."
  curl -fsSL https://tailscale.com/install.sh | sh
fi

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"
if [[ -z "$TAILSCALE_IP" ]]; then
  echo "Tailscale not connected. Running sudo tailscale up..."
  tailscale up || true
  sleep 5
  TAILSCALE_IP="$(tailscale ip -4 2>/dev/null || true)"
fi
[[ -n "$TAILSCALE_IP" ]] || { echo "No Tailscale IP. Finish tailscale login and rerun."; exit 1; }

read -r -p "Backend URL [$DEFAULT_BACKEND_URL]: " API_BASE_URL
API_BASE_URL="${API_BASE_URL:-$DEFAULT_BACKEND_URL}"
read -r -p "VPN interface [$DEFAULT_VPN_INTERFACE]: " VPN_INTERFACE
VPN_INTERFACE="${VPN_INTERFACE:-$DEFAULT_VPN_INTERFACE}"
read -r -s -p "Local MySQL root password: " MYSQL_ROOT_PASS; echo
MYSQL=(mysql -u root "-p$MYSQL_ROOT_PASS" -N)

curl -fsS --max-time 5 "$API_BASE_URL/api/v1/health" >/dev/null 2>&1 && echo "Backend reachable" || echo "WARNING: backend not reachable now"

mapfile -t DBS < <("${MYSQL[@]}" -e "SHOW DATABASES;" | grep -vE '^(information_schema|performance_schema|mysql|sys)$')
[[ ${#DBS[@]} -gt 0 ]] || { echo "No user databases found"; exit 1; }
TMP="$(mktemp)"
for DB in "${DBS[@]}"; do
  HAS="$(${MYSQL[@]} -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB' AND table_name='address';" 2>/dev/null || echo 0)"
  [[ "$HAS" == "1" ]] || continue
  FOSA="$(${MYSQL[@]} -e "SELECT fosaid FROM \`$DB\`.address WHERE fosaid IS NOT NULL LIMIT 1;" 2>/dev/null || true)"
  CENTER="$(${MYSQL[@]} -e "SELECT COALESCE(village, cell, sector, district) FROM \`$DB\`.address LIMIT 1;" 2>/dev/null || true)"
  [[ -n "$FOSA" ]] && echo "$DB|${DB%%_*}|$FOSA|$CENTER" >> "$TMP"
done
[[ -s "$TMP" ]] || { echo "No database with address.fosaid found"; exit 1; }

echo "Detected health-centre databases:"
nl -w2 -s') ' "$TMP"
read -r -p "Select number: " PICK
LINE="$(sed -n "${PICK}p" "$TMP")"
[[ -n "$LINE" ]] || { echo "Invalid selection"; exit 1; }
IFS='|' read -r DB_NAME CHANNEL_NAME FOSAID DETECTED_CENTER <<< "$LINE"
[[ -n "$CHANNEL_NAME" ]] || CHANNEL_NAME="$DB_NAME"
read -r -p "Health Centre Name [${DETECTED_CENTER:-$CHANNEL_NAME}]: " HEALTH_CENTER_NAME
HEALTH_CENTER_NAME="${HEALTH_CENTER_NAME:-${DETECTED_CENTER:-$CHANNEL_NAME}}"
MONITOR_PASS="$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-20)"

echo "Creating monitor user..."
"${MYSQL[@]}" <<SQL
CREATE USER IF NOT EXISTS '$MONITOR_USER'@'localhost' IDENTIFIED BY '$MONITOR_PASS';
ALTER USER '$MONITOR_USER'@'localhost' IDENTIFIED BY '$MONITOR_PASS';
CREATE USER IF NOT EXISTS '$MONITOR_USER'@'127.0.0.1' IDENTIFIED BY '$MONITOR_PASS';
ALTER USER '$MONITOR_USER'@'127.0.0.1' IDENTIFIED BY '$MONITOR_PASS';
GRANT SELECT, PROCESS, REPLICATION CLIENT ON *.* TO '$MONITOR_USER'@'localhost';
GRANT SELECT, PROCESS, REPLICATION CLIENT ON *.* TO '$MONITOR_USER'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

mkdir -p "$APP_DIR"
cat > "$APP_DIR/local_agent.py" <<'PY'
#!/usr/bin/env python3
import json, os, socket, sqlite3, subprocess, time
from datetime import datetime
import psutil, pymysql, requests
from pymysql.cursors import DictCursor

API_BASE_URL=os.getenv('API_BASE_URL').rstrip('/')
FOSS_ID=os.getenv('FOSS_ID'); HEALTH_CENTER_NAME=os.getenv('HEALTH_CENTER_NAME')
DB_NAME=os.getenv('DB_NAME'); CHANNEL_NAME=os.getenv('CHANNEL_NAME')
MYSQL_HOST=os.getenv('MYSQL_HOST','127.0.0.1'); MYSQL_PORT=int(os.getenv('MYSQL_PORT','3306'))
MYSQL_USER=os.getenv('MYSQL_USER'); MYSQL_PASSWORD=os.getenv('MYSQL_PASSWORD')
VPN_INTERFACE=os.getenv('VPN_INTERFACE','tailscale0'); REPORT_INTERVAL_SECONDS=int(os.getenv('REPORT_INTERVAL_SECONDS','60'))
CACHE_DB=os.getenv('CACHE_DB','/opt/medisoft-local-agent/cache.db')
AGENT_VERSION=os.getenv('AGENT_VERSION','3.0')
session=requests.Session()

def now(): return datetime.utcnow().isoformat()+"Z"
def conn(db=None):
    kw=dict(host=MYSQL_HOST,port=MYSQL_PORT,user=MYSQL_USER,password=MYSQL_PASSWORD,cursorclass=DictCursor,autocommit=True,connect_timeout=5)
    if db: kw['database']=db
    return pymysql.connect(**kw)
def qval(sql,args=None,db=None,default=None):
    with conn(db) as c:
        with c.cursor() as cur:
            cur.execute(sql,args or ())
            r=cur.fetchone()
            return default if not r else list(r.values())[-1]
def qrows(sql,args=None,db=None):
    with conn(db) as c:
        with c.cursor() as cur:
            cur.execute(sql,args or ())
            return cur.fetchall()
def init_cache():
    c=sqlite3.connect(CACHE_DB); c.execute('CREATE TABLE IF NOT EXISTS failed_reports(id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'); c.commit(); c.close()
def cache_payload(p):
    c=sqlite3.connect(CACHE_DB); c.execute('INSERT INTO failed_reports(payload) VALUES(?)',(json.dumps(p),)); c.commit(); c.close()
def resend_cached():
    c=sqlite3.connect(CACHE_DB)
    for rid,p in c.execute('SELECT id,payload FROM failed_reports ORDER BY id ASC LIMIT 50').fetchall():
        try:
            r=session.post(API_BASE_URL+'/api/v1/hybrid/source-report',json=json.loads(p),timeout=10)
            if r.status_code<400: c.execute('DELETE FROM failed_reports WHERE id=?',(rid,)); c.commit()
        except Exception: pass
    c.close()
def mysql_status():
    try: qval('SELECT 1'); return 'online'
    except Exception: return 'offline'
def cloud_connection():
    try: return 'online' if session.get(API_BASE_URL+'/api/v1/health',timeout=5).status_code<400 else 'offline'
    except Exception: return 'offline'
def vpn_status():
    try: return 'online' if psutil.net_if_stats().get(VPN_INTERFACE) and psutil.net_if_stats()[VPN_INTERFACE].isup else 'offline'
    except Exception: return 'unknown'
def db_size_mb():
    try: return float(qval('SELECT ROUND(SUM(data_length+index_length)/1024/1024,2) FROM information_schema.tables WHERE table_schema=%s',(DB_NAME,),default=0) or 0)
    except Exception: return 0
def table_count():
    try: return int(qval('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s',(DB_NAME,),default=0) or 0)
    except Exception: return 0
def table_summary():
    try:
        tables=qrows('SELECT table_name name, table_rows approx_rows, ROUND((data_length+index_length)/1024/1024,2) size_mb FROM information_schema.tables WHERE table_schema=%s ORDER BY (data_length+index_length) DESC LIMIT 25',(DB_NAME,))
        out=[]
        for t in tables:
            name=t['name']; rows=int(t.get('approx_rows') or 0)
            try: rows=int(qval(f'SELECT COUNT(*) FROM `{name}`',db=DB_NAME,default=rows) or rows)
            except Exception: pass
            out.append({'table':name,'rows':rows,'size_mb':float(t.get('size_mb') or 0)})
        return out
    except Exception: return []
def latest_data():
    for table in ['consultations','patients','orders','address']:
        for col in ['updated_at','date_updated','modified_at','created_at','date_created']:
            try:
                has=int(qval('SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=%s AND table_name=%s AND column_name=%s',(DB_NAME,table,col),default=0) or 0)
                if has:
                    return str(qval(f'SELECT MAX(`{col}`) FROM `{table}`',db=DB_NAME,default='') or '')
            except Exception: pass
    return None
def replica_status():
    out={'io_running':'No','sql_running':'No','seconds_behind':None,'last_io_error':'','last_sql_error':''}
    try:
        try: rows=qrows(f"SHOW REPLICA STATUS FOR CHANNEL `{CHANNEL_NAME}`")
        except Exception: rows=qrows('SHOW REPLICA STATUS')
        if rows:
            r=rows[0]
            out.update({'io_running':r.get('Replica_IO_Running') or r.get('Slave_IO_Running') or 'No','sql_running':r.get('Replica_SQL_Running') or r.get('Slave_SQL_Running') or 'No','seconds_behind':r.get('Seconds_Behind_Source') if r.get('Seconds_Behind_Source') is not None else r.get('Seconds_Behind_Master'),'last_io_error':r.get('Last_IO_Error') or '','last_sql_error':r.get('Last_SQL_Error') or ''})
    except Exception as e: out['last_sql_error']=str(e)[:500]
    return out
def source_config():
    r=replica_status()
    try:
        log_bin=str(qval("SHOW VARIABLES LIKE 'log_bin'",default='OFF')).upper(); server_id=str(qval("SHOW VARIABLES LIKE 'server_id'",default='0'))
        repl_hosts=[x.get('HOST') for x in qrows("SELECT HOST FROM information_schema.PROCESSLIST WHERE USER IN ('replica','repl','replication')") if x.get('HOST')]
        r.update({'source_config_ok':server_id!='0' and log_bin=='ON','connected_replicas':len(repl_hosts),'replica_hosts':repl_hosts})
    except Exception: r.update({'source_config_ok':False,'connected_replicas':0,'replica_hosts':[]})
    return r
def payload():
    disk=psutil.disk_usage('/') ; src=source_config(); ts=[]
    try: ts=os.popen('tailscale ip -4 2>/dev/null').read().strip().splitlines()
    except Exception: pass
    return {'foss_id':FOSS_ID,'server_id':FOSS_ID,'health_center_name':HEALTH_CENTER_NAME,'db_name':DB_NAME,'database_name':DB_NAME,'channel_name':CHANNEL_NAME,'hostname':socket.gethostname(),'tailscale_ip':ts[0] if ts else None,'mysql_status':mysql_status(),'internet_status':'vpn','cloud_connection':cloud_connection(),'vpn_status':vpn_status(),'cpu_usage':psutil.cpu_percent(interval=1),'ram_usage':psutil.virtual_memory().percent,'disk_usage':disk.percent,'database_size_mb':db_size_mb(),'local_table_count':table_count(),'local_table_summary_json':table_summary(),'local_latest_time':latest_data(),'source_config_ok':src.get('source_config_ok'), 'connected_replicas':src.get('connected_replicas'), 'replica_hosts':src.get('replica_hosts'),'io_running':src.get('io_running'),'sql_running':src.get('sql_running'),'seconds_behind':src.get('seconds_behind'),'last_io_error':src.get('last_io_error',''),'last_sql_error':src.get('last_sql_error',''),'agent_version':AGENT_VERSION,'sent_at':now()}
def mysql_exec(sql):
    cmd=['mysql',f'-h{MYSQL_HOST}',f'-P{MYSQL_PORT}',f'-u{MYSQL_USER}',f'-p{MYSQL_PASSWORD}','-e',sql]
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=60)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-1000:])
    return p.stdout.strip()
def run_command(action,params):
    ch=params.get('channel_name') or CHANNEL_NAME
    try:
        if action=='restart_mysql': subprocess.run(['systemctl','restart','mysql'],check=True,timeout=60); return True,'local mysql restarted'
        if action=='test_mysql': qval('SELECT 1'); return True,'local mysql OK'
        if action=='run_diagnostics': return True,json.dumps(payload())[:2000]
        if action=='refresh_status': send_report(); return True,'status refreshed'
        suffix=f" FOR CHANNEL `{ch}`" if ch else ''
        if action=='start_replica': return True,mysql_exec('START REPLICA'+suffix+';') or f'replica started channel={ch}'
        if action=='stop_replica': return True,mysql_exec('STOP REPLICA'+suffix+';') or f'replica stopped channel={ch}'
        if action=='restart_replica': mysql_exec('STOP REPLICA'+suffix+';'); mysql_exec('START REPLICA'+suffix+';'); return True,f'replica restarted channel={ch}'
        if action=='start_sql': return True,mysql_exec('START REPLICA SQL_THREAD'+suffix+';') or f'SQL thread started channel={ch}'
        if action=='start_io': return True,mysql_exec('START REPLICA IO_THREAD'+suffix+';') or f'IO thread started channel={ch}'
        if action=='stop_sql': return True,mysql_exec('STOP REPLICA SQL_THREAD'+suffix+';') or f'SQL thread stopped channel={ch}'
        if action=='stop_io': return True,mysql_exec('STOP REPLICA IO_THREAD'+suffix+';') or f'IO thread stopped channel={ch}'
        return False,'unknown local action'
    except Exception as e: return False,str(e)
def report_result(cid,ok,res):
    try: session.post(API_BASE_URL+f'/api/v1/local-servers/{FOSS_ID}/commands/{cid}/result',json={'status':'done' if ok else 'failed','result':res[:2000]},timeout=10)
    except Exception: pass
def poll_commands():
    try:
        r=session.get(API_BASE_URL+f'/api/v1/local-servers/{FOSS_ID}/commands/next',timeout=10); data=r.json(); cmd=data.get('command')
        if not cmd: return
        params={}
        try: params=json.loads(cmd.get('params') or '{}')
        except Exception: params={}
        ok,res=run_command(cmd.get('action'),params); report_result(cmd.get('id'),ok,res); print(json.dumps({'time':now(),'command':cmd.get('action'),'ok':ok,'result':res[:200]}))
    except Exception as e: print(json.dumps({'time':now(),'command_poll_error':str(e)}))
def send_report():
    data=payload(); r=session.post(API_BASE_URL+'/api/v1/hybrid/source-report',json=data,timeout=10)
    if r.status_code>=400: cache_payload(data)
    return r

def main():
    init_cache(); print('Medisoft Local Agent v3 started')
    while True:
        resend_cached()
        try:
            r=send_report(); print(json.dumps({'time':now(),'heartbeat':r.status_code,'server_id':FOSS_ID,'channel':CHANNEL_NAME}))
        except Exception as e:
            try: cache_payload(payload())
            except Exception: pass
            print(json.dumps({'time':now(),'heartbeat_error':str(e)}))
        poll_commands()
        time.sleep(REPORT_INTERVAL_SECONDS)
if __name__=='__main__': main()
PY
chmod +x "$APP_DIR/local_agent.py"
cat > "$ENV_FILE" <<EOF
API_BASE_URL=$API_BASE_URL
FOSS_ID=$FOSAID
HEALTH_CENTER_NAME=$HEALTH_CENTER_NAME
DB_NAME=$DB_NAME
CHANNEL_NAME=$CHANNEL_NAME
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=$MONITOR_USER
MYSQL_PASSWORD=$MONITOR_PASS
VPN_INTERFACE=$VPN_INTERFACE
REPORT_INTERVAL_SECONDS=60
AGENT_VERSION=$VERSION
CACHE_DB=$APP_DIR/cache.db
EOF
chmod 600 "$ENV_FILE"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install psutil pymysql requests
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Medisoft Local Monitoring Agent v3
After=network-online.target mysql.service tailscaled.service
Wants=network-online.target
[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/local_agent.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$APP_NAME"
systemctl restart "$APP_NAME"
rm -f "$TMP"
echo "=================================================="
echo "INSTALLED: Medisoft Local Agent v$VERSION"
echo "Server/FOSAID : $FOSAID"
echo "Health Centre : $HEALTH_CENTER_NAME"
echo "Database      : $DB_NAME"
echo "Channel       : $CHANNEL_NAME"
echo "Tailscale IP  : $TAILSCALE_IP"
echo "Backend       : $API_BASE_URL"
echo "Check: systemctl status $APP_NAME"
echo "Logs : journalctl -u $APP_NAME -f"
echo "Cloud status: curl $API_BASE_URL/api/v1/local-servers/$FOSAID/commands"
echo "=================================================="
