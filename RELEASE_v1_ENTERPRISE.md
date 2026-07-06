# Medisoft Guardian Cloud v1.0 Enterprise

This release wires Lovable-generated UI features to real production backend behavior.

## Cloud features working now

- Admin login with default bootstrap admin created by installer.
- Health centre auto-registration from local agent using FOSA ID.
- Dashboard live status for:
  - local server reachability / heartbeat freshness,
  - MySQL online/offline,
  - replica IO thread,
  - replica SQL thread,
  - CPU, RAM, disk,
  - database size and latest local data time.
- Operations Center summary and Rwanda map-ready coordinates.
- Health score 0-100 per health centre.
- Timeline events for agent registration, alerts, replication issues, and First Aid commands.
- Deterministic AI comments explaining root cause and fix steps even when no external AI key is configured.
- Optional Lovable AI Gateway if `LOVABLE_API_KEY` is configured.
- First Aid actions queued from dashboard and picked by local agent:
  - Restart MySQL,
  - Start Replica,
  - Stop Replica,
  - Restart Replica,
  - Reset Replica.
- SMS alerts through Intouch Rwanda settings.
- Email alerts through Resend settings.
- 7-day retention scheduler for heavy monitoring tables.
- Prometheus `/metrics` endpoint for Grafana.

## Future-version actions shown honestly

Some AI comments mention future-version actions such as remote network reset, safe log cleanup, and duplicate-key repair wizard. These are intentionally labeled as future actions unless a backend implementation exists.

## Cloud installation

```bash
git clone <repo-url>
cd health-center-monitor-main
sudo bash install.sh
```

Optional environment before running:

```bash
export DB_NAME=medisoft_central
export DB_USER=root
export DB_PASS='your_mysql_password'
export SERVER_NAME=guardian.yourdomain.rw
export ADMIN_USER=admin
export ADMIN_PASSWORD='StrongPasswordHere'
```

## Local health centre installation

Copy `local-agent-install.sh` to the local health centre server, then run:

```bash
sudo bash local-agent-install.sh
```

The installer will discover local databases, create a MySQL monitor user, install the systemd service, and start sending data directly to the cloud backend.

## Required dashboard settings after first login

Go to **Settings**:

- SMS Gateway: Intouch username, password, sender ID, admin phone numbers.
- Email Alerts: Resend API key, sender email, admin emails.

## Grafana

Grafana should use Prometheus as a data source. Prometheus scrapes:

```text
http://your-cloud-domain/metrics
```

Grafana does not collect health centre data directly; it visualizes metrics from the backend.
