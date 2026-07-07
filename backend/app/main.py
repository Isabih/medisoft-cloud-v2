import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.routers.cloud import router as cloud_router
import app.routers.hybrid_monitoring as hybrid_monitoring
import app.routers.sms_logs as sms_logs

from app.models.user import User, UserRole
from app.models.health_center import HealthCenter, MonitoredDatabase
from app.models.replication import ReplicationStatus
from app.models.alert import Alert
from app.models.backup import Backup
from app.models.metrics import HeartbeatLog, DatabaseMetric
from app.models.settings import Setting
from app.models.hybrid_monitoring import SourceAgentReport, CloudReplicaReport, HybridDiagnosis
from app.models.guardian import ReplicationGuardianEvent, LocalStatusReport, ReplicaEmergencyState

import app.routers.auth as auth
import app.routers.dashboard as dashboard
import app.routers.alerts as alerts
import app.routers.health_centers as health_centers
import app.routers.monitored_databases as monitored_databases
import app.routers.backups as backups
import app.routers.reports as reports
import app.routers.settings as settings_router
import app.routers.sync as sync
import app.routers.websocket as websocket
import app.routers.databases as databases
import app.routers.replication_guardian as replication_guardian
import app.routers.local_status as local_status
import app.routers.replication_actions as replication_actions
import app.routers.hybrid_source as hybrid_source
import app.routers.agent_control as agent_control
import app.routers.installer as installer
import app.routers.audit as audit
import app.routers.system_health as system_health
import app.routers.operations as operations
import app.routers.timeline as timeline
import app.routers.agent_version as agent_version
import app.routers.metrics_prometheus as metrics_prometheus
import app.routers.ai_diagnose as ai_diagnose
import app.routers.database_integrity as database_integrity
import app.routers.local_server_commands as local_server_commands
import app.routers.cloud_admin_commands as cloud_admin_commands
import app.routers.retention as retention
import app.routers.monitoring_v4 as monitoring_v4

from app.services.alert_engine import start_alert_engine
from app.services.retention_service import start_retention_scheduler
from app.services.monitoring_v4 import start_monitoring_v4

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)
else:
    logger.info("AUTO_CREATE_TABLES disabled; expecting schema to be created via migrations.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/health")
def api_health():
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(alerts.router, prefix=settings.api_v1_prefix)
app.include_router(health_centers.router, prefix=settings.api_v1_prefix)
app.include_router(monitored_databases.router, prefix=settings.api_v1_prefix)
app.include_router(backups.router, prefix=settings.api_v1_prefix)
app.include_router(reports.router, prefix=settings.api_v1_prefix)
app.include_router(settings_router.router, prefix=settings.api_v1_prefix)
app.include_router(sync.router, prefix=settings.api_v1_prefix)
app.include_router(websocket.router)
app.include_router(databases.router, prefix=settings.api_v1_prefix)
app.include_router(replication_guardian.router, prefix=settings.api_v1_prefix)
app.include_router(local_status.router, prefix=settings.api_v1_prefix)
app.include_router(replication_actions.router, prefix=settings.api_v1_prefix)
app.include_router(cloud_router, prefix=settings.api_v1_prefix)
app.include_router(hybrid_monitoring.router)
app.include_router(hybrid_source.router, prefix=settings.api_v1_prefix)
app.include_router(agent_control.router, prefix=settings.api_v1_prefix)
app.include_router(installer.router, prefix=settings.api_v1_prefix)
app.include_router(audit.router, prefix=settings.api_v1_prefix)
app.include_router(system_health.router, prefix=settings.api_v1_prefix)
app.include_router(operations.router, prefix=settings.api_v1_prefix)
app.include_router(timeline.router, prefix=settings.api_v1_prefix)
app.include_router(agent_version.router, prefix=settings.api_v1_prefix)
app.include_router(ai_diagnose.router, prefix=settings.api_v1_prefix)
app.include_router(database_integrity.router, prefix=settings.api_v1_prefix)
app.include_router(local_server_commands.router, prefix=settings.api_v1_prefix)
app.include_router(cloud_admin_commands.router, prefix=settings.api_v1_prefix)
app.include_router(retention.router, prefix=settings.api_v1_prefix)
app.include_router(metrics_prometheus.router)
app.include_router(sms_logs.router, prefix=settings.api_v1_prefix)
app.include_router(monitoring_v4.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def _start_background():
    try:
        start_alert_engine()
    except Exception as exc:
        logger.warning("alert engine could not start: %s", exc)
    try:
        start_retention_scheduler()
    except Exception as exc:
        logger.warning("retention scheduler could not start: %s", exc)
    try:
        start_monitoring_v4()
    except Exception as exc:
        logger.warning("monitoring v4 scheduler could not start: %s", exc)
 