from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.replication_guardian_service import (
    local_status_payload,
    save_local_status_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/local-status", tags=["local-status"])


class LocalStatusReportIn(BaseModel):
    foss_id: Optional[str] = None
    db_name: Optional[str] = None
    channel_name: Optional[str] = None
    hostname: Optional[str] = None

    health_center_name: Optional[str] = None
    center_name: Optional[str] = None

    cpu_usage: float = 0
    ram_usage: float = 0
    storage_usage: float = 0
    disk_usage: Optional[float] = None

    mysql_status: str = "unknown"
    internet_status: str = "unknown"
    backend_status: Optional[str] = None
    cloud_connection: Optional[str] = None

    local_row_count: int = 0
    local_latest_time: Optional[str] = None
    reported_at: Optional[str] = None

    @property
    def resolved_center_name(self) -> Optional[str]:
        return (
            self.health_center_name
            or self.center_name
            or self.hostname
            or self.db_name
            or self.channel_name
        )


@router.post("/report")
def local_status_report(payload: LocalStatusReportIn, db: Session = Depends(get_db)):
    try:
        data = payload.model_dump()

        if not data.get("health_center_name") and payload.resolved_center_name:
            data["health_center_name"] = payload.resolved_center_name

        if not data.get("backend_status"):
            data["backend_status"] = payload.cloud_connection or "unknown"

        if data.get("disk_usage") is None:
            data["disk_usage"] = data.get("storage_usage", 0)

        if not data.get("storage_usage") and data.get("disk_usage") is not None:
            data["storage_usage"] = data["disk_usage"]

        logger.info("LOCAL STATUS DATA: %s", data)

        return save_local_status_report(db, data)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to save local status report")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def local_status_list(db: Session = Depends(get_db)):
    try:
        return local_status_payload(db)
    except Exception as exc:
        logger.exception("Failed to fetch local status list")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {exc}")