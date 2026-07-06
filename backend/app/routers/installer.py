from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/installer", tags=["Installer"])

@router.get("/local-agent", response_class=PlainTextResponse)
def get_local_agent_installer():
    candidates = [
        Path("../medisoft-local-agent-install-v3.sh"),
        Path("../local-agent-install.sh"),
        Path("agent_scripts/medisoft-local-agent-install-v3.sh"),
        Path("agent_scripts/local-agent-install.sh"),
    ]

    for path in candidates:
        if path.exists():
            return path.read_text()

    raise HTTPException(status_code=404, detail="Local agent installer script not found")
