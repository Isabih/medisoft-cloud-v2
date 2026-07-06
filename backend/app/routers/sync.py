from fastapi import APIRouter

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status")
def sync_status():
    return {
        "healthy": 0,
        "lagging": 0,
        "stopped": 0
    }