# Monitoring v4 admin API — development setup

The following endpoints require a separate administrator bearer token:
- POST /api/v1/monitoring-v4/collect-now
- GET /api/v1/monitoring-v4/registered-centers
- GET /api/v1/monitoring-v4/center-complete/{foss_id}

GET /api/v1/monitoring-v4/health remains public and reports only service liveness.

Generate a unique secret with `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`.
Set `MEDISOFT_MONITORING_ADMIN_TOKEN` securely in the backend service environment
(never commit the secret or put it in frontend code). Restart the backend only
during an approved deployment window. Without a configured secret, admin routes
return HTTP 503 by design. Invalid credentials return HTTP 401.

**Important:** This is a temporary service-to-service/admin boundary, not a
replacement for proper user sessions, RBAC, MFA, and auditing. Do not embed the
secret in a browser frontend or expose it to health-center users. Route browser
requests through an authenticated backend-for-frontend after implementing proper
user authorization.

The legacy login endpoint currently issues `dev-token`; do not reuse it as
the monitoring secret. Other existing endpoints need a separate authorization
audit before production deployment.

Tests: `cd backend && pytest tests/test_monitoring_v4_security.py`.

No MySQL replication configuration is modified by this change.
