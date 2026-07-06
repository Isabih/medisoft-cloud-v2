from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.replication_guardian_service import repair_channel

router = APIRouter(prefix="/replication", tags=["replication"])


@router.post("/repair/{channel_name}")
def repair_replication(channel_name: str, db: Session = Depends(get_db)):
    try:
        result = repair_channel(db, channel_name)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/restart/{channel_name}")
def restart_replication(channel_name: str, db: Session = Depends(get_db)):
    db.execute(text("STOP REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
    db.execute(text("START REPLICA FOR CHANNEL :channel_name"), {"channel_name": channel_name})
    db.commit()
    return {"success": True, "message": "Replica restarted", "channel_name": channel_name}
