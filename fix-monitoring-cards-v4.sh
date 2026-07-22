#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Backup ==="
cp "$BACKEND/app/main.py" "$BACKEND/app/main.py.bak_$(date +%F_%H%M%S)"
cp "$APP/src/pages/Monitoring.tsx" "$APP/src/pages/Monitoring.tsx.bak_$(date +%F_%H%M%S)"

echo "=== Create backend live dashboard override ==="
cat > "$BACKEND/app/routers/monitoring_cards_fix_v4.py" <<'PY'
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/dashboard", tags=["monitoring-cards-fix-v4"])

def good(v):
    return str(v or "").lower() in ("yes", "online", "ok", "running", "true", "1", "on")

def parse_json(v, fallback):
    if not v:
        return fallback
    try:
        return json.loads(v) if isinstance(v, str) else v
    except Exception:
        return fallback

def minutes_ago(dt):
    if not dt:
        return 999999
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return 999999
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60)

@router.get("/centers-live")
def centers_live_fixed(db: Session = Depends(get_db)):
    centers = db.execute(text("""
        SELECT *
        FROM health_centers
        ORDER BY name
    """)).mappings().all()

    output = []

    for hc in centers:
        foss_id = str(hc.get("foss_id") or "")

        local = db.execute(text("""
            SELECT *
            FROM source_agent_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        cloud = db.execute(text("""
            SELECT *
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

        last_seen = local.get("sent_at") or local.get("created_at") or hc.get("last_seen")
        age = minutes_ago(last_seen)

        mysql_online = good(local.get("mysql_status")) or good(hc.get("mysql_status"))
        internet_online = good(local.get("internet_status")) or good(hc.get("internet_status"))
        backend_online = age <= 3

        io_ok = good(cloud.get("io_running")) or good(local.get("io_running"))
        sql_ok = good(cloud.get("sql_running")) or good(local.get("sql_running"))

        is_online = backend_online and mysql_online and internet_online
        is_replication_ok = io_ok and sql_ok

        if is_online and is_replication_ok:
            status = "online"
            success_rate = 100
            risk_score = 0
            health_score = 100
        elif is_online:
            status = "partial"
            success_rate = 70
            risk_score = 30
            health_score = 70
        else:
            status = "offline"
            success_rate = 0
            risk_score = 100
            health_score = 0

        important_rows = parse_json(local.get("important_table_rows"), {})
        table_summary = parse_json(local.get("local_table_summary_json"), [])

        orders_today = 0
        if isinstance(important_rows, dict):
            orders_today = int(important_rows.get("orders") or 0)

        db_size = (
            local.get("database_size_mb")
            or local.get("local_size_mb")
            or integrity.get("local_size_mb")
            or hc.get("data_size_mb")
            or 0
        )

        row = {
            **dict(hc),

            "id": hc.get("id"),
            "name": hc.get("name"),
            "health_center_name": hc.get("name"),
            "foss_id": foss_id,
            "db_name": local.get("db_name") or hc.get("database_name"),
            "database_name": local.get("database_name") or local.get("db_name") or hc.get("database_name"),
            "channel_name": local.get("channel_name") or cloud.get("channel_name") or hc.get("replication_channel"),

            "status": status,
            "internet_status": "online" if internet_online else "offline",
            "mysql_status": "online" if mysql_online else "offline",
            "cloud_connection": "online" if backend_online else "failed",
            "backend_connection": "online" if backend_online else "failed",
            "local_server_reachable": backend_online,

            "io_running": "Yes" if io_ok else "No",
            "sql_running": "Yes" if sql_ok else "No",
            "replica_io": "Yes" if io_ok else "No",
            "replica_sql": "Yes" if sql_ok else "No",
            "seconds_behind": cloud.get("seconds_behind") or local.get("seconds_behind") or 0,
            "last_io_error": cloud.get("last_io_error") or local.get("last_io_error") or "",
            "last_sql_error": cloud.get("last_sql_error") or local.get("last_sql_error") or "",

            "cpu_usage": float(local.get("cpu_usage") or hc.get("cpu_usage") or 0),
            "ram_usage": float(local.get("ram_usage") or hc.get("ram_usage") or 0),
            "disk_usage": float(local.get("disk_usage") or hc.get("disk_usage") or 0),

            "database_size_mb": float(db_size or 0),
            "local_size_mb": float(db_size or 0),
            "data_size_mb": float(db_size or 0),
            "local_rows_count": int(local.get("local_rows_count") or integrity.get("local_rows_count") or 0),
            "local_table_count": int(local.get("local_table_count") or integrity.get("local_table_count") or 0),
            "local_table_summary_json": table_summary,

            "orders_today": orders_today,
            "success_rate": success_rate,
            "risk_score": risk_score,
            "health_score": health_score,

            "last_seen": str(last_seen) if last_seen else None,
            "last_data_timestamp": str(local.get("latest_local_time") or local.get("local_latest_time") or last_seen) if (local.get("latest_local_time") or local.get("local_latest_time") or last_seen) else None,
            "last_updated": str(cloud.get("checked_at") or cloud.get("created_at") or last_seen) if (cloud.get("checked_at") or cloud.get("created_at") or last_seen) else None,

            "replication": {
                "io_running": "Yes" if io_ok else "No",
                "sql_running": "Yes" if sql_ok else "No",
                "seconds_behind": cloud.get("seconds_behind") or 0,
                "last_io_error": cloud.get("last_io_error") or "",
                "last_sql_error": cloud.get("last_sql_error") or "",
            }
        }

        output.append(row)

    return output
PY

echo "=== Register override before existing dashboard router ==="
python3 - <<'PY'
from pathlib import Path

p = Path("/opt/medisoft-guardian-v3/backend/app/main.py")
s = p.read_text()

if "monitoring_cards_fix_v4" not in s:
    s = s.replace(
        "import app.routers.dashboard as dashboard",
        "import app.routers.monitoring_cards_fix_v4 as monitoring_cards_fix_v4\nimport app.routers.dashboard as dashboard"
    )

if "app.include_router(monitoring_cards_fix_v4.router" not in s:
    s = s.replace(
        "app.include_router(dashboard.router, prefix=settings.api_v1_prefix)",
        "app.include_router(monitoring_cards_fix_v4.router, prefix=settings.api_v1_prefix)\napp.include_router(dashboard.router, prefix=settings.api_v1_prefix)"
    )

p.write_text(s)
PY

echo "=== Rename Cloud Connection label to Backend Connection ==="
python3 - <<'PY'
from pathlib import Path

p = Path("/opt/medisoft-guardian-v3/src/pages/Monitoring.tsx")
s = p.read_text()
s = s.replace("Cloud Connection", "Backend Connection")
p.write_text(s)
PY

echo "=== Restart backend ==="
sudo systemctl restart medisoft-guardian-v4-backend
sleep 3

echo "=== Rebuild frontend ==="
cd "$APP"
npm run build -- --base=/v3/
sudo systemctl restart medisoft-guardian-v3-frontend
sudo systemctl reload nginx

echo "=== Test live data ==="
curl -s http://127.0.0.1:8004/api/v1/dashboard/centers-live | jq '.[0] | {
  name,
  status,
  backend_connection,
  cloud_connection,
  io_running,
  sql_running,
  orders_today,
  success_rate,
  risk_score,
  health_score
}'

echo "DONE ✅"
echo "Open /v3/monitoring and hard refresh: Ctrl + Shift + R"
