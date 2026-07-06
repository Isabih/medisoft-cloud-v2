import uuid
from sqlalchemy import Column, String, Integer, Numeric, Date, Time, DateTime, func
from app.core.database import Base


class Backup(Base):
    __tablename__ = "backups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=False)
    center_name = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    file_name = Column(String(500), nullable=False)
    file_size_mb = Column(Numeric(10, 2), default=0)
    duration_seconds = Column(Integer, default=0)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())