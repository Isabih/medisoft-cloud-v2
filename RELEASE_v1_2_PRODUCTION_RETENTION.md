# Medisoft Guardian Cloud v1.2 Production Retention Update

This update makes the monitoring database production-safe.

## Added

- Automatic detailed monitoring cleanup after 7 days.
- Compact `incident_history` table for long-term offline/failure history.
- Manual retention cleanup endpoint: `POST /api/v1/retention/run`.
- Retention status endpoint: `GET /api/v1/retention/status`.
- Reports page: Incident History view for 90-day and custom date ranges.
- Settings page: Retention tab.
- SQL upgrade: `backend/sql/upgrades_v12_retention_incidents.sql`.
- Log rotation for `/var/log/medisoft-guardian.log`.

## Policy

Detailed raw records are deleted after 7 days by default:

- `source_agent_reports`
- `cloud_replica_reports`
- `local_status_reports`
- `hybrid_diagnoses`
- `heartbeat_logs`
- `database_metrics`
- resolved alerts older than the detailed window

Before deletion, failures are preserved in `incident_history`, so admins can still see how many times each health centre/database went offline over the last 3 months or more.

## Install/upgrade

```bash
mysql -u root -p central_monitoring < backend/sql/upgrades_v12_retention_incidents.sql
sudo systemctl restart medisoft-guardian-backend
```

Run cleanup manually once after upgrade:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/retention/run
```
