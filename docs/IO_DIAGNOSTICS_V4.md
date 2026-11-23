# Medisoft v4 — IO diagnostics and recovery notification

Development branch only. No production deployment has occurred.

## Behavior
- Each collector cycle reads `SHOW REPLICA STATUS FOR CHANNEL` and uses the real cloud-side IO state/error.
- When IO is Connecting/Off, the cloud performs a **2-second TCP probe** to the source host and port reported by MySQL. Fresh agent reports provide internet, VPN and local MySQL observations.
- The dashboard `GET /api/v1/dashboard/centers-live` includes `io_diagnostics`: cause, confidence, evidence, suggested solution, incident state, and email timestamp.
- Missing replica status is **unknown**, not IO OFF.
- An IO recovery email is attempted after **two consecutive successful collector checks** following a known active incident. Email is not sent on initial healthy startup.
- SQL thread and lag are **not** considered recovered just because IO is running.
- No automatic `START REPLICA`, `STOP REPLICA`, `RESET REPLICA`, `CHANGE REPLICATION SOURCE`, or source modifications.

## SMTP settings (backend service environment; never commit secrets)
- `MEDISOFT_RECOVERY_EMAIL_TO`: comma-separated administrator recipient addresses.
- `MEDISOFT_SMTP_HOST`: SMTP hostname.
- `MEDISOFT_SMTP_PORT`: 587 (STARTTLS) or 465 (TLS).
- `MEDISOFT_SMTP_FROM`: verified sender address.
- `MEDISOFT_SMTP_USER` and `MEDISOFT_SMTP_PASSWORD`: optional SMTP credentials.

When SMTP is not configured, the incident is retained and email is pending for a later collector check. A failed send is logged and retried. Configure the recipient list carefully; the current implementation sends only to the configured admin recipients, not per-center recipients.

## Safety and limitations
- TCP success proves a socket handshake, **not** successful MySQL replication authentication or a healthy VPN.
- A failed internet check alone does not prove the replication path is broken.
- Current dashboard returns only redacted diagnostic fields; raw MySQL errors may contain sensitive information and must remain restricted.
- The dashboard route still needs full session/RBAC integration before deployment. Existing legacy login issues remain.
- Email send and DB commit are not atomic: a rare crash between delivery and commit can produce a duplicate notification. Use an outbox with message IDs for production-grade exactly-once-like delivery.
- The current collector creates the incident metadata table with `CREATE TABLE IF NOT EXISTS`. Validate schema migration and DB privileges in staging.
- Monitoring currently does expensive whole-database row counts; performance review is required before rollout.
- Test and validate with staging MySQL replicas, an SMTP test inbox, and deliberate connectivity faults. Do not simulate failures on production channels.

Run tests from `backend` with `pytest tests/test_io_diagnostics_v4.py`.
