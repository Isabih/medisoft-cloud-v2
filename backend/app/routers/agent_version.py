"""Agent version registry and safe auto-update hook.

The local agent calls `GET /agent-version/latest?current=1.2.3` on each heartbeat
and, when a newer version is offered, downloads it and restarts itself.
The registry is manually curated via `POST /agent-version` from an admin UI.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/agent-version", tags=["agent-version"])


class AgentVersionIn(BaseModel):
    version: str
    channel: str = "stable"
    download_url: str | None = None
    sha256: str | None = None
    notes: str | None = None
    is_current: bool = True


class AgentReport(BaseModel):
    foss_id: str | None = None
    center_id: str | None = None
    version: str


@router.get("/latest")
def get_latest(channel: str = "stable", current: str | None = Query(None),
               db: Session = Depends(get_db)):
    row = db.execute(text(
        """
        SELECT version, download_url, sha256, notes, released_at
        FROM agent_versions
        WHERE channel = :ch AND is_current = 1
        ORDER BY released_at DESC LIMIT 1
        """
    ), {"ch": channel}).mappings().first()
    if not row:
        return {"version": None, "update_available": False}
    latest = dict(row)
    latest["update_available"] = bool(current and current != latest["version"])
    return latest


@router.post("")
def register_version(payload: AgentVersionIn, db: Session = Depends(get_db)):
    if not payload.version:
        raise HTTPException(400, "version is required")
    if payload.is_current:
        db.execute(text(
            "UPDATE agent_versions SET is_current = 0 WHERE channel = :ch"
        ), {"ch": payload.channel})
    db.execute(text(
        """
        INSERT INTO agent_versions
            (version, channel, download_url, sha256, notes, is_current)
        VALUES (:v, :ch, :url, :sha, :n, :cur)
        ON DUPLICATE KEY UPDATE
            download_url = VALUES(download_url),
            sha256 = VALUES(sha256),
            notes = VALUES(notes),
            is_current = VALUES(is_current)
        """
    ), {
        "v": payload.version, "ch": payload.channel,
        "url": payload.download_url, "sha": payload.sha256,
        "n": payload.notes, "cur": 1 if payload.is_current else 0,
    })
    db.commit()
    return {"ok": True}


@router.post("/report")
def report_version(payload: AgentReport, db: Session = Depends(get_db)):
    """Agents call this to declare their currently-installed version."""
    if not payload.version:
        raise HTTPException(400, "version is required")
    if payload.center_id:
        db.execute(text(
            "UPDATE health_centers SET agent_version=:v, agent_last_report=NOW() "
            "WHERE id=:id"
        ), {"v": payload.version[:50], "id": payload.center_id})
    elif payload.foss_id:
        db.execute(text(
            "UPDATE health_centers SET agent_version=:v, agent_last_report=NOW() "
            "WHERE foss_id=:f"
        ), {"v": payload.version[:50], "f": payload.foss_id})
    db.commit()
    return {"ok": True}


@router.get("")
def list_versions(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT version, channel, download_url, sha256, notes, is_current, released_at "
        "FROM agent_versions ORDER BY released_at DESC"
    )).mappings().all()
    return [dict(r) for r in rows]
