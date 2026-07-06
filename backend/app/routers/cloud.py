import json
from fastapi import APIRouter, HTTPException

router = APIRouter()

STATUS_FILE = "/opt/monitoring/cloud_status.json"


@router.get("/cloud/status")
def get_cloud_status():
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cloud status file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load cloud status: {str(e)}")
