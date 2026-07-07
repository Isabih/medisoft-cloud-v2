# Backend production readiness checklist

## Keep
- `app/`
- `requirements.txt`
- `run.py`
- `.env.example`
- `sql/`

## Delete from deployment packages
- `venv/`
- `.env`
- `__pycache__/`
- `.DS_Store`
- `__MACOSX/`
- throwaway files like `hello.txt`

## Before production
1. Confirm both routes exist in live OpenAPI:
   - `/api/v1/hybrid/source-report`
   - `/api/v1/local-status/report`
2. Keep FastAPI bound to `127.0.0.1:8004` and use nginx as the public `/api/` entrypoint.
3. Use `API_BASE_URL=http://YOUR_SERVER_IP_OR_DOMAIN` in agents, not `:8004`.
4. Replace `Base.metadata.create_all()` with migrations when schema starts changing frequently.
5. Verify `health_centers` rows have correct `foss_id`, `database_name`, and `replication_channel` values.
6. Test these manually before rollout:
   - `POST /api/v1/hybrid/source-report`
   - `POST /api/v1/local-status/report`
   - `GET /api/v1/hybrid/centers/summary`
   - `GET /api/v1/local-status`
7. Put the backend behind a systemd service and verify nginx proxying to `127.0.0.1:8004`.

## Notes on this updated package
- Local status now accepts `foss_id`, `db_name`, `channel_name`, and `hostname` as identifiers.
- Local status can map `cloud_connection` into `backend_status` automatically.
- `run.py` now respects `.env` host/port settings.
- Config now supports `APP_NAME`, `CORS_ORIGINS`, and `AUTO_CREATE_TABLES`.
