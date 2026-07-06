# Medisoft Guardian Cloud v1.2 Command Center

This release separates command execution into two safety zones.

## 1. Health Centre / Local Server Commands

These commands affect only one selected local health-centre server. The cloud backend queues the command; the local agent pulls it and executes it locally.

Endpoints:

```text
POST /api/v1/local-servers/{server_id}/commands/restart-replica
POST /api/v1/local-servers/{server_id}/commands/start-sql
POST /api/v1/local-servers/{server_id}/commands/start-io
POST /api/v1/local-servers/{server_id}/commands/restart-mysql
POST /api/v1/local-servers/{server_id}/commands/{action}
GET  /api/v1/local-servers/{server_id}/commands
GET  /api/v1/local-servers/{server_id}/commands/next
POST /api/v1/local-servers/{server_id}/commands/{command_id}/result
```

Supported local actions:

```text
restart_mysql
start_replica
stop_replica
restart_replica
start_sql
start_io
stop_sql
stop_io
test_mysql
run_diagnostics
refresh_status
```

Every command should include the channel name when known:

```json
{
  "requested_by": "admin",
  "channel_name": "nyamata",
  "reason": "SQL thread stopped"
}
```

## 2. Cloud Admin Commands

These commands affect the central/cloud server only. They are disabled by default.

Endpoints:

```text
GET  /api/v1/cloud-admin/commands
POST /api/v1/cloud-admin/commands/{action}
```

Supported cloud actions:

```text
restart_backend
restart_frontend
restart_nginx
restart_grafana
restart_prometheus
restart_cloud_mysql
```

To enable cloud admin commands, set:

```env
ENABLE_CLOUD_ADMIN_COMMANDS=true
```

Cloud commands require:

```json
{
  "requested_by": "super_admin",
  "confirm": true,
  "reason": "maintenance"
}
```

## 3. Local Agent v3

New installer:

```bash
sudo bash medisoft-local-agent-install-v3.sh
```

It does not create replication, dump databases, upload dumps, or configure cloud replication.

It only:

- detects Tailscale IP
- detects database and FOSAID
- detects channel name
- creates MySQL monitor user
- posts heartbeat to cloud
- collects CPU/RAM/disk
- collects MySQL, SQL, IO, lag, database size, row/table summaries
- pulls local-server commands from backend
- executes first-aid actions locally
- reports command result back to backend

Use v2 replication setup for creating replication channels. Use v3 agent for monitoring and dashboard First Aid.
