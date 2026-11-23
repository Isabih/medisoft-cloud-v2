# Medisoft v4 local development

## Clone and configure
```bash
git clone -b feature/medisoft-v4-monitoring https://github.com/Isabih/medisoft-cloud-v2.git
cd medisoft-cloud-v2
cp backend/.env.example backend/.env
```

Edit `backend/.env`. It is ignored by Git; `.env.example` contains placeholders only.

### Option A: Connect local backend to existing cloud MySQL
1. Connect your Mac/Linux machine to the private network (for example, Tailscale).
2. Configure `DATABASE_URL=mysql+pymysql://USER:PASSWORD@PRIVATE_CLOUD_HOST:3306/DATABASE` in `backend/.env`.
3. Use a dedicated least-privilege account. The current backend contains endpoints and background collectors that **write** monitoring tables; do **not** use a production account or production database for local development without first disabling/isolating these jobs and reviewing migrations.
4. Keep `AUTO_CREATE_TABLES=false` to prevent SQLAlchemy from automatically creating its model tables on startup. **Note:** the monitoring collector has its own migration logic and must be disabled or isolated separately; this setting alone does not make the application read-only.
5. Do not expose MySQL port 3306 to the public internet; use a private VPN.

### Option B: Local MySQL for safe development
Create a separate disposable development database and account with appropriate local privileges, then set:
```dotenv
DATABASE_URL=mysql+pymysql://local_monitor_user:REPLACE_PASSWORD@127.0.0.1:3306/medisoft_monitor_dev
AUTO_CREATE_TABLES=true
```
Never reuse a production replication channel or overwrite an existing health-center database.

### Start backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8004 --reload
```
Check `http://127.0.0.1:8004/api/v1/health`.

### Frontend
The frontend's actual API configuration must be checked before selecting its environment variable name. The backend default CORS list allows local port 8080. Do not place `SECRET_KEY`, database credentials, SMTP credentials, or the monitoring admin token in any `VITE_*` variable.

### Generate secrets locally
```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```
Generate a different value for each secret. If you have already committed credentials, rotate them.

### Deployment safety
This branch is not production-ready: legacy authentication and collector authorization require further work, and migrations/monitoring jobs must be audited. Do not point a live production database at this development backend merely to preview the UI.
