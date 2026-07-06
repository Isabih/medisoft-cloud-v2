import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime
from app.core.database import Base


class ReplicationStatus(Base):
    __tablename__ = "replication_status"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    center_id = Column(String(36), nullable=False)
    channel_name = Column(String(100))
    source_host = Column(String(255))
    io_running = Column(String(10), nullable=False)
    sql_running = Column(String(10), nullable=False)
    seconds_behind = Column(Integer)
    last_io_error = Column(Text)
    last_sql_error = Column(Text)
    checked_at = Column(DateTime)