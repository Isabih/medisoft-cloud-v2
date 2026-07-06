"""
AI diagnose router — proxies a structured prompt to Lovable AI Gateway
and returns JSON { root_cause, fix_steps[], severity, auto_healable }.

Env: LOVABLE_API_KEY (auto-provisioned by Lovable).
"""
import os
import json
import hashlib
import logging
import uuid
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.diagnosis_rules import diagnose_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

GATEWAY = "https://ai.gateway.lovable.dev/v1/chat/completions"
MODEL = "google/gemini-3-flash-preview"

SYSTEM_PROMPT = """You are a senior MySQL replication and Linux ops engineer
helping monitor 50+ remote health center databases. Given the current status
JSON for one health center (replication threads, errors, CPU/RAM/Disk,
heartbeat, last backup), produce STRICT JSON with this shape:

{
  "root_cause": "<one short sentence>",
  "fix_steps": ["<actionable step 1>", "<step 2>", ...],
  "severity": "info" | "warning" | "critical",
  "auto_healable": true | false
}

Be specific. If IO thread is off with "Lost connection" — diagnose network.
If SQL thread off with duplicate-key — diagnose conflict, suggest sql_slave_skip_counter.
If disk > 90% — flag critical, suggest cleanup. Keep fix_steps under 6.
Return ONLY JSON, no markdown, no commentary.
"""


class DiagnoseRequest(BaseModel):
    center_id: str
    context: Dict[str, Any] = {}


def _fingerprint(ctx: dict) -> str:
    return hashlib.sha256(
        json.dumps(ctx, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]


@router.post("/diagnose")
def diagnose(req: DiagnoseRequest, db: Session = Depends(get_db)):
    api_key = os.getenv("LOVABLE_API_KEY") or os.getenv("OPENAI_API_KEY")

    # Pull center context from DB
    center = db.execute(
        text("SELECT name, province, district, anydesk_id, rustdesk_id, "
             "phone_number_1, phone_contact_1, cpu_usage, ram_usage, disk_usage, "
             "internet_status, mysql_status, last_seen "
             "FROM health_centers WHERE id = :id"),
        {"id": req.center_id},
    ).mappings().first()
    if not center:
        raise HTTPException(404, "Health center not found")

    rep = db.execute(
        text("SELECT io_running, sql_running, seconds_behind, last_io_error, last_sql_error, checked_at "
             "FROM replication_status WHERE center_id = :id "
             "ORDER BY checked_at DESC LIMIT 1"),
        {"id": req.center_id},
    ).mappings().first()

    payload_ctx = {
        "center": dict(center),
        "replication": dict(rep) if rep else None,
        "extra": req.context,
    }

    fp = _fingerprint(payload_ctx)

    # Cache: skip LLM if we asked the same question in last hour
    cached = db.execute(
        text("SELECT root_cause, fix_steps, severity, auto_healable FROM ai_diagnoses "
             "WHERE center_id = :id AND fingerprint = :fp "
             "AND created_at > NOW() - INTERVAL 1 HOUR ORDER BY created_at DESC LIMIT 1"),
        {"id": req.center_id, "fp": fp},
    ).mappings().first()
    if cached:
        return {
            "root_cause": cached["root_cause"],
            "fix_steps": json.loads(cached["fix_steps"]) if isinstance(cached["fix_steps"], str) else cached["fix_steps"],
            "severity": cached["severity"],
            "auto_healable": bool(cached["auto_healable"]),
            "cached": True,
        }

    if not api_key:
        data = diagnose_context(payload_ctx)
        db.execute(
            text("INSERT INTO ai_diagnoses "
                 "(id, center_id, fingerprint, root_cause, fix_steps, severity, auto_healable, created_at) "
                 "VALUES (:id, :cid, :fp, :rc, :fs, :sev, :ah, NOW())"),
            {
                "id": str(uuid.uuid4()), "cid": req.center_id, "fp": fp,
                "rc": data.get("root_cause", ""),
                "fs": json.dumps(data.get("fix_steps", [])),
                "sev": data.get("severity", "info"),
                "ah": 1 if data.get("auto_healable") else 0,
            },
        )
        db.commit()
        data["mode"] = "deterministic_ai_comments"
        return data

    try:
        r = requests.post(
            GATEWAY,
            headers={
                "Lovable-API-Key": api_key,
                "X-Lovable-AIG-SDK": "fastapi",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload_ctx, default=str)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=30,
        )
        if r.status_code == 429:
            raise HTTPException(429, "AI rate-limited, try again shortly")
        if r.status_code == 402:
            raise HTTPException(402, "AI credits exhausted — add credits in Lovable workspace settings")
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("AI diagnose failed; falling back to deterministic diagnosis")
        data = diagnose_context(payload_ctx)
        data["mode"] = "fallback_after_ai_error"

    # Persist
    db.execute(
        text("INSERT INTO ai_diagnoses "
             "(id, center_id, fingerprint, root_cause, fix_steps, severity, auto_healable, created_at) "
             "VALUES (:id, :cid, :fp, :rc, :fs, :sev, :ah, NOW())"),
        {
            "id": str(uuid.uuid4()), "cid": req.center_id, "fp": fp,
            "rc": data.get("root_cause", ""),
            "fs": json.dumps(data.get("fix_steps", [])),
            "sev": data.get("severity", "info"),
            "ah": 1 if data.get("auto_healable") else 0,
        },
    )
    db.commit()
    return data
