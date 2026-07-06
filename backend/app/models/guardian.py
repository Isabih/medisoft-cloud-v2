import uuid
from sqlalchemy import Column, String, Integer, Numeric, Text, DateTime, Boolean, func
from app.core.database import Base


class ReplicationGuardianEvent(Base):
    __tablename__ = "replication_guardian_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=True)
    center_name = Column(String(255), nullable=True)
    channel_name = Column(String(100), nullable=False, index=True)
    source_host = Column(String(255), nullable=True)
    event_type = Column(String(50), nullable=False)  # observed/heal/manual_repair/alert/resolve
    classification = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False, default="observed")
    message = Column(Text, nullable=True)
    action_taken = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class LocalStatusReport(Base):
    __tablename__ = "local_status_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=True, index=True)
    center_name = Column(String(255), nullable=False, index=True)
    agent_status = Column(String(20), nullable=False, default="online")
    internet_status = Column(String(20), nullable=False, default="unknown")
    mysql_status = Column(String(20), nullable=False, default="unknown")
    backend_status = Column(String(20), nullable=True)
    cpu_usage = Column(Numeric(5, 2), default=0)
    ram_usage = Column(Numeric(5, 2), default=0)
    storage_usage = Column(Numeric(5, 2), default=0)
    local_row_count = Column(Integer, default=0)
    cloud_row_count = Column(Integer, default=0)
    local_latest_time = Column(DateTime, nullable=True)
    cloud_latest_time = Column(DateTime, nullable=True)
    compare_status = Column(String(20), nullable=False, default="unknown")
    comparison_message = Column(Text, nullable=True)
    sync_freshness_minutes = Column(Integer, nullable=True)
    reported_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class ReplicaEmergencyState(Base):
    __tablename__ = "replica_emergency_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=True)
    center_name = Column(String(255), nullable=True)
    channel_name = Column(String(100), nullable=False, unique=True, index=True)
    severity = Column(String(20), nullable=False, default="critical")
    classification = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    message = Column(Text, nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
