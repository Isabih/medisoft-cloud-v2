import uuid
from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, func
from app.core.database import Base


class HeartbeatLog(Base):
    __tablename__ = "heartbeat_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=False)
    foss_id = Column(String(50), nullable=False)
    mysql_status = Column(String(20), nullable=False)
    internet_status = Column(String(20), nullable=False)
    cloud_connection = Column(String(20), nullable=False)
    cpu_usage = Column(Numeric(5, 2), default=0)
    ram_usage = Column(Numeric(5, 2), default=0)
    disk_usage = Column(Numeric(5, 2), default=0)
    received_at = Column(DateTime, server_default=func.now())


class DatabaseMetric(Base):
    __tablename__ = "database_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=False)
    table_name = Column(String(255), nullable=False)
    rows_count = Column(Integer, default=0)
    data_size_mb = Column(Numeric(10, 2), default=0)
    last_sync = Column(DateTime, nullable=True)
    date = Column(Date, nullable=True)