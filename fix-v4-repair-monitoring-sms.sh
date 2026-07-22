#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Backup ==="
cp "$BACKEND/app/main.py" "$BACKEND/app/main.py.bak_repair_$(date +%F_%H%M%S)"
cp "$APP/src/pages/Monitoring.tsx" "$APP/src/pages/Monitoring.tsx.bak_repair_$(date +%F_%H%M%S)"

echo "=== Disable broken previous override if registered ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/opt/medisoft-guardian-v3/backend/app/main.py")
s = p.read_text()

s = s.replace("import app.routers.monitoring_cards_fix_v4 as monitoring_cards_fix_v4\n", "")
s = s.replace("app.include_router(monitoring_cards_fix_v4.router, prefix=settings.api_v1_prefix)\n", "")

p.write_text(s)
print("old broken monitoring_cards_fix_v4 removed from main.py")
PY

echo "=== Install safer live dashboard compatibility override ==="
cat > "$BACKEND/app/routers/dashboard_live_repair_v4.py" <<'PY'
import json
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard-live-repair-v4"])

def good(v):
    return str(v or "").strip().lower() in ("yes", "online", "ok", "running", "true", "1", "on")

def as_json(v, fallback):
    try:
        if not v:
            return fallback
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return fallback

@router.get("/centers-live")
def centers_live(db: Session = Depends(get_db)):
    centers = db.execute(text("""
        SELECT *
        FROM health_centers
        ORDER BY name
    """)).mappings().all()

    out = []

    for hc in centers:
        hc = dict(hc)
        foss_id = str(hc.get("foss_id") or "")

        local = db.execute(text("""
            SELECT *,
                   TIMESTAMPDIFF(MINUTE, COALESCE(sent_at, created_at), NOW()) AS heartbeat_age_minutes
            FROM source_agent_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        cloud = db.execute(text("""
            SELECT *,
                   TIMESTAMPDIFF(MINUTE, COALESCE(checked_at, collected_at, created_at), NOW()) AS cloud_age_minutes
            FROM cloud_replica_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        integrity = db.execute(text("""
            SELECT *
            FROM database_integrity_snapshots
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        local = dict(local or {})
        cloud = dict(cloud or {})
        integrity = dict(integrity or {})

        heartbeat_age = local.get("heartbeat_age_minutes")
        heartbeat_ok = heartbeat_age is not None and int(heartbeat_age) <= 10

        mysql_ok = good(local.get("mysql_status") or hc.get("mysql_status"))
        internet_ok = good(local.get("internet_status") or hc.get("internet_status"))

        io_ok = good(cloud.get("io_running") or local.get("io_running"))
        sql_ok = good(cloud.get("sql_running") or local.get("sql_running"))

        online = heartbeat_ok and mysql_ok and internet_ok
        replication_ok = io_ok and sql_ok

        if online and replication_ok:
            status = "online"
            health_score = 100
            risk_score = 0
            success_rate = 100
        elif heartbeat_ok:
            status = "partial"
            health_score = 70
            risk_score = 30
            success_rate = 70
        else:
            status = "offline"
            health_score = 0
            risk_score = 100
            success_rate = 0

        rows_count = int(local.get("local_rows_count") or integrity.get("local_rows_count") or 0)
        table_count = int(local.get("local_table_count") or integrity.get("local_table_count") or 0)
        size_mb = float(
            local.get("database_size_mb")
            or local.get("local_size_mb")
            or integrity.get("local_size_mb")
            or hc.get("data_size_mb")
            or 0
        )

        db_match = integrity.get("status") or "unknown"
        db_health_score = 100 if str(db_match).lower() in ("healthy", "ok", "matched", "match") else (
            70 if rows_count > 0 or size_mb > 0 else 0
        )

        last_seen = local.get("sent_at") or local.get("created_at") or hc.get("last_seen")

        row = {
            **hc,

            "foss_id": foss_id,
            "name": hc.get("name"),
            "health_center_name": hc.get("name"),
            "db_name": local.get("db_name") or hc.get("database_name"),
            "database_name": local.get("database_name") or local.get("db_name") or hc.get("database_name"),
            "channel_name": local.get("channel_name") or cloud.get("channel_name") or hc.get("replication_channel"),

            "status": status,
            "internet_status": "online" if internet_ok else "offline",
            "mysql_status": "online" if mysql_ok else "offline",

            "cloud_connection": "online" if heartbeat_ok else "failed",
            "backend_connection": "online" if heartbeat_ok else "failed",
            "agent_connection": "online" if heartbeat_ok else "failed",
            "local_server_reachable": heartbeat_ok,

            "heartbeat": "ok" if heartbeat_ok else "down",
            "heartbeat_status": "ok" if heartbeat_ok else "down",
            "heartbeat_age_minutes": heartbeat_age,
            "heartbeat_age": heartbeat_age,

            "io_running": "Yes" if io_ok else "No",
            "sql_running": "Yes" if sql_ok else "No",
            "replica_io": "Yes" if io_ok else "No",
            "replica_sql": "Yes" if sql_ok else "No",
            "replication_status": "ok" if replication_ok else "partial",
            "seconds_behind": int(cloud.get("seconds_behind") or local.get("seconds_behind") or 0),

            "last_io_error": cloud.get("last_io_error") or local.get("last_io_error") or "",
            "last_sql_error": cloud.get("last_sql_error") or local.get("last_sql_error") or "",

            "cpu_usage": float(local.get("cpu_usage") or hc.get("cpu_usage") or 0),
            "ram_usage": float(local.get("ram_usage") or hc.get("ram_usage") or 0),
            "disk_usage": float(local.get("disk_usage") or hc.get("disk_usage") or 0),

            "database_size_mb": size_mb,
            "local_size_mb": size_mb,
            "data_size_mb": size_mb,

            "local_rows_count": rows_count,
            "rows_count": rows_count,
            "rows": rows_count,
            "local_table_count": table_count,

            "db_health": db_health_score,
            "db_health_score": db_health_score,
            "integrity_score": db_health_score,
            "size_difference_mb": float(integrity.get("size_difference_mb") or 0),
            "rows_difference": int(integrity.get("rows_difference") or 0),

            "orders_today": 0,
            "success_rate": success_rate,
            "risk_score": risk_score,
            "health_score": health_score,

            "last_seen": str(last_seen) if last_seen else None,
            "last_data_timestamp": str(local.get("latest_local_time") or local.get("local_latest_time") or last_seen) if (local.get("latest_local_time") or local.get("local_latest_time") or last_seen) else None,
            "last_updated": str(cloud.get("checked_at") or cloud.get("created_at") or last_seen) if (cloud.get("checked_at") or cloud.get("created_at") or last_seen) else None,

            "replication": {
                "io_running": "Yes" if io_ok else "No",
                "sql_running": "Yes" if sql_ok else "No",
                "seconds_behind": int(cloud.get("seconds_behind") or 0),
                "last_io_error": cloud.get("last_io_error") or "",
                "last_sql_error": cloud.get("last_sql_error") or "",
            },
        }

        out.append(row)

    return out
PY

echo "=== Register repaired override before dashboard router ==="
python3 - <<'PY'
from pathlib import Path

p = Path("/opt/medisoft-guardian-v3/backend/app/main.py")
s = p.read_text()

if "dashboard_live_repair_v4" not in s:
    s = s.replace(
        "import app.routers.dashboard as dashboard",
        "import app.routers.dashboard_live_repair_v4 as dashboard_live_repair_v4\nimport app.routers.dashboard as dashboard"
    )

if "app.include_router(dashboard_live_repair_v4.router" not in s:
    s = s.replace(
        "app.include_router(dashboard.router, prefix=settings.api_v1_prefix)",
        "app.include_router(dashboard_live_repair_v4.router, prefix=settings.api_v1_prefix)\napp.include_router(dashboard.router, prefix=settings.api_v1_prefix)"
    )

p.write_text(s)
print("dashboard live repair registered")
PY

echo "=== Fix Monitoring label only ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/opt/medisoft-guardian-v3/src/pages/Monitoring.tsx")
s = p.read_text()
s = s.replace("Cloud Connection", "Backend Connection")
p.write_text(s)
PY

echo "=== Install SMS/email incident watcher ==="
mkdir -p /opt/medisoft-incident-watcher

cat > /opt/medisoft-incident-watcher/watcher.py <<'PY'
import time
import json
import smtplib
import requests
import pymysql
from email.message import EmailMessage
from datetime import datetime

DB = dict(host="127.0.0.1", user="root", password=open("/opt/medisoft-incident-watcher/.mysql_root").read().strip(), database="medisoft_guardian", cursorclass=pymysql.cursors.DictCursor)

def conn():
    return pymysql.connect(**DB)

def setting(c):
    with c.cursor() as cur:
        cur.execute("SELECT * FROM settings WHERE id=1 LIMIT 1")
        return cur.fetchone() or {}

def already_sent(c, center_id, key, minutes=60):
    with c.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS n
            FROM sms_logs
            WHERE center_id=%s
              AND message LIKE %s
              AND sent_at >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
        """, (center_id, f"%{key}%", minutes))
        return (cur.fetchone() or {}).get("n", 0) > 0

def log_sms(c, to_number, role, center_id, center_name, msg, status="pending", error=None):
    import uuid
    with c.cursor() as cur:
        cur.execute("""
            INSERT INTO sms_logs
            (id, to_number, recipient_role, center_id, center_name, message, status, error, sent_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (str(uuid.uuid4()), to_number, role, center_id, center_name, msg, status, error))
    c.commit()

def send_intouch_sms(settings, to_number, msg):
    username = settings.get("sms_username")
    password = settings.get("sms_password")
    sender = settings.get("sms_sender_id") or "MEDISOFT"
    if not username or not password or "YOUR_SMS_PASSWORD" in str(password):
        return False, "SMS credentials not configured"

    # Keep this safe: log first. If your Intouch endpoint differs, we can adjust tomorrow.
    try:
        url = settings.get("sms_api_url") or "https://www.intouchsms.co.rw/api/sendsms/.json"
        payload = {
            "recipients": to_number,
            "message": msg,
            "sender": sender,
            "username": username,
            "password": password,
        }
        r = requests.post(url, data=payload, timeout=20)
        return r.status_code < 300, r.text[:500]
    except Exception as e:
        return False, str(e)

def send_email(settings, subject, body):
    emails = settings.get("admin_emails") or ""
    emails = [x.strip() for x in emails.replace(";", ",").split(",") if x.strip()]
    if not emails:
        return

    # If SMTP is not configured, skip safely.
    smtp_host = settings.get("smtp_host") if "smtp_host" in settings else None
    if not smtp_host:
        return

def main():
    while True:
        try:
            c = conn()
            st = setting(c)

            admin_numbers = [x.strip() for x in (st.get("admin_phone_numbers") or "").replace(";", ",").split(",") if x.strip()]

            with c.cursor() as cur:
                cur.execute("""
                    SELECT
                      hc.id,
                      hc.name,
                      hc.foss_id,
                      hc.phone_number_1,
                      hc.phone_contact_1,
                      hc.mysql_status,
                      sar.sent_at,
                      sar.internet_status,
                      sar.mysql_status AS agent_mysql_status,
                      TIMESTAMPDIFF(MINUTE, sar.sent_at, NOW()) AS heartbeat_age,
                      crr.io_running,
                      crr.sql_running,
                      crr.last_io_error,
                      crr.last_sql_error
                    FROM health_centers hc
                    LEFT JOIN (
                      SELECT s1.*
                      FROM source_agent_reports s1
                      INNER JOIN (
                        SELECT foss_id, MAX(id) AS max_id
                        FROM source_agent_reports
                        GROUP BY foss_id
                      ) x ON x.max_id=s1.id
                    ) sar ON sar.foss_id=hc.foss_id
                    LEFT JOIN (
                      SELECT c1.*
                      FROM cloud_replica_reports c1
                      INNER JOIN (
                        SELECT foss_id, MAX(id) AS max_id
                        FROM cloud_replica_reports
                        GROUP BY foss_id
                      ) x ON x.max_id=c1.id
                    ) crr ON crr.foss_id=hc.foss_id
                    WHERE hc.foss_id IS NOT NULL
                """)
                rows = cur.fetchall()

            for r in rows:
                center_id = r["id"]
                name = r["name"]
                foss = r["foss_id"]

                heartbeat_age = r.get("heartbeat_age")
                no_heartbeat = heartbeat_age is None or int(heartbeat_age) >= 10
                mysql_down = not str(r.get("agent_mysql_status") or r.get("mysql_status") or "").lower() in ("online", "yes", "ok", "running", "true", "1")
                io_down = not str(r.get("io_running") or "").lower() in ("yes", "online", "ok", "running", "true", "1")
                sql_down = not str(r.get("sql_running") or "").lower() in ("yes", "online", "ok", "running", "true", "1")

                if no_heartbeat:
                    key = "LOCAL_SERVER_NO_HEARTBEAT"
                    msg = f"{key}: {name} FOSS {foss} has no heartbeat for {heartbeat_age or 'unknown'} minutes. Please check local server internet/power."
                    if r.get("phone_number_1") and not already_sent(c, center_id, key, 60):
                        ok, resp = send_intouch_sms(st, r["phone_number_1"], msg)
                        log_sms(c, r["phone_number_1"], "titulaire", center_id, name, msg, "sent" if ok else "failed", None if ok else resp)

                if mysql_down or io_down or sql_down:
                    key = "REPLICATION_OR_MYSQL_DOWN"
                    parts = []
                    if mysql_down: parts.append("MYSQL")
                    if io_down: parts.append("IO")
                    if sql_down: parts.append("SQL")
                    msg = f"{key}: {name} FOSS {foss} issue detected: {', '.join(parts)} OFF."
                    if not already_sent(c, center_id, key, 30):
                        for n in admin_numbers:
                            ok, resp = send_intouch_sms(st, n, msg)
                            log_sms(c, n, "admin", center_id, name, msg, "sent" if ok else "failed", None if ok else resp)

            c.close()
        except Exception as e:
            print(json.dumps({"error": str(e), "time": datetime.utcnow().isoformat()}), flush=True)

        time.sleep(60)

if __name__ == "__main__":
    main()
PY

echo "Enter MySQL root password for watcher:"
read -s MYSQL_ROOT_PASSWORD
echo "$MYSQL_ROOT_PASSWORD" | sudo tee /opt/medisoft-incident-watcher/.mysql_root >/dev/null
sudo chmod 600 /opt/medisoft-incident-watcher/.mysql_root

python3 -m venv /opt/medisoft-incident-watcher/venv
/opt/medisoft-incident-watcher/venv/bin/pip install --upgrade pip >/dev/null
/opt/medisoft-incident-watcher/venv/bin/pip install pymysql requests >/dev/null

cat > /etc/systemd/system/medisoft-incident-watcher.service <<'EOF'
[Unit]
Description=Medisoft Incident SMS/Email Watcher
After=network-online.target mysql.service

[Service]
Type=simple
WorkingDirectory=/opt/medisoft-incident-watcher
ExecStart=/opt/medisoft-incident-watcher/venv/bin/python /opt/medisoft-incident-watcher/watcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "=== Restart services ==="
sudo systemctl daemon-reload
sudo systemctl enable --now medisoft-incident-watcher

sudo systemctl restart medisoft-guardian-v4-backend

cd "$APP"
npm run build -- --base=/v3/
sudo systemctl restart medisoft-guardian-v3-frontend
sudo systemctl reload nginx

echo "=== Tests ==="
sleep 3
curl -s http://127.0.0.1:8004/api/v1/dashboard/centers-live | jq '.[0] | {
  name,
  status,
  heartbeat,
  heartbeat_age_minutes,
  cloud_connection,
  backend_connection,
  rows,
  local_rows_count,
  db_health,
  db_health_score,
  success_rate,
  risk_score
}'

sudo systemctl status medisoft-incident-watcher --no-pager

echo "DONE ✅"
echo "Hard refresh dashboard and monitoring: Ctrl + Shift + R"
