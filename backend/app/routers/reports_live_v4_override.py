from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/reports", tags=["reports-live-v4"])

def ok_status(v):
    return str(v or "").lower() in ("yes", "on", "online", "running", "ok", "true", "1")

@router.get("/operational")
def operational_live_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    db: Session = Depends(get_db),
):
    today = str(date.today())

    centers = db.execute(text("""
        SELECT
            hc.id AS center_id,
            hc.name AS center_name,
            hc.foss_id,
            hc.phone_contact_1 AS head_name,
            hc.phone_number_1 AS head_phone
        FROM health_centers hc
        ORDER BY hc.name
    """)).mappings().all()

    rows = []
    for c in centers:
        foss_id = c["foss_id"]

        local = db.execute(text("""
            SELECT sent_at, created_at
            FROM source_agent_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        cloud = db.execute(text("""
            SELECT io_running, sql_running, seconds_behind, checked_at, created_at
            FROM cloud_replica_reports
            WHERE foss_id=:foss_id
            ORDER BY id DESC
            LIMIT 1
        """), {"foss_id": foss_id}).mappings().first()

        sms = db.execute(text("""
            SELECT
              COUNT(*) AS sms_sent,
              SUM(CASE WHEN status IN ('delivered','success','sent') THEN 1 ELSE 0 END) AS sms_delivered
            FROM sms_logs
            WHERE center_id=:center_id
              AND DATE(sent_at)=CURDATE()
        """), {"center_id": c["center_id"]}).mappings().first()

        io_up = ok_status(cloud["io_running"] if cloud else None)
        sql_up = ok_status(cloud["sql_running"] if cloud else None)

        last_seen = None
        if local:
            last_seen = local["sent_at"] or local["created_at"]
        elif cloud:
            last_seen = cloud["checked_at"] or cloud["created_at"]

        rows.append({
            "day": today,
            "center_id": c["center_id"],
            "center_name": c["center_name"],
            "foss_id": foss_id,
            "head_name": c["head_name"] or "Head of HC",
            "head_phone": c["head_phone"] or "",
            "last_seen": str(last_seen) if last_seen else None,
            "io_down": not io_up,
            "sql_down": not sql_up,
            "both_down": (not io_up and not sql_up),
            "io_down_count": 0 if io_up else 1,
            "sql_down_count": 0 if sql_up else 1,
            "samples": 1,
            "outdated": False,
            "sms_sent": int((sms or {}).get("sms_sent") or 0),
            "sms_delivered": int((sms or {}).get("sms_delivered") or 0),
            "sms_to_head": 0,
            "sms_to_admin": 0,
            "head_notified": False,
        })

    return rows
