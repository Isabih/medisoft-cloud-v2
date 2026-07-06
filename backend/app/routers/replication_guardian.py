from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.replication_guardian_service import (
    guardian_events_payload,
    guardian_status_payload,
    repair_channel,
)

router = APIRouter(prefix="/replication-guardian", tags=["replication-guardian"])


@router.get("/status")
def replication_guardian_status(db: Session = Depends(get_db)):
    return guardian_status_payload(db)


@router.get("/events")
def replication_guardian_events(limit: int = 100, db: Session = Depends(get_db)):
    return guardian_events_payload(db, limit=limit)


@router.post("/repair/{channel_name}")
def replication_guardian_repair(channel_name: str, db: Session = Depends(get_db)):
    try:
        result = repair_channel(db, channel_name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
