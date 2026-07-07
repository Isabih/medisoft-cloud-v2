from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, func
from app.core.database import Base


class SourceAgentReport(Base):
    __tablename__ = "source_agent_reports"

    id = Column(Integer, primary_key=True, index=True)
    foss_id = Column(String(64), index=True, nullable=False)

    db_name = Column(String(128), nullable=True)
    channel_name = Column(String(128), nullable=True)
    hostname = Column(String(255), nullable=True)

    mysql_status = Column(String(32), nullable=False, default="unknown")
    internet_status = Column(String(32), nullable=False, default="unknown")
    cloud_connection = Column(String(32), nullable=False, default="unknown")

    cpu_usage = Column(Float, nullable=False, default=0)
    ram_usage = Column(Float, nullable=False, default=0)
    disk_usage = Column(Float, nullable=False, default=0)

    database_size_mb = Column(Float, nullable=False, default=0)
    local_size_mb = Column(Float, nullable=False, default=0)
    local_table_count = Column(Integer, nullable=False, default=0)
    local_rows_count = Column(Integer, nullable=False, default=0)
    local_latest_time = Column(DateTime, nullable=True)
    agent_version = Column(String(50), nullable=True)

    source_config_ok = Column(Boolean, nullable=False, default=False)
    connected_replicas = Column(Integer, nullable=False, default=0)
    replica_hosts_json = Column(Text, nullable=True)

    io_running = Column(String(16), nullable=False, default="No")
    sql_running = Column(String(16), nullable=False, default="No")
    seconds_behind = Column(Float, nullable=True)

    last_io_error = Column(Text, nullable=True)
    last_sql_error = Column(Text, nullable=True)

    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CloudReplicaReport(Base):
    __tablename__ = "cloud_replica_reports"

    id = Column(Integer, primary_key=True, index=True)
    foss_id = Column(String(64), index=True, nullable=False)

    db_name = Column(String(128), nullable=True)
    channel_name = Column(String(128), nullable=True)
    source_host = Column(String(255), nullable=True)

    io_running = Column(String(16), nullable=False, default="No")
    sql_running = Column(String(16), nullable=False, default="No")
    seconds_behind = Column(Float, nullable=True)

    last_io_error = Column(Text, nullable=True)
    last_sql_error = Column(Text, nullable=True)

    health_center_id = Column(String(36), nullable=True)
    health_center_name = Column(String(255), nullable=True)
    cloud_database_size_mb = Column(Float, nullable=False, default=0)
    cloud_table_count = Column(Integer, nullable=False, default=0)
    cloud_rows_count = Column(Integer, nullable=False, default=0)
    cloud_latest_time = Column(DateTime, nullable=True)
    source_log_file = Column(String(255), nullable=True)
    read_source_log_pos = Column(Integer, nullable=True)
    relay_log_file = Column(String(255), nullable=True)
    relay_log_pos = Column(Integer, nullable=True)
    raw_json = Column(Text, nullable=True)
    collected_at = Column(DateTime, nullable=True)

    checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HybridDiagnosis(Base):
    __tablename__ = "hybrid_diagnoses"

    id = Column(Integer, primary_key=True, index=True)
    foss_id = Column(String(64), index=True, nullable=False)

    severity = Column(String(32), nullable=False, default="info")
    diagnosis_code = Column(String(128), nullable=False, default="unknown")
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)

    probable_cause = Column(Text, nullable=True)
    recommended_actions_json = Column(Text, nullable=True)

    confidence = Column(Float, nullable=False, default=0.5)

    source_report_id = Column(Integer, ForeignKey("source_agent_reports.id"), nullable=True)
    cloud_report_id = Column(Integer, ForeignKey("cloud_replica_reports.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)