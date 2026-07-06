# Medisoft Guardian Cloud v1.1 Enterprise

## New in v1.1: Database Integrity & Drift Health

This release adds local-vs-cloud database comparison so the platform does not only show whether SQL and IO are running. It also checks whether data appears healthy and aligned between the health-centre server and the cloud replica.

### Added features

- Local database size reported by agent.
- Local table count reported by agent.
- Local row count for configured check table.
- Local latest update timestamp for configured check table.
- Cloud database size calculated on the cloud server.
- Cloud table count calculated on the cloud server.
- Cloud row count for the same configured check table.
- Cloud latest update timestamp for the same configured check table.
- Database integrity score from 0-100.
- Drift status: healthy, minor_drift, major_drift, critical_drift.
- AI-style probable cause and recommended fix for database drift.
- Dashboard Database Integrity panel.
- Health centre table DB Health column.
- Prometheus metrics for Grafana:
  - medisoft_database_integrity_score
  - medisoft_database_rows_difference
  - medisoft_database_size_difference_mb
  - medisoft_database_drift_detected

### Required migration

```bash
mysql -u root -p medisoft_central < backend/sql/upgrades_v11_database_integrity.sql
```

### Local agent

Install the included v1.1 local agent on each health centre server:

```bash
sudo bash local-agent-install.sh
```

The agent sends data directly to:

```text
/api/v1/hybrid/source-report
```

### Important environment values

In the local agent env file:

```env
CHECK_TABLE_NAME=address
CHECK_TIME_COLUMN=updated_at
```

Change those if your real production table is better, for example orders, patients, encounters, or transactions.

### Safe monitoring strategy

v1.1 avoids heavy full-row comparison every minute. It uses lightweight checks every heartbeat and stores historical integrity checks. Deep checksum comparison should be added later as a manual or nightly job.
