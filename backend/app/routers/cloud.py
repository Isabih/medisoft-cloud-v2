import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/cloud/status")
def get_cloud_status():
    try:
        with Path(settings.cloud_status_file).open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Expected object")
        stamp = datetime.fromisoformat(str(data["last_updated"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        if age < -30 or age > 90:
            return {"monitoring_status": "stale", "last_updated": data["last_updated"],
                    "age_seconds": round(age), "server_status": "unknown"}
        return {**data, "monitoring_status": "fresh", "age_seconds": round(age)}
    except (OSError, ValueError, TypeError, KeyError):
        return {"monitoring_status": "unavailable", "server_status": "unknown"}
