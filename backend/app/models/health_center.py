import uuid
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, func
from app.core.database import Base


class HealthCenter(Base):
    __tablename__ = "health_centers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    province = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    database_name = Column(String(255), unique=True, nullable=False)
    foss_id = Column(String(50), unique=True, nullable=False)

    replication_channel = Column(String(100), unique=True, nullable=True)
    source_host = Column(String(255), nullable=True)
    source_port = Column(Integer, default=3306)

    status = Column(String(20), default="offline")
    internet_status = Column(String(20), default="offline")
    mysql_status = Column(String(20), default="offline")
    cloud_connection = Column(String(20), default="failed")

    last_seen = Column(DateTime, nullable=True)
    last_data_timestamp = Column(DateTime, nullable=True)

    data_size_mb = Column(Numeric(10, 2), default=0)
    risk_score = Column(Integer, default=0)
    success_rate = Column(Numeric(5, 2), default=0)
    avg_rows_per_sync = Column(Integer, default=0)
    avg_data_size_mb = Column(Numeric(10, 2), default=0)

    cpu_usage = Column(Numeric(5, 2), default=0)
    ram_usage = Column(Numeric(5, 2), default=0)
    disk_usage = Column(Numeric(5, 2), default=0)

    anydesk_id = Column(String(50), nullable=True)
    rustdesk_id = Column(String(50), nullable=True)

    phone_number_1 = Column(String(30), nullable=True)
    phone_contact_1 = Column(String(100), nullable=True)
    phone_number_2 = Column(String(30), nullable=True)
    phone_contact_2 = Column(String(100), nullable=True)

    expected_sync_interval = Column(Integer, default=15)
    has_real_foss_id = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class MonitoredDatabase(Base):
    __tablename__ = "monitored_databases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    health_center_id = Column(String(36), nullable=False)
    database_name = Column(String(255), nullable=False)
    replica_status = Column(String(20), default="ok")
    rows_count = Column(Integer, default=0)
    data_size_mb = Column(Numeric(10, 2), default=0)
    last_checked = Column(DateTime, nullable=True)
    last_backup = Column(DateTime, nullable=True)
    drift_detected = Column(Boolean, default=False)
    backup_status = Column(String(20), nullable=True)