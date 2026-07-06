# Medisoft Cloud — Complete Backend & Infrastructure Guide

## Table of Contents
1. [Architecture Overview](#architecture)
2. [Database Schema](#database-schema)
3. [API Reference](#api-reference)
4. [WebSocket Protocol](#websocket)
5. [Local Monitoring Agent](#local-agent)
6. [Prometheus Exporter](#prometheus)
7. [Grafana Dashboards](#grafana)
8. [Installation Scripts](#installation)
9. [Security & Roles](#security)

---

## 1. Architecture Overview <a id="architecture"></a>

```
┌──────────────────────┐     Agent pushes every 30-60s    ┌──────────────────────────┐
│  Local Health Center │ ──────────────────────────────── │  Cloud Server            │
│                      │     Heartbeat (30s)              │  (FastAPI + MySQL)       │
│  - MySQL Replica     │     Replication status (60s)     │                          │
│  - Monitoring Agent  │     DB metrics (5 min)           │  - central_monitoring DB │
│  - Backup cron       │     Nightly backup report        │  - WebSocket /ws/monitor │
│                      │                                  │  - Prometheus :9100      │
└──────────────────────┘                                  │  - JWT Auth              │
                                                          └──────────────────────────┘
                                                                   │
                                                          ┌────────┴────────┐
                                                          │  React Frontend │
                                                          │  (WebSocket +   │
                                                          │   Polling fallback)│
                                                          └─────────────────┘
                                                                   │
                                                          ┌────────┴────────┐
                                                          │  Grafana        │
                                                          │  (Prometheus    │
                                                          │   scrape)       │
                                                          └─────────────────┘
```

**CRITICAL RULE:** The monitoring system NEVER directly queries health center databases. All data is pushed by the local agent.

**Flow:**
1. Each HC runs a lightweight monitoring agent
2. Agent pushes heartbeat (30s), replication status (60s), DB metrics (5min), backup report (nightly)
3. Cloud server processes data, updates `central_monitoring` DB
4. WebSocket broadcasts changes to connected frontends
5. Prometheus exporter exposes metrics for Grafana
6. If no heartbeat in 120s → mark HC offline
7. If no backup by 07:00 → generate critical alert

---

## 2. Database Schema <a id="database-schema"></a>

### MySQL — `central_monitoring` database

```sql
-- =============================================
-- USERS & ROLES
-- =============================================
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE user_roles (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    user_id VARCHAR(36) NOT NULL,
    role ENUM('admin', 'user') NOT NULL,
    UNIQUE(user_id, role),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- =============================================
-- HEALTH CENTERS
-- =============================================
CREATE TABLE health_centers (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    name VARCHAR(255) NOT NULL,
    province VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    database_name VARCHAR(255) UNIQUE NOT NULL,
    foss_id VARCHAR(50) UNIQUE NOT NULL,
    has_real_foss_id BOOLEAN DEFAULT TRUE,
    registered_date DATE DEFAULT (CURDATE()),
    expected_sync_interval INT DEFAULT 15,
    last_seen TIMESTAMP NULL,
    last_sync TIMESTAMP NULL,
    last_failed_sync TIMESTAMP NULL,
    status ENUM('online', 'offline', 'partial') DEFAULT 'offline',
    internet_status ENUM('online', 'offline') DEFAULT 'offline',
    mysql_status ENUM('online', 'offline') DEFAULT 'offline',
    cloud_connection ENUM('ok', 'failed') DEFAULT 'failed',
    data_size_mb DECIMAL(10,2) DEFAULT 0,
    risk_score INT DEFAULT 0,
    success_rate DECIMAL(5,2) DEFAULT 0,
    avg_rows_per_sync INT DEFAULT 0,
    avg_data_size_mb DECIMAL(10,2) DEFAULT 0,
    cpu_usage DECIMAL(5,2) DEFAULT 0,
    ram_usage DECIMAL(5,2) DEFAULT 0,
    disk_usage DECIMAL(5,2) DEFAULT 0,
    anydesk_id VARCHAR(50) NULL,
    rustdesk_id VARCHAR(50) NULL,
    phone_number_1 VARCHAR(20) NULL,
    phone_contact_1 VARCHAR(100) NULL,
    phone_number_2 VARCHAR(20) NULL,
    phone_contact_2 VARCHAR(100) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- =============================================
-- MONITORED DATABASES (Replica tracking)
-- =============================================
CREATE TABLE monitored_databases (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    health_center_id VARCHAR(36) NOT NULL,
    database_name VARCHAR(255) NOT NULL,
    replica_status ENUM('ok', 'offline', 'partial') DEFAULT 'ok',
    rows_count INT DEFAULT 0,
    data_size_mb DECIMAL(10,2) DEFAULT 0,
    last_checked TIMESTAMP NULL,
    last_backup TIMESTAMP NULL,
    drift_detected BOOLEAN DEFAULT FALSE,
    UNIQUE(health_center_id, database_name),
    FOREIGN KEY (health_center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- Auto-populate when HC is registered:
-- INSERT INTO monitored_databases (health_center_id, database_name)
-- SELECT id, database_name FROM health_centers;

-- =============================================
-- REPLICATION STATUS LOG
-- =============================================
CREATE TABLE replication_status (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    io_running VARCHAR(10) NOT NULL,
    sql_running VARCHAR(10) NOT NULL,
    seconds_behind INT NULL,
    last_io_error TEXT NULL,
    last_sql_error TEXT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- HEARTBEAT LOGS
-- =============================================
CREATE TABLE heartbeat_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    foss_id VARCHAR(50) NOT NULL,
    mysql_status ENUM('online', 'offline') NOT NULL,
    internet_status ENUM('online', 'offline') NOT NULL,
    cloud_connection ENUM('ok', 'failed') NOT NULL,
    cpu_usage DECIMAL(5,2) DEFAULT 0,
    ram_usage DECIMAL(5,2) DEFAULT 0,
    disk_usage DECIMAL(5,2) DEFAULT 0,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- SYNC LOGS
-- =============================================
CREATE TABLE sync_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('success', 'failed', 'partial') NOT NULL,
    rows_synced INT DEFAULT 0,
    data_size_mb DECIMAL(10,2) DEFAULT 0,
    tables_synced TEXT NULL,
    error_message TEXT NULL,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- NIGHTLY BACKUPS
-- =============================================
CREATE TABLE backups (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    center_name VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    time TIME NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    file_size_mb DECIMAL(10,2) DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    status ENUM('success', 'failed') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- DATABASE METRICS (Top tables, per-table stats)
-- =============================================
CREATE TABLE database_metrics (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    rows_count INT DEFAULT 0,
    data_size_mb DECIMAL(10,2) DEFAULT 0,
    last_sync TIMESTAMP NULL,
    date DATE DEFAULT (CURDATE()),
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- SCHEMA DRIFT DETECTION
-- =============================================
CREATE TABLE drift_reports (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    database_name VARCHAR(255) NOT NULL,
    missing_columns TEXT NULL,       -- JSON array
    extra_columns TEXT NULL,         -- JSON array
    missing_rows INT DEFAULT 0,
    incorrect_fosaid BOOLEAN DEFAULT FALSE,
    offline_count INT DEFAULT 0,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- ALERTS
-- =============================================
CREATE TABLE alerts (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    center_id VARCHAR(36) NOT NULL,
    center_name VARCHAR(255) NOT NULL,
    type ENUM('no_sync','partial_sync','data_drop','backup_missing','replication_stopped','high_lag','drift_detected','heartbeat_missing') NOT NULL,
    message TEXT NOT NULL,
    severity ENUM('warning', 'critical') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    FOREIGN KEY (center_id) REFERENCES health_centers(id) ON DELETE CASCADE
);

-- =============================================
-- DAILY REPORTS (auto-generated)
-- =============================================
CREATE TABLE daily_reports (
    id VARCHAR(36) PRIMARY KEY DEFAULT (UUID()),
    date DATE UNIQUE NOT NULL,
    full_sync_centers INT DEFAULT 0,
    partial_centers INT DEFAULT 0,
    no_data_centers INT DEFAULT 0,
    total_data_volume_gb DECIMAL(10,4) DEFAULT 0,
    total_rows_synced INT DEFAULT 0,
    details JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================
-- SETTINGS
-- =============================================
CREATE TABLE settings (
    id INT PRIMARY KEY DEFAULT 1,
    day_close_time TIME DEFAULT '00:00:00',
    auto_generate_reports BOOLEAN DEFAULT TRUE,
    polling_interval INT DEFAULT 30,
    heartbeat_timeout_seconds INT DEFAULT 120,
    backup_check_time TIME DEFAULT '07:00:00',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
INSERT INTO settings (id) VALUES (1);

-- =============================================
-- INDEXES
-- =============================================
CREATE INDEX idx_sync_center ON sync_logs(center_id, timestamp);
CREATE INDEX idx_hb_center ON heartbeat_logs(center_id, received_at);
CREATE INDEX idx_backup_center ON backups(center_id, date);
CREATE INDEX idx_metrics_center ON database_metrics(center_id, date);
CREATE INDEX idx_repl_center ON replication_status(center_id, checked_at);
CREATE INDEX idx_drift_center ON drift_reports(center_id, checked_at);
CREATE INDEX idx_alerts_center ON alerts(center_id, created_at);
CREATE INDEX idx_monitored_hc ON monitored_databases(health_center_id);
```

---

## 3. API Reference <a id="api-reference"></a>

Base URL: `http://your-server:8000/api/v1`

### Health Check (no auth)
```
GET /health → { "status": "ok", "timestamp": "..." }
```

### Auth
```
POST /api/v1/auth/login
Body: { "username": "admin", "password": "pass" }
→ { "access_token": "...", "token_type": "bearer", "user": { "id", "username", "role" } }
```

### Health Centers (auth required)
```
GET    /api/v1/health-centers          → [HealthCenter]
GET    /api/v1/health-centers/{id}     → HealthCenter
POST   /api/v1/health-centers          → Register new HC
POST   /api/v1/health-centers/validate-db → { "exists": bool, "already_registered": bool }
```

### Monitored Databases (auth required)
```
GET    /api/v1/monitored-databases     → [MonitoredDatabase]
GET    /api/v1/monitored-databases/{id} → MonitoredDatabase
```

### Drift Detection (auth required)
```
GET    /api/v1/drift/reports           → [DriftReport]
GET    /api/v1/drift/reports/{center_id} → DriftReport
```

### Agent Endpoints (NO JWT — uses foss_id)

#### Heartbeat (every 30s)
```
POST /api/v1/heartbeat
{
  "foss_id": "FOSS-KIRWA",
  "mysql_status": "online",
  "internet_status": "online",
  "cloud_connection": "ok",
  "cpu_usage": 32,
  "ram_usage": 61,
  "disk_usage": 48,
  "sent_at": "2026-03-05T10:00:00Z"
}
```
**Server logic:**
1. Find HC by foss_id
2. Update: internet_status, mysql_status, cloud_connection, cpu/ram/disk_usage, last_seen = now()
3. Insert heartbeat_log
4. If NOW() - last_seen > 120s → set status = 'offline', generate alert
5. Broadcast via WebSocket: `{ type: "heartbeat", center_id, data }`

#### Replication Report (every 60s)
```
POST /api/v1/replication/report
{
  "foss_id": "FOSS-KIRWA",
  "io_running": "Yes",
  "sql_running": "Yes",
  "seconds_behind": 0,
  "last_io_error": "",
  "last_sql_error": "",
  "checked_at": "2026-03-05T10:00:00Z"
}
```
**Server logic:**
1. Determine sync status:
   - FULL: IO=Yes, SQL=Yes, seconds_behind ≤ 5
   - PARTIAL: IO or SQL running but lag > expected_sync_interval
   - OFFLINE: IO or SQL = No
2. Update HC status + monitored_databases.replica_status
3. Insert replication_status log
4. If status changed → generate alert + broadcast WebSocket
5. **Auto-repair:** If replica offline, attempt MySQL replication restart, log in sync_logs

#### Database Metrics (every 5 min)
```
POST /api/v1/metrics/database
{
  "foss_id": "FOSS-KIRWA",
  "top_tables": [
    {"name": "patients", "rows": 1250, "size_mb": 45.2},
    {"name": "consultations", "rows": 890, "size_mb": 32.1}
  ],
  "total_size_mb": 245.8
}
```

#### Latest Data Check
```
POST /api/v1/metrics/latest-data
{
  "foss_id": "FOSS-KIRWA",
  "last_order_time": "2026-03-05T10:09:58Z"
}
```

#### Backup Report (nightly)
```
POST /api/v1/backup/report
{
  "foss_id": "FOSS-KIRWA",
  "backup_date": "2026-03-05",
  "status": "success",
  "file_size_mb": 145.3,
  "duration_seconds": 42
}
```

### Dashboard (auth required)
```
GET /api/v1/dashboard/summary
GET /api/v1/dashboard/sync-activity
GET /api/v1/dashboard/alerts
GET /api/v1/dashboard/unregistered-dbs
```

### Reports (auth required)
```
GET /api/v1/reports/daily?from=...&to=...
GET /api/v1/reports/center/{center_id}?from=...&to=...
GET /api/v1/reports/download/{date}?format=pdf|excel
```

### Backups (auth required)
```
GET /api/v1/backups?center_id=...&from=...&to=...
GET /api/v1/backups/center/{center_id}
```

### Available Databases (auth required)
```
GET /api/v1/databases/available → [{ "schema_name": "pos_db" }]
```
Must exclude system DBs and already-registered DBs.

### Settings (admin only)
```
GET /api/v1/settings
PUT /api/v1/settings
```

---

## 4. WebSocket Protocol <a id="websocket"></a>

### Endpoint
```
ws://your-server:8000/ws/monitor?token=JWT_TOKEN
```

### Event Types
```json
{
  "type": "heartbeat|replication|backup|alert|metrics|status_change",
  "hc_name": "REMERA",
  "database_name": "remera_440",
  "center_id": "uuid",
  "data": { ... },
  "timestamp": "2026-03-05T10:00:00Z"
}
```

### FastAPI Implementation
```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import List
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    # Optional: validate token from query param
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

Then in your heartbeat/replication/backup handlers:
```python
await manager.broadcast({
    "type": "heartbeat",
    "center_id": center.id,
    "hc_name": center.name,
    "database_name": center.database_name,
    "data": payload.dict(),
    "timestamp": datetime.utcnow().isoformat()
})
```

---

## 5. Local Monitoring Agent <a id="local-agent"></a>

### agent.py (runs on each HC server)
```python
#!/usr/bin/env python3
"""Medisoft Local Monitoring Agent — runs on each health center server"""
import requests, time, subprocess, json, psutil, pymysql, traceback
from datetime import datetime

with open("/opt/medisoft-local/config.json") as f:
    cfg = json.load(f)

API = cfg["cloud_api"]
FOSS_ID = cfg["foss_id"]
HC_NAME = cfg["healthcenter_name"]
DB_NAME = cfg["database_name"]
DB_USER = cfg.get("mysql_user", "root")
DB_PASS = cfg.get("mysql_password", "")

def check_mysql():
    try:
        r = subprocess.run(["mysqladmin","ping","-u",DB_USER,f"--password={DB_PASS}","--silent"],
                          capture_output=True, timeout=5)
        return r.returncode == 0
    except:
        return False

def check_internet():
    try:
        subprocess.run(["ping","8.8.8.8","-c","1","-W","2"], capture_output=True, timeout=5, check=True)
        return True
    except:
        return False

def check_cloud():
    try:
        r = requests.get(f"{API}/health", timeout=5)
        return r.status_code == 200
    except:
        return False

def get_replication_status():
    try:
        conn = pymysql.connect(host='localhost', user=DB_USER, password=DB_PASS)
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SHOW REPLICA STATUS")
            row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "io_running": row.get("Replica_IO_Running", row.get("Slave_IO_Running", "No")),
            "sql_running": row.get("Replica_SQL_Running", row.get("Slave_SQL_Running", "No")),
            "seconds_behind": row.get("Seconds_Behind_Source", row.get("Seconds_Behind_Master")),
            "last_io_error": row.get("Last_IO_Error", ""),
            "last_sql_error": row.get("Last_SQL_Error", ""),
        }
    except Exception as e:
        print(f"Replication check error: {e}")
        return None

def get_db_metrics():
    try:
        conn = pymysql.connect(host='localhost', user=DB_USER, password=DB_PASS, db=DB_NAME)
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT table_name, table_rows, ROUND(data_length/1024/1024, 2) AS size_mb
                FROM information_schema.tables
                WHERE table_schema = %s
                ORDER BY table_rows DESC LIMIT 10
            """, (DB_NAME,))
            tables = cur.fetchall()
            cur.execute("""
                SELECT ROUND(SUM(data_length)/1024/1024, 2) AS total
                FROM information_schema.tables WHERE table_schema = %s
            """, (DB_NAME,))
            total = cur.fetchone()
        conn.close()
        return {
            "top_tables": [{"name": t["table_name"], "rows": t["table_rows"] or 0, "size_mb": float(t["size_mb"] or 0)} for t in tables],
            "total_size_mb": float(total["total"] or 0)
        }
    except:
        return None

def get_latest_order():
    try:
        conn = pymysql.connect(host='localhost', user=DB_USER, password=DB_PASS, db=DB_NAME)
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(time) FROM orders")
            row = cur.fetchone()
        conn.close()
        return row[0].isoformat() if row and row[0] else None
    except:
        return None

def post(endpoint, data):
    try:
        requests.post(f"{API}{endpoint}", json=data, timeout=10)
    except Exception as e:
        print(f"Failed to post {endpoint}: {e}")

# Main loop
heartbeat_interval = cfg.get("heartbeat_interval", 30)
replication_interval = cfg.get("replication_interval", 60)
metrics_interval = cfg.get("metrics_interval", 300)

last_replication = 0
last_metrics = 0

while True:
    now = time.time()
    ts = datetime.utcnow().isoformat()

    # Heartbeat (every 30s)
    mysql_ok = check_mysql()
    internet_ok = check_internet()
    cloud_ok = check_cloud()

    post("/heartbeat", {
        "foss_id": FOSS_ID,
        "mysql_status": "online" if mysql_ok else "offline",
        "internet_status": "online" if internet_ok else "offline",
        "cloud_connection": "ok" if cloud_ok else "failed",
        "cpu_usage": psutil.cpu_percent(),
        "ram_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "sent_at": ts,
    })

    # Replication check (every 60s)
    if now - last_replication >= replication_interval:
        rep = get_replication_status()
        if rep:
            post("/replication/report", {
                "foss_id": FOSS_ID, **rep, "checked_at": ts
            })
        last_replication = now

    # DB metrics (every 5 min)
    if now - last_metrics >= metrics_interval:
        metrics = get_db_metrics()
        if metrics:
            post("/metrics/database", {"foss_id": FOSS_ID, **metrics})

        # Latest order time
        lot = get_latest_order()
        if lot:
            post("/metrics/latest-data", {"foss_id": FOSS_ID, "last_order_time": lot})

        last_metrics = now

    time.sleep(heartbeat_interval)
```

### nightly_backup.sh
```bash
#!/bin/bash
source /opt/medisoft-local/config.env 2>/dev/null
CLOUD_API=$(python3 -c "import json;print(json.load(open('/opt/medisoft-local/config.json'))['cloud_api'])")
FOSS_ID=$(python3 -c "import json;print(json.load(open('/opt/medisoft-local/config.json'))['foss_id'])")
DB_NAME=$(python3 -c "import json;print(json.load(open('/opt/medisoft-local/config.json'))['database_name'])")
DB_USER=$(python3 -c "import json;print(json.load(open('/opt/medisoft-local/config.json')).get('mysql_user','root'))")
DB_PASS=$(python3 -c "import json;print(json.load(open('/opt/medisoft-local/config.json')).get('mysql_password',''))")

DATE=$(date +%Y-%m-%d)
FILE="${DB_NAME}_backup_${DATE}.sql.gz"
DIR="/var/backups/medisoft"
mkdir -p $DIR

START=$(date +%s)
mysqldump -u $DB_USER --password="$DB_PASS" --single-transaction --quick $DB_NAME | gzip > "$DIR/$FILE"
END=$(date +%s)
DURATION=$((END - START))

if [ $? -eq 0 ]; then
    SIZE=$(du -m "$DIR/$FILE" | cut -f1); STATUS="success"
else
    SIZE=0; STATUS="failed"
fi

curl -sX POST "$CLOUD_API/backup/report" -H "Content-Type: application/json" \
  -d "{\"foss_id\":\"$FOSS_ID\",\"backup_date\":\"$DATE\",\"status\":\"$STATUS\",\"file_size_mb\":$SIZE,\"duration_seconds\":$DURATION}"

find $DIR -name "*.sql.gz" -mtime +7 -delete
```

Cron: `0 2 * * * /opt/medisoft-local/nightly_backup.sh >> /var/log/medisoft-backup.log 2>&1`

### config.json
```json
{
  "cloud_api": "https://your-cloud-server.com/api/v1",
  "foss_id": "FOSS-001",
  "healthcenter_name": "kirwa",
  "database_name": "kirwa_new",
  "heartbeat_interval": 30,
  "replication_interval": 60,
  "metrics_interval": 300,
  "mysql_user": "root",
  "mysql_password": "",
  "backup_dir": "/var/backups/medisoft"
}
```

### Systemd Service
```ini
# /etc/systemd/system/medisoft-agent.service
[Unit]
Description=Medisoft Monitoring Agent
After=network.target mysql.service

[Service]
Type=simple
User=medisoft
ExecStart=/usr/bin/python3 /opt/medisoft-local/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 6. Prometheus Exporter <a id="prometheus"></a>

### prometheus_exporter.py
```python
#!/usr/bin/env python3
"""Medisoft Prometheus Exporter — exposes metrics for Grafana"""
from prometheus_client import start_http_server, Gauge
import pymysql
import time
import threading

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'db': 'central_monitoring',
    'cursorclass': pymysql.cursors.DictCursor
}

# Prometheus metrics
replica_status_g = Gauge('medisoft_db_replica_status', 'Replica status (1=ok, 0=offline)',
                         ['hc_name', 'database_name'])
rows_count_g = Gauge('medisoft_db_rows_count', 'Number of rows in monitored DB',
                     ['hc_name', 'database_name'])
data_size_g = Gauge('medisoft_db_size_mb', 'Size of database in MB',
                    ['hc_name', 'database_name'])
last_checked_g = Gauge('medisoft_db_last_checked', 'Unix timestamp of last check',
                       ['hc_name', 'database_name'])
backup_status_g = Gauge('medisoft_backup_status', 'Backup success (1=ok, 0=failed)',
                        ['hc_name', 'database_name'])
cpu_usage_g = Gauge('medisoft_cpu_usage', 'CPU usage percent', ['hc_name'])
ram_usage_g = Gauge('medisoft_ram_usage', 'RAM usage percent', ['hc_name'])
disk_usage_g = Gauge('medisoft_disk_usage', 'Disk usage percent', ['hc_name'])
seconds_behind_g = Gauge('medisoft_seconds_behind', 'Replication seconds behind', ['hc_name', 'database_name'])

def update_metrics():
    while True:
        try:
            conn = pymysql.connect(**DB_CONFIG)
            with conn.cursor() as cur:
                # Monitored databases
                cur.execute("""
                    SELECT m.database_name, h.name AS hc_name, m.replica_status,
                           m.rows_count, m.data_size_mb, UNIX_TIMESTAMP(m.last_checked) AS ts
                    FROM monitored_databases m
                    JOIN health_centers h ON h.id = m.health_center_id
                """)
                for r in cur.fetchall():
                    labels = [r['hc_name'], r['database_name']]
                    replica_status_g.labels(*labels).set(1 if r['replica_status'] == 'ok' else 0)
                    rows_count_g.labels(*labels).set(r['rows_count'])
                    data_size_g.labels(*labels).set(r['data_size_mb'])
                    last_checked_g.labels(*labels).set(r['ts'] or 0)

                # HC resources
                cur.execute("SELECT name, cpu_usage, ram_usage, disk_usage FROM health_centers")
                for r in cur.fetchall():
                    cpu_usage_g.labels(r['name']).set(r['cpu_usage'] or 0)
                    ram_usage_g.labels(r['name']).set(r['ram_usage'] or 0)
                    disk_usage_g.labels(r['name']).set(r['disk_usage'] or 0)

                # Latest replication lag
                cur.execute("""
                    SELECT h.name AS hc_name, h.database_name, rs.seconds_behind
                    FROM health_centers h
                    JOIN replication_status rs ON rs.center_id = h.id
                    WHERE rs.id IN (
                        SELECT MAX(id) FROM replication_status GROUP BY center_id
                    )
                """)
                for r in cur.fetchall():
                    seconds_behind_g.labels(r['hc_name'], r['database_name']).set(r['seconds_behind'] or -1)

                # Backup status (latest per center)
                cur.execute("""
                    SELECT h.name AS hc_name, h.database_name, b.status
                    FROM health_centers h
                    LEFT JOIN backups b ON b.center_id = h.id AND b.id = (
                        SELECT MAX(id) FROM backups WHERE center_id = h.id
                    )
                """)
                for r in cur.fetchall():
                    backup_status_g.labels(r['hc_name'], r['database_name']).set(
                        1 if r['status'] == 'success' else 0
                    )

            conn.close()
        except Exception as e:
            print(f"Metrics update error: {e}")
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=update_metrics, daemon=True).start()
    start_http_server(9100)
    print("Prometheus exporter running on :9100")
    while True:
        time.sleep(3600)
```

### Systemd Service
```ini
# /etc/systemd/system/medisoft-prometheus.service
[Unit]
Description=Medisoft Prometheus Exporter
After=network.target mysql.service

[Service]
Type=simple
User=medisoft
ExecStart=/usr/bin/python3 /opt/medisoft-backend/prometheus_exporter.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Prometheus Config (prometheus.yml)
```yaml
scrape_configs:
  - job_name: 'medisoft'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:9100']
```

---

## 7. Grafana Dashboards <a id="grafana"></a>

### Recommended Panels

| Panel | Type | Metric | Alert Rule |
|-------|------|--------|------------|
| Replica Status Overview | Table/Heatmap | `medisoft_db_replica_status` | `== 0` → Offline |
| Heartbeat Last Seen | Time Series | `medisoft_db_last_checked` | `time() - value > 180` → Missing |
| Database Size | Time Series | `medisoft_db_size_mb` | Abnormal growth |
| Rows Count | Time Series | `medisoft_db_rows_count` | `== 0` → Empty/drift |
| Backup Status | Table | `medisoft_backup_status` | `== 0` → Failed |
| CPU/RAM/Disk | Gauge | `medisoft_cpu/ram/disk_usage` | `> 90` → Critical |
| Replication Lag | Time Series | `medisoft_seconds_behind` | `> 60` → High lag |

### Import JSON
```json
{
  "annotations": { "list": [] },
  "panels": [
    {
      "type": "table", "title": "Replica Status",
      "targets": [{ "expr": "medisoft_db_replica_status", "format": "table" }]
    },
    {
      "type": "graph", "title": "Replication Lag",
      "targets": [{ "expr": "medisoft_seconds_behind", "legendFormat": "{{hc_name}}" }]
    },
    {
      "type": "graph", "title": "Database Size (MB)",
      "targets": [{ "expr": "medisoft_db_size_mb", "legendFormat": "{{hc_name}}" }]
    },
    {
      "type": "graph", "title": "Rows Count",
      "targets": [{ "expr": "medisoft_db_rows_count", "legendFormat": "{{hc_name}}" }]
    },
    {
      "type": "table", "title": "Backup Status",
      "targets": [{ "expr": "medisoft_backup_status", "format": "table" }]
    },
    {
      "type": "gauge", "title": "CPU Usage",
      "targets": [{ "expr": "medisoft_cpu_usage", "legendFormat": "{{hc_name}}" }]
    },
    {
      "type": "gauge", "title": "RAM Usage",
      "targets": [{ "expr": "medisoft_ram_usage", "legendFormat": "{{hc_name}}" }]
    }
  ],
  "schemaVersion": 36, "version": 1
}
```

### Grafana Alerting Rules
```yaml
groups:
  - name: medisoft
    rules:
      - alert: ReplicaOffline
        expr: medisoft_db_replica_status == 0
        for: 1m
        labels: { severity: critical }
        annotations: { summary: "Replica offline: {{ $labels.hc_name }}" }

      - alert: HeartbeatMissing
        expr: time() - medisoft_db_last_checked > 180
        for: 0m
        labels: { severity: critical }
        annotations: { summary: "No heartbeat: {{ $labels.hc_name }}" }

      - alert: BackupFailed
        expr: medisoft_backup_status == 0
        for: 0m
        labels: { severity: warning }
        annotations: { summary: "Backup failed: {{ $labels.hc_name }}" }

      - alert: HighCPU
        expr: medisoft_cpu_usage > 90
        for: 5m
        labels: { severity: warning }
        annotations: { summary: "High CPU: {{ $labels.hc_name }}" }

      - alert: EmptyDatabase
        expr: medisoft_db_rows_count == 0
        for: 5m
        labels: { severity: critical }
        annotations: { summary: "Empty DB: {{ $labels.hc_name }}" }

      - alert: HighReplicationLag
        expr: medisoft_seconds_behind > 60
        for: 2m
        labels: { severity: warning }
        annotations: { summary: "High lag ({{ $value }}s): {{ $labels.hc_name }}" }
```

---

## 8. Installation Scripts <a id="installation"></a>

### Backend: install_backend.sh
```bash
#!/bin/bash
set -e
echo "=== Medisoft Backend Installer ==="
sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv mysql-server nginx
INSTALL_DIR="/opt/medisoft-backend"
sudo mkdir -p $INSTALL_DIR && sudo chown $USER $INSTALL_DIR && cd $INSTALL_DIR
python3 -m venv venv && source venv/bin/activate
cat > requirements.txt << 'EOF'
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pymysql==1.1.1
cryptography==44.0.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
pydantic==2.10.3
pydantic-settings==2.7.0
alembic==1.14.0
python-dotenv==1.0.1
websockets==12.0
prometheus-client==0.21.0
EOF
pip install -r requirements.txt
echo "Backend installed. Configure .env and run: uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

### Frontend: install_frontend.sh
```bash
#!/bin/bash
set -e
echo "=== Medisoft Frontend Installer ==="
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
cd medisoft-frontend
npm install
npm run build
echo "Built! Copy dist/ to /var/www/medisoft/"
echo "Nginx config:"
echo "  location / { try_files \$uri /index.html; }"
echo "  location /api/ { proxy_pass http://127.0.0.1:8000; }"
echo "  location /ws/ { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Upgrade \$http_upgrade; proxy_set_header Connection \"upgrade\"; }"
```

### Local Agent: install_local.sh
```bash
#!/bin/bash
set -e
echo "=== Medisoft Local Agent Setup ==="
sudo apt-get install -y python3 python3-pip
pip3 install requests pymysql psutil
INSTALL_DIR="/opt/medisoft-local"
sudo mkdir -p $INSTALL_DIR

read -p "Cloud API URL: " CLOUD_API
read -p "FOSS ID: " FOSS_ID
read -p "Health Center Name: " HC_NAME
read -p "Database Name: " DB_NAME
read -p "MySQL User [root]: " DB_USER; DB_USER=${DB_USER:-root}
read -sp "MySQL Password: " DB_PASS; echo

cat > $INSTALL_DIR/config.json << EOF
{
  "cloud_api": "$CLOUD_API",
  "foss_id": "$FOSS_ID",
  "healthcenter_name": "$HC_NAME",
  "database_name": "$DB_NAME",
  "heartbeat_interval": 30,
  "replication_interval": 60,
  "metrics_interval": 300,
  "mysql_user": "$DB_USER",
  "mysql_password": "$DB_PASS",
  "backup_dir": "/var/backups/medisoft"
}
EOF

# Copy agent.py and nightly_backup.sh to $INSTALL_DIR
# Setup systemd service + backup cron
sudo systemctl daemon-reload
sudo systemctl enable medisoft-agent
sudo systemctl start medisoft-agent
echo "(crontab -l; echo '0 2 * * * $INSTALL_DIR/nightly_backup.sh >> /var/log/medisoft-backup.log 2>&1') | crontab -"
echo "Done! Agent running, backup cron set for 2 AM."
```

---

## 9. Security & Roles <a id="security"></a>

| Endpoint | Admin | User | Agent (no JWT) |
|---|---|---|---|
| GET /health-centers | ✅ | ✅ | — |
| POST /health-centers | ✅ | ✅ | — |
| GET /dashboard/* | ✅ | ✅ | — |
| GET /reports/* | ✅ | ✅ | — |
| GET /monitored-databases | ✅ | ✅ | — |
| GET /drift/reports | ✅ | ✅ | — |
| PUT /settings | ✅ | ❌ | — |
| DELETE anything | ✅ | ❌ | — |
| POST /heartbeat | — | — | ✅ (foss_id) |
| POST /replication/report | — | — | ✅ (foss_id) |
| POST /metrics/* | — | — | ✅ (foss_id) |
| POST /backup/report | — | — | ✅ (foss_id) |
| WS /ws/monitor | ✅ | ✅ | — |

### Admin User Setup
```sql
-- Password: kabuyedm (bcrypt hash)
INSERT INTO users (id, username, hashed_password, is_active)
VALUES (UUID(), 'admin', '$2b$12$LJ3m4ys3Lk0T8nOtn9C5/.q3K8HzV8UJF5S3XQrPn8JnYxZ5NXWWK', TRUE);

INSERT INTO user_roles (id, user_id, role)
SELECT UUID(), id, 'admin' FROM users WHERE username = 'admin';
```

---

## Quick Start

1. **Cloud Server:** `bash install_backend.sh` → API on :8000, WS on :8000/ws/monitor, Prometheus on :9100
2. **Frontend:** `bash install_frontend.sh` → Nginx serves dist/ with WS proxy
3. **Each HC:** `bash install_local.sh` → agent + backup cron
4. **Grafana:** Import dashboard JSON, configure Prometheus datasource → scrape :9100
5. **Login** with admin/kabuyedm → Dashboard auto-updates via WebSocket
