# Full Integration Plan — Local Agent + Replica Guardian + Frontend

Login is already fixed: `admin` / `kabuyedm`. Your three scripts are copied to `backend/agent_scripts/` so the backend can serve them as downloads.

## 1. Agent → Backend contract (from your scripts)

Every health-center server posts every ~30s to:

`POST /api/v1/hybrid/source-report`

Payload (verbatim from `new_local-installer.sh`):
```
foss_id, health_center_name, db_name, channel_name, hostname,
mysql_status, internet_status, cloud_connection, vpn_status,
cpu_usage, ram_usage, disk_usage, database_size_mb,
source_config_ok, connected_replicas, replica_hosts,
io_running, sql_running,
local_row_count, local_latest_time, sent_at
```

Response may contain `{"action": "restart_mysql"}` — the agent will self-heal.

## 2. Backend work (FastAPI + MySQL)

New / updated files:

- `backend/sql/upgrades_v3.sql` — tables: `source_reports` (rolling), `agent_actions` (queued commands), keep existing `sms_logs`.
- `backend/app/routers/hybrid_source.py` — `POST /hybrid/source-report` upserts a `health_centers` row by `foss_id`, stores latest snapshot, broadcasts WS `source_report`, queues pending action from `agent_actions` and returns it.
- `backend/app/routers/agent_control.py` — admin endpoints:
  - `POST /agent/{foss_id}/restart-mysql`
  - `POST /agent/{foss_id}/restart-replica`
  - `POST /agent/{foss_id}/reset-replica`
  - `POST /agent/{foss_id}/custom` (free-form action queued for next poll)
- `backend/app/routers/installer.py` — `GET /installer/{kind}` streams the three scripts (`local-agent`, `guardian`, `replication`) for one-click download.
- `backend/app/services/alert_engine.py` — runs every 60s:
  - If `now - last_seen > 3 min` → mark **offline** + send SMS to head-of-center + admins (Africa's Talking via existing `sms_service`).
  - If `io_running != "Yes"` or `sql_running != "Yes"` → SMS admins with HC name, contact, AnyDesk/RustDesk, AI suggestion.
  - Records every send in `sms_logs` (already exists).
- Register routers + scheduler in `app/main.py`.

## 3. Frontend work

- **Login** — already updated to `kabuyedm`.
- **Dashboard** — add "Live Agents" strip showing each `foss_id` with CPU/RAM/disk gauges, IO/SQL pills, last-seen badge; powered by `source_report` WS event.
- **HealthCenterDetail** (currently broken — holds RegisterHealthCenter content) → rewrite as real detail page with tabs: Overview · Replication · Resources · SMS log · **Actions** (Restart MySQL / Restart Replica / Reset Replica / Auto-Heal / AI Diagnose).
- **New page `/installers`** — three download cards (Local Agent, Guardian, Replication Setup) hitting `/installer/{kind}` with copy-paste install one-liner.
- **SmsLogs** — add filter chips (delivered/failed/pending) and per-row "Resend" already wired.
- **Alerts** — surface offline + replica-down rows with the SMS-status icons (sent/failed/not-sent).
- **Animations** — keep current `page-enter` / `card-lift`; add a subtle pulsing dot on live agents.

## 4. New env vars (backend `.env`)
Already documented in `BACKEND_GUIDE_v2.md`: `AT_USERNAME`, `AT_API_KEY`, `AT_SENDER_ID`, `ADMIN_PHONE_NUMBERS`, `LOVABLE_API_KEY`.

## 5. Out of scope (won't touch unless asked)
- The shell scripts themselves — kept verbatim as you sent them.
- Grafana embed page — already done.
- Auth tables / RLS.

## What you do after I ship
1. `mysql -u root -p medisoft_central < backend/sql/upgrades_v3.sql`
2. Restart FastAPI.
3. On each HC server, run the installer (now downloadable from `/installers`).

Confirm and I'll build it.
