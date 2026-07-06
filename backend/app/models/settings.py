from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    day_close_time = Column(String(20), default="00:00:00")
    auto_generate_reports = Column(Boolean, default=True)
    polling_interval = Column(Integer, default=30)
    heartbeat_timeout_seconds = Column(Integer, default=120)
    backup_check_time = Column(String(20), default="07:00:00")