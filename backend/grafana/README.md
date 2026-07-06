# Medisoft Grafana setup

## Start the stack

```bash
cd backend/grafana
docker compose -f docker-compose.grafana.yml up -d
```

Then open:
- Grafana  → http://localhost:3000  (anonymous viewer enabled, admin/admin to edit)
- Prometheus → http://localhost:9090

## Dashboards used by the in-app /grafana page

The React app expects these dashboard UIDs (configure them inside Grafana):

| UID                      | Title              | Recommended panels                              |
|--------------------------|--------------------|-------------------------------------------------|
| `medisoft-overview`      | Cluster Overview   | Online vs offline, lag heatmap, KPI tiles       |
| `medisoft-replication`   | Replication Lag    | `medisoft_replication_lag_seconds` per center   |
| `medisoft-resources`     | Resource Heatmap   | CPU / RAM / Disk per center                     |
| `medisoft-per-hc`        | Per-Health-Center  | Templated by `$center` variable                 |

When you create each dashboard, set the UID in Dashboard Settings → JSON Model
to match exactly.

## Metrics exposed by the FastAPI backend

`GET /metrics` (Prometheus text format):

- `medisoft_heartbeat_age_seconds{center,id}`
- `medisoft_cpu_usage_percent{center}`
- `medisoft_ram_usage_percent{center}`
- `medisoft_disk_usage_percent{center}`
- `medisoft_center_online{center}`
- `medisoft_replication_lag_seconds{center}`
- `medisoft_replication_io_running{center}`
- `medisoft_replication_sql_running{center}`
- `medisoft_sms_24h_total{status}`

## Embedding into the React app

In the app, go to **Settings → Grafana** (or use the gear icon on `/grafana`)
and set the Grafana base URL (default `http://localhost:3000`). The iframe
appends `?kiosk&theme=dark` so the chrome is hidden.

For production, put Grafana behind the same domain (or use a reverse proxy)
to avoid iframe / cookie / CORS issues.
