# Medisoft Cloud — Full Install & Run Guide

## 0. TL;DR — One-command install

After cloning the repo:

```bash
# On the CLOUD server (Ubuntu 22.04+, run as root):
git clone <this-repo> medisoft && cd medisoft
sudo DB_USER=root DB_PASS='yourpass' DB_NAME=central_monitoring \
     SERVER_NAME=medisoft.example.com bash install.sh

# On each HEALTH CENTER machine:
sudo bash local-agent-install.sh \
     --cloud https://medisoft.example.com \
     --foss  RW-12345 \
     --db    my_center_db
```

`install.sh` installs Python + Node + nginx + MySQL client, creates the venv,
applies **every** SQL migration in `backend/sql/`, builds the React frontend
into `/var/www/medisoft`, writes a `medisoft-backend` systemd unit, and
configures nginx to serve the SPA and proxy `/api` + `/ws` to FastAPI on
port 8000. Reach the app at `http://<server>/`.

`local-agent-install.sh` installs Tailscale, drops a heartbeat + safe
auto-update script at `/opt/medisoft-agent/`, and runs it every minute via a
systemd timer that also reports the agent version to the cloud.

---

This guide covers the **three environments** you need to bring online:

1. The **Cloud Server** (FastAPI + central MySQL + this React frontend)
2. Each **Health Center server** (Local Agent + Replica MySQL + Guardian)
3. The optional **Grafana + Prometheus** observability stack

Login to the frontend with `admin` / `kabuyedm` (dev default — change in
`src/lib/auth-config.ts` before going to production).

---

## 1. Cloud Server (one-time)

### 1.1 Requirements

- Ubuntu 22.04+ (or Debian 12+)
- Python 3.11+, MySQL 8.0+, Node 20+, nginx
- A public hostname (e.g. `medisoft.yourdomain.rw`) with HTTPS

### 1.2 Backend (FastAPI)

```bash
git clone <this repo> /opt/medisoft && cd /opt/medisoft/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — DB_HOST, DB_USER, DB_PASS, DB_NAME=medisoft_central,
# AT_USERNAME, AT_API_KEY, AT_SENDER_ID, ADMIN_PHONE_NUMBERS,
# LOVABLE_API_KEY, JWT_SECRET, CORS_ORIGINS
```

Create the central database and apply all migrations **in order**:

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS medisoft_central;"
mysql -u root -p medisoft_central < sql/upgrades.sql
mysql -u root -p medisoft_central < sql/upgrades_v2.sql
mysql -u root -p medisoft_central < sql/upgrades_v3.sql
mysql -u root -p medisoft_central < sql/upgrades_v4.sql   # audit_logs table
```

> The `audit_logs` table powers the **Audit Log** page in the UI. Every
> remote-agent action, SMS resend and backup update writes a row here so
> operators have a permanent who/what/when trail.

Run the API (dev):

```bash
python run.py            # binds 127.0.0.1:8000 by default
```

Production (systemd):

```ini
# /etc/systemd/system/medisoft-api.service
[Unit]
Description=Medisoft FastAPI
After=network.target mysql.service

[Service]
WorkingDirectory=/opt/medisoft/backend
ExecStart=/opt/medisoft/backend/venv/bin/python run.py
Restart=always
EnvironmentFile=/opt/medisoft/backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now medisoft-api
```

### 1.3 nginx + HTTPS

```nginx
server {
  server_name medisoft.yourdomain.rw;
  location /api/   { proxy_pass http://127.0.0.1:8000;
                     proxy_http_version 1.1;
                     proxy_set_header Upgrade $http_upgrade;
                     proxy_set_header Connection "upgrade"; }
  location /ws/    { proxy_pass http://127.0.0.1:8000;
                     proxy_http_version 1.1;
                     proxy_set_header Upgrade $http_upgrade;
                     proxy_set_header Connection "upgrade"; }
  location /       { root /opt/medisoft/dist; try_files $uri /index.html; }
}
```

Then: `sudo certbot --nginx -d medisoft.yourdomain.rw`.

### 1.4 Frontend

```bash
cd /opt/medisoft
npm install && npm run build
sudo rsync -a dist/ /var/www/medisoft/  # or serve from nginx root above
```

In the running app, open **Settings → API base URL**. **Leave it blank**
when the frontend is served from the same nginx that proxies the backend —
the app will auto-use `window.location.origin + /api/v1`. Only set an
explicit value when the frontend and backend live on different hosts.

You can also bake the URL at build time with a `.env` file in the repo root:

```bash
echo "VITE_API_BASE_URL=https://medisoft.yourdomain.rw/api/v1" > .env
npm run build
```

### 1.5 Post-install verification — System Health page

After bringing the API and frontend up, log into the UI and open
**System Health** in the sidebar (or `/system-health`). It calls
`GET /api/v1/system/health-check` and validates:

- Database connectivity (latency in ms)
- Required API routes registered (`/auth`, `/dashboard`, `/hybrid/source-report`,
  `/installer`, `/audit`, `/sms`, `/ws/monitor`, …)
- WebSocket manager state + active connection count
- `agent_commands` queue table (needed for remote Restart MySQL / Replica)
- `audit_logs` + `sms_logs` tables
- SMS gateway env vars (`AT_USERNAME`, `AT_API_KEY`, `ADMIN_PHONE_NUMBERS`)

A green "All systems operational" badge means the install is ready for
health-center agents to connect. Any red row prints the exact error and
the hint to fix it (e.g. "Run sql/upgrades_v3.sql to create agent_commands").

### 1.6 Smoke tests (CLI)

```bash
curl -fsS https://medisoft.yourdomain.rw/api/v1/health
curl -fsS https://medisoft.yourdomain.rw/api/v1/installer
curl -fsS https://medisoft.yourdomain.rw/api/v1/system/health-check | jq .ok
```

---

## 2. Health Center Server (per site)

Each health-center machine runs:

- The site's **production MySQL** (already in place — Medisoft FOSS)
- A **MySQL replica** that streams changes to the cloud central DB
- The **Local Agent** that pushes a heartbeat every 30 s to `/api/v1/hybrid/source-report`
- The **Replica Guardian** that auto-restarts the replica when it stalls

### 2.1 One-click install (recommended)

From the cloud frontend, open **Installers** in the sidebar. For each script
copy the one-liner — for example:

```bash
curl -fsSL https://medisoft.yourdomain.rw/api/v1/installer/local-agent  -o agent.sh && sudo bash agent.sh
curl -fsSL https://medisoft.yourdomain.rw/api/v1/installer/guardian     -o guard.sh && sudo bash guard.sh
curl -fsSL https://medisoft.yourdomain.rw/api/v1/installer/replication  -o repl.sh  && sudo bash repl.sh
```

Each script prompts for the missing values: `FOSS_ID`, `HEALTH_CENTER_NAME`,
local MySQL credentials, and the cloud API URL. They write a systemd unit
and start it immediately.

### 2.2 Order to install

1. `replication` — creates the replication channel from the site's MySQL to
   the cloud central DB.
2. `local-agent` — starts pushing telemetry. Within ~30 s the HC appears on
   the **Health Centers** page.
3. `guardian` — keeps the replica healthy and listens for queued
   actions (Restart MySQL / Restart Replica / Reset Replica) issued from the
   detail page in the cloud UI.

### 2.3 Verify

```bash
systemctl status medisoft-agent medisoft-guardian
journalctl -u medisoft-agent -f
```

In the cloud UI:

- The HC appears on **Health Centers** with green Status / Internet / MySQL /
  IO / SQL pills and a fresh **Last seen** timestamp.
- Open the HC → **Overview** tab — the 24 h heartbeat timeline starts
  filling. The legend explains Healthy / Partial / Failure and the SMS dot.
- Click **Actions → Restart Replica** to queue a remote command and watch
  the agent execute it on the next poll.

---

## 3. Grafana + Prometheus (optional but recommended)

```bash
cd /opt/medisoft/backend/grafana
docker compose -f docker-compose.grafana.yml up -d
```

This brings up:

- Prometheus on `:9090` scraping `host.docker.internal:8000/metrics`
- Grafana on `:3000` with anonymous viewer + iframe embedding enabled

Create four dashboards with the UIDs the app expects:

| UID                    | Title              |
|------------------------|--------------------|
| `medisoft-overview`    | Cluster Overview   |
| `medisoft-replication` | Replication Lag    |
| `medisoft-resources`   | Resource Heatmap   |
| `medisoft-per-hc`      | Per-Health-Center  |

For production, expose Grafana over the **same HTTPS domain** as the app —
e.g. `https://grafana.yourdomain.rw` — otherwise browsers will block the
iframe inside the Lovable preview / hosted frontend.

Finally, open **Grafana** in the sidebar, click **Configure**, paste the
public Grafana URL and **Save**. The "Test connection" button shows a green
"reachable" badge when the iframe will load.

---

## 4. SMS alerts (Africa's Talking)

Set these in `backend/.env`:

```
AT_USERNAME=sandbox            # or your live username
AT_API_KEY=...                 # from africastalking.com dashboard
AT_SENDER_ID=MEDISOFT          # optional
ADMIN_PHONE_NUMBERS=+2507xxxxxxxx,+2507yyyyyyyy
```

Alerts the backend sends automatically (see `alert_engine.py`):

- HC offline (>3 min without heartbeat) → admins + head of HC
- Replication IO or SQL down → admins
- Daily summary at 18:00 (configurable in `Settings → Alerts`)

All deliveries are logged to `sms_logs` and visible at **SMS Logs** in the
sidebar.

---

## 5. Updates & rollouts

- **Backend**: `git pull && systemctl restart medisoft-api`. Run any new
  `sql/upgrades_v*.sql` migrations in order.
- **Frontend**: `npm install && npm run build` and reload nginx.
- **Agents**: push a new version of the installer scripts into
  `backend/agent_scripts/` — health centers can re-run the one-liner from
  the **Installers** page to upgrade themselves.
