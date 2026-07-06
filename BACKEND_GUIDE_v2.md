# Medisoft Backend — Integration Notes (v2)

This complements `BACKEND_GUIDE.md`. The frontend now expects these new
endpoints and behaviours. Drop the included files into `backend/app/` and
register the routers in `app/main.py`.

## 1. Run the SQL upgrade

```bash
mysql -u root -p medisoft_central < backend/sql/upgrades_v2.sql
```

Creates: `sms_logs`, `ai_diagnoses`, `admin_notifications`.

## 2. New env vars (backend/.env)

```
# Africa's Talking
AT_USERNAME=sandbox          # or your live username
AT_API_KEY=atsk_xxx
AT_SENDER_ID=MEDISOFT        # optional, alphanumeric
ADMIN_PHONE_NUMBERS=+250788123456,+250788654321

# Lovable AI Gateway (auto-provisioned in the Lovable workspace).
# Copy the value from Lovable → Workspace Settings → Secrets
LOVABLE_API_KEY=lvl_xxx

# Grafana
GRAFANA_BASE_URL=http://localhost:3000
```

## 3. Register new routers in `app/main.py`

```python
from app.routers.sms import router as sms_router
from app.routers.ai_diagnose import router as ai_router
from app.routers.metrics_prometheus import router as metrics_router
from app.services.retention_service import start_retention_scheduler

app.include_router(sms_router, prefix="/api/v1")
app.include_router(ai_router,  prefix="/api/v1")
app.include_router(metrics_router)   # serves /metrics for Prometheus

@app.on_event("startup")
def _startup():
    start_retention_scheduler()
```

Add to `backend/requirements.txt`:

```
apscheduler>=3.10
requests>=2.31
```

## 4. New endpoints expected by the frontend

| Method | Path                                              | Purpose                       |
|--------|---------------------------------------------------|-------------------------------|
| POST   | `/api/v1/replication-guardian/repair/{channel}`   | Auto-heal (already existed)   |
| POST   | `/api/v1/ai/diagnose`                             | AI root-cause + fix steps     |
| GET    | `/api/v1/sms/logs?center_id=&limit=`              | Outbound SMS history          |
| POST   | `/api/v1/sms/{id}/resend`                         | Re-send a failed SMS          |
| GET    | `/metrics`                                        | Prometheus exporter           |

## 5. Auto-heal behaviour to implement / extend

In `app/services/replication_guardian_service.py::repair_channel`:

```python
def repair_channel(db, channel_name):
    steps = []
    # 1. Stop replica
    run("STOP REPLICA FOR CHANNEL %s", channel_name); steps.append("STOP REPLICA")
    # 2. Inspect last_io_error / last_sql_error
    err = fetch_status(channel_name)
    if "Lost connection" in err.get("io_error", ""):
        run("RESET REPLICA FOR CHANNEL %s", channel_name); steps.append("RESET REPLICA")
    if "duplicate entry" in err.get("sql_error", "").lower():
        run("SET GLOBAL sql_slave_skip_counter=1"); steps.append("SKIP duplicate")
    # 3. Start replica
    run("START REPLICA FOR CHANNEL %s", channel_name); steps.append("START REPLICA")
    # 4. Re-check
    status = fetch_status(channel_name)
    return {"success": status["io"] == "Yes" and status["sql"] == "Yes",
            "steps_taken": steps, "after": status}
```

## 6. SMS alert rules to wire in `alert_service`

```python
from app.services.sms_service import (
    notify_admins, notify_head_of_center, build_replica_down_message,
)

# Local server offline (no heartbeat > 2 × expected_sync_interval)
if hc.last_seen_age_min > 2 * hc.expected_sync_interval:
    msg = f"[MEDISOFT] {hc.name} local server appears OFFLINE since {hc.last_seen}."
    notify_head_of_center(db, hc.phone_number_1, msg, hc.id, hc.name)
    notify_admins(db, msg, hc.id, hc.name)

# Replica IO or SQL stopped → admins only
if rep.io_running != "Yes" or rep.sql_running != "Yes":
    ai_text = ai_diagnose_inline(db, hc.id)  # optional
    msg = build_replica_down_message(
        hc.name, hc.phone_contact_1,
        rep.io_running, rep.sql_running,
        hc.anydesk_id, hc.rustdesk_id,
        rep.last_io_error or rep.last_sql_error,
        ai_text,
    )
    notify_admins(db, msg, hc.id, hc.name)
```

## 7. Retention

`start_retention_scheduler()` runs **daily at 02:00 UTC** and deletes:
`heartbeat_logs`, `database_metrics`, `replication_status`, resolved `alerts`,
`sms_logs`, `ai_diagnoses`, `admin_notifications` older than **7 days**.
Master data (`health_centers`, `monitored_databases`) is never touched.

## 8. Remove nightly zip backups

Whatever scheduled job currently zips full nightly dumps — disable it.
Backup *status* push from the local agents (`POST /api/v1/backup/report`)
stays as-is so the dashboard backup KPI keeps working.

## 9. WebSocket events the frontend now consumes

| Event              | When to emit                                                    |
|--------------------|-----------------------------------------------------------------|
| `data_ingest`      | On every agent push (heartbeat/metrics) — `{rows, bytes}`       |
| `sms_sent`         | After `send_sms`                                                |
| `sms_status`       | When you get an Africa's Talking delivery callback (optional)   |
| `ai_diagnosis_ready` | After `/ai/diagnose` produces a result                        |

Example:

```python
await ws_manager.broadcast({
    "type": "data_ingest",
    "center_id": hc.id,
    "rows": payload.local_row_count,
    "bytes": payload.size_bytes,
    "timestamp": datetime.utcnow().isoformat(),
})
```

## 10. Grafana

See `backend/grafana/README.md`.
