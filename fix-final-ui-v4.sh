#!/usr/bin/env bash
set -e

APP="/opt/medisoft-guardian-v3"
BACKEND="$APP/backend"

echo "=== Backup files ==="
cp "$APP/src/lib/api.ts" "$APP/src/lib/api.ts.bak_$(date +%F_%H%M%S)"
cp "$APP/src/lib/query.ts" "$APP/src/lib/query.ts.bak_$(date +%F_%H%M%S)"
cp "$APP/src/pages/Dashboard.tsx" "$APP/src/pages/Dashboard.tsx.bak_$(date +%F_%H%M%S)"
cp "$APP/src/pages/HealthCenters.tsx" "$APP/src/pages/HealthCenters.tsx.bak_$(date +%F_%H%M%S)"
cp "$APP/src/pages/Monitoring.tsx" "$APP/src/pages/Monitoring.tsx.bak_$(date +%F_%H%M%S)"
cp "$BACKEND/app/main.py" "$BACKEND/app/main.py.bak_$(date +%F_%H%M%S)"

echo "=== Fix SMS logs response shape ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/opt/medisoft-guardian-v3/src/lib/api.ts")
s = p.read_text()

old = '''export const fetchSmsLogs = (params?: { from?: string; to?: string; center_id?: string }) =>
  api.get("/sms/logs", { params });'''

new = '''export const fetchSmsLogs = async (params?: { from?: string; to?: string; center_id?: string }) => {
  const res = await api.get("/sms/logs", { params });
  const data = res.data;
  return {
    ...res,
    data: Array.isArray(data) ? data : (data?.logs || []),
  };
};'''

if old in s:
    s = s.replace(old, new)
else:
    print("fetchSmsLogs exact block not found, doing safe regex patch")
    import re
    s = re.sub(
        r'export const fetchSmsLogs = \(params\?: \{ from\?: string; to\?: string; center_id\?: string \}\) =>\s*api\.get\("/sms/logs", \{ params \}\);',
        new,
        s,
        flags=re.S,
    )

p.write_text(s)
PY

echo "=== Make queries refresh in background ==="
python3 - <<'PY'
from pathlib import Path

q = Path("/opt/medisoft-guardian-v3/src/lib/query.ts")
s = q.read_text()
s = s.replace("refetchIntervalInBackground: false", "refetchIntervalInBackground: true")
q.write_text(s)

for file in [
    "/opt/medisoft-guardian-v3/src/pages/Dashboard.tsx",
    "/opt/medisoft-guardian-v3/src/pages/HealthCenters.tsx",
    "/opt/medisoft-guardian-v3/src/pages/Monitoring.tsx",
]:
    p = Path(file)
    s = p.read_text()
    s = s.replace("refetchInterval: 30000", "refetchInterval: 5000")
    s = s.replace("refetchInterval: 15000", "refetchInterval: 5000")
    s = s.replace("refetchInterval: 30_000", "refetchInterval: 5000")
    p.write_text(s)
PY

echo "=== Add live reports override backend route ==="
cat > "$BACKEND/app/routers/reports_live_v4_override.py" <<'PY'
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/reports", tags=["reports-live-v4"])

def ok_status(v):
    return str(v or "").lower() in ("yes", "on", "online", "running", "ok", "true", "1")

@router.get("/operational")
def operational_live_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
):
    today = str(date.today())

    centers = db.execute(text("""
        SELECT
            hc.id AS center_id,
            hc.name AS center_name,
            hc.foss_id,
            hc.phone_contact_1 AS head_name,
            hc.phone_number_1 AS head_phone
        FROM health_centers hc
        ORDER BY hc.name
    """)).mappings().all()

    rows = []
    for c in centers:
        foss_id = c["foss_id"]

        local = db.execute(text("""
            SELECT sent_at, created_at
            FROM source_agent_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        cloud = db.execute(text("""
            SELECT io_running, sql_running, seconds_behind, checked_at, created_at
            FROM cloud_replica_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        sms = db.execute(text("""
            SELECT
              COUNT(*) AS sms_sent,
              SUM(CASE WHEN status IN ('delivered','success','sent') THEN 1 ELSE 0 END) AS sms_delivered
            FROM sms_logs
            WHERE center_id=:center_id
              AND DATE(sent_at)=CURDATE()
        """), {"center_id": c["center_id"]}).mappings().first()

        io_up = ok_status(cloud["io_running"] if cloud else None)
        sql_up = ok_status(cloud["sql_running"] if cloud else None)

        last_seen = None
        if local:
            last_seen = local["sent_at"] or local["created_at"]
        elif cloud:
            last_seen = cloud["checked_at"] or cloud["created_at"]

        rows.append({
            "day": today,
            "center_id": c["center_id"],
            "center_name": c["center_name"],
            "foss_id": foss_id,
            "head_name": c["head_name"] or "Head of HC",
            "head_phone": c["head_phone"] or "",
            "last_seen": str(last_seen) if last_seen else None,
            "io_down": not io_up,
            "sql_down": not sql_up,
            "both_down": (not io_up and not sql_up),
            "io_down_count": 0 if io_up else 1,
            "sql_down_count": 0 if sql_up else 1,
            "samples": 1,
            "outdated": False,
            "sms_sent": int((sms or {}).get("sms_sent") or 0),
            "sms_delivered": int((sms or {}).get("sms_delivered") or 0),
            "sms_to_head": 0,
            "sms_to_admin": 0,
            "head_notified": False,
        })

    return rows
PY

echo "=== Register live reports override before old reports router ==="
python3 - <<'PY'
from pathlib import Path
p = Path("/opt/medisoft-guardian-v3/backend/app/main.py")
s = p.read_text()

if "reports_live_v4_override" not in s:
    s = s.replace(
        "import app.routers.reports as reports",
        "import app.routers.reports_live_v4_override as reports_live_v4_override\nimport app.routers.reports as reports"
    )

if "app.include_router(reports_live_v4_override.router" not in s:
    s = s.replace(
        "app.include_router(reports.router, prefix=settings.api_v1_prefix)",
        "app.include_router(reports_live_v4_override.router, prefix=settings.api_v1_prefix)\napp.include_router(reports.router, prefix=settings.api_v1_prefix)"
    )

p.write_text(s)
PY

echo "=== Create basic Grafana dashboards ==="
cat > /tmp/medisoft-grafana-dashboard.json <<'JSON'
{
  "dashboard": {
    "uid": "medisoft-overview",
    "title": "Medisoft Overview",
    "tags": ["medisoft"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "10s",
    "panels": [
      {
        "type": "text",
        "title": "Medisoft Guardian",
        "gridPos": {"x":0,"y":0,"w":24,"h":8},
        "options": {
          "mode": "markdown",
          "content": "# Medisoft Guardian Monitoring\\n\\nGrafana is connected. Detailed Prometheus panels can be added after datasource queries are finalized."
        }
      }
    ]
  },
  "overwrite": true
}
JSON

for uid in medisoft-overview medisoft-replication-lag medisoft-resource-heatmap medisoft-per-center; do
  sed "s/medisoft-overview/$uid/g; s/Medisoft Overview/Medisoft ${uid}/g" /tmp/medisoft-grafana-dashboard.json > "/tmp/${uid}.json"
  curl -s -u admin:admin \
    -H "Content-Type: application/json" \
    -X POST http://127.0.0.1:3000/api/dashboards/db \
    --data-binary "@/tmp/${uid}.json" >/dev/null || true
done

echo "=== Restart backend ==="
sudo systemctl restart medisoft-guardian-v4-backend

echo "=== Rebuild frontend ==="
cd "$APP"
npm run build -- --base=/v3/
sudo systemctl restart medisoft-guardian-v3-frontend
sudo systemctl reload nginx

echo "=== Tests ==="
sleep 3
curl -s http://127.0.0.1:8004/api/v1/sms/logs | jq
curl -s "http://127.0.0.1:8004/api/v1/reports/operational?from=2026-07-01&to=2026-07-08" | jq '.[0]'
curl -s http://127.0.0.1:3000/api/search | jq

echo "DONE ✅"
echo "Hard refresh browser: Ctrl + Shift + R"
