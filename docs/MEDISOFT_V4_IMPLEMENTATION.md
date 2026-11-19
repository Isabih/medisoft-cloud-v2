# Medisoft v4 monitoring — implementation contract

Status: **development only**. This document does not deploy or change any replication channel.

## Non-negotiable safety boundaries
- Never run CHANGE REPLICATION SOURCE, RESET REPLICA, DROP DATABASE, skip transactions, or modify GTID/source coordinates from the monitoring workflow.
- Existing MySQL replication remains authoritative and untouched.
- Never classify stale or missing telemetry as healthy. Separate **unknown/unreachable** from **confirmed stopped**.
- Collect replica IO/SQL state on the **cloud replica**, and local MySQL/VPN/internet state on the **health-center agent**.
- Keep only the latest **verified hourly** backup per facility. Preserve the prior backup until its successor is fully verified and atomically published. No nightly schedule.
- Only compare the `orders` table, at a consistent replication checkpoint; counts alone cannot prove equality.
- Restrict patient-related data and raw MySQL error details to authorized roles. No patient records in emails or logs.

## Workstreams and acceptance criteria

### 1. Monitoring security and accurate status
- Authenticate each agent independently, rotate/revoke credentials, and authorize all administrative endpoints.
- Replace hardcoded connectivity and replication statuses with measured, timestamped checks.
- Collect agent heartbeat, local MySQL, VPN peer connectivity, internet reachability, CPU, RAM, disk, and agent version.
- Add explicit `healthy`, `degraded`, `critical`, `unreachable`, `unknown`, `recovering` states.
- Acceptance: an expired heartbeat never displays a healthy facility; missing cloud query permission displays `unknown`, not `SQL OFF`.

### 2. Incident lifecycle
- Detect confirmed IO/SQL OFF, backup overdue, and unreachable agents separately.
- Deduplicate incidents, record first/last seen, acknowledge and resolve after sustained healthy checks.
- Send immediate alerts and verified recovery notices; health-center users receive summaries, admins receive diagnostic details.
- Acceptance: intermittent connectivity does not generate repeated false recovery messages.

### 3. Hourly backup and downloads
- Upgrade the independent backup kit's receiver, runner, timer and installer together.
- Idempotent installation with service locking, existing key preservation and rollback.
- Store per-facility backup metadata: database, created/verified times, size, checksum, retries, last error.
- Allow admin download of retained hourly backup without deletion.
- Allow admin-created fresh MySQL export, with temporary-only cleanup after confirmed delivery or expiration.
- Acceptance: failed transfer retains the previous valid backup; rerun creates no duplicate timers.

### 4. Orders comparison
- Compare only `orders`, with consistent snapshot/checkpoint and chunked primary-key/checksum verification.
- Distinguish pending replication from confirmed divergence and unavailable comparison.
- Never automatically modify orders.
- Acceptance: matching counts but different row content is detected in test fixtures.

### 5. History and Grafana
- Persist time-stamped metrics; expose 24h/7d/30d views.
- Validate exporter, Prometheus scrape, Grafana data source, dashboards and service startup.
- Acceptance: graphs display collected measurements and no synthetic healthy values.

### 6. National map and reports
- Filter facility list/map by province, district, sector, status and FOSAID.
- Use verified coordinates only; facilities without coordinates stay in list.
- Send daily administrator email summarizing replica state, latest replica write, hourly backup, incidents and agent reachability.
- Acceptance: email failure is retried and recorded, without leaking patient data.

### 7. Agent rollout and audit
- Signed/versioned packages, staged rollout, automatic rollback, audit logs for sensitive actions.
- Acceptance: an unsuccessful upgrade restores the previous agent and does not touch replication.

## Existing code audit required before integration
- `backend/app/routers/monitoring_v4.py`: verify authentication on `/collect-now`, `/registered-centers`, `/center-complete/{foss_id}`; avoid exposing raw source/replica reports.
- `backend/app/services/monitoring_v4.py`: audit collection errors, freshness handling, and schema migrations before production startup.
- Audit existing agent report ingestion and any hardcoded statuses before trusting dashboard cards.
- Audit existing backup receiver's retention logic before changing the hourly timer.

## Rollout gates
1. Unit/integration tests with disposable MySQL databases.
2. Verify no replication configuration mutation and no production database deletion.
3. Test offline/online, SQL/IO failures, mismatched orders, backup failure, upgrade rollback.
4. Pilot one non-production facility; review logs and metrics.
5. Admin approval for production rollout. No automatic deployment from this branch.
