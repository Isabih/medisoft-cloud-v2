from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily")
def daily_reports():
    return []


@router.get("/center/{center_id}")
def center_report(center_id: str):
    return {"center_id": center_id, "rows": []}


@router.get("/download/{date}")
def download_report(date: str, format: str):
    return {"date": date, "format": format, "message": "Not implemented yet"}


@router.get("/operational")
def operational_report(
    db: Session = Depends(get_db),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
):
    """
    Per-day per-center operational report:
      - IO down, SQL down, both down (most recent state of the day)
      - Outdated (no heartbeat in last 30 min of the day)
      - SMS sent / delivered counts + flag whether head-of-HC was reached
    """
    where_date = ""
    params: dict = {}
    if from_:
        where_date += " AND DATE(sr.created_at) >= :from_d"
        params["from_d"] = from_
    if to:
        where_date += " AND DATE(sr.created_at) <= :to_d"
        params["to_d"] = to
    if not from_ and not to:
        where_date = " AND sr.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"

    try:
        rows = db.execute(
            text(f"""
                SELECT
                    DATE(sr.created_at) AS day,
                    hc.id AS center_id,
                    hc.name AS center_name,
                    hc.foss_id,
                    hc.phone_contact_1 AS head_name,
                    hc.phone_number_1 AS head_phone,
                    MAX(sr.created_at) AS last_seen,
                    SUBSTRING_INDEX(GROUP_CONCAT(sr.io_running ORDER BY sr.created_at DESC SEPARATOR '||'), '||', 1) AS io_last,
                    SUBSTRING_INDEX(GROUP_CONCAT(sr.sql_running ORDER BY sr.created_at DESC SEPARATOR '||'), '||', 1) AS sql_last,
                    SUM(CASE WHEN LOWER(COALESCE(sr.io_running,'')) NOT IN ('yes','on') THEN 1 ELSE 0 END) AS io_down_count,
                    SUM(CASE WHEN LOWER(COALESCE(sr.sql_running,'')) NOT IN ('yes','on') THEN 1 ELSE 0 END) AS sql_down_count,
                    COUNT(*) AS sample_count
                FROM source_agent_reports sr
                JOIN health_centers hc ON hc.foss_id = sr.foss_id
                WHERE 1=1 {where_date}
                GROUP BY DATE(sr.created_at), hc.id
                ORDER BY day DESC, center_name
            """),
            params,
        ).mappings().all()
        rows = [dict(r) for r in rows]
    except Exception:
        rows = []

    # SMS aggregation per (day, center)
    sms_idx: dict = {}
    try:
        sms_rows = db.execute(
            text("""
                SELECT DATE(sent_at) AS day, center_id,
                       COUNT(*) AS sms_sent,
                       SUM(CASE WHEN status IN ('sent','delivered') THEN 1 ELSE 0 END) AS sms_ok,
                       SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS sms_delivered,
                       SUM(CASE WHEN recipient_role = 'head' THEN 1 ELSE 0 END) AS sms_head,
                       SUM(CASE WHEN recipient_role = 'admin' THEN 1 ELSE 0 END) AS sms_admin
                FROM sms_logs
                WHERE sent_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY DATE(sent_at), center_id
            """)
        ).mappings().all()
        for s in sms_rows:
            sms_idx[(str(s["day"]), s["center_id"])] = dict(s)
    except Exception:
        pass

    out = []
    for r in rows:
        io_ok = (r["io_last"] or "").lower() in ("yes", "on")
        sql_ok = (r["sql_last"] or "").lower() in ("yes", "on")
        sms = sms_idx.get((str(r["day"]), r["center_id"]), {})
        out.append({
            "day": str(r["day"]),
            "center_id": r["center_id"],
            "center_name": r["center_name"],
            "foss_id": r["foss_id"],
            "head_name": r["head_name"],
            "head_phone": r["head_phone"],
            "last_seen": str(r["last_seen"]) if r["last_seen"] else None,
            "io_down": not io_ok,
            "sql_down": not sql_ok,
            "both_down": (not io_ok) and (not sql_ok),
            "io_down_count": int(r["io_down_count"] or 0),
            "sql_down_count": int(r["sql_down_count"] or 0),
            "samples": int(r["sample_count"] or 0),
            "outdated": r["last_seen"] is None,
            "sms_sent": int(sms.get("sms_sent") or 0),
            "sms_delivered": int(sms.get("sms_delivered") or 0),
            "sms_to_head": int(sms.get("sms_head") or 0),
            "sms_to_admin": int(sms.get("sms_admin") or 0),
            "head_notified": int(sms.get("sms_head") or 0) > 0,
        })
    return out


@router.get("/incident-history")
def incident_history(
    db: Session = Depends(get_db),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    foss_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    """Long-term compact incident history. This survives the 7-day raw data cleanup."""
    where = []
    params = {"limit": limit}
    if from_:
        where.append("started_at >= :from_d")
        params["from_d"] = from_
    if to:
        where.append("started_at < DATE_ADD(:to_d, INTERVAL 1 DAY)")
        params["to_d"] = to
    if foss_id:
        where.append("foss_id = :foss_id")
        params["foss_id"] = foss_id
    if event_type:
        where.append("event_type = :event_type")
        params["event_type"] = event_type
    if not where:
        where.append("started_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)")
    where_sql = " AND ".join(where)
    try:
        rows = db.execute(text(f"""
            SELECT id, foss_id, center_id, center_name, database_name, channel_name,
                   event_type, severity, started_at, ended_at, duration_seconds,
                   occurrence_count, root_cause, recommended_fix, first_aid_action,
                   resolved, source_table
            FROM incident_history
            WHERE {where_sql}
            ORDER BY started_at DESC
            LIMIT :limit
        """), params).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


@router.get("/incident-summary")
def incident_summary(
    db: Session = Depends(get_db),
    days: int = Query(90, ge=7, le=365),
):
    try:
        by_type = db.execute(text("""
            SELECT event_type, severity, COUNT(*) AS incidents, SUM(occurrence_count) AS occurrences
            FROM incident_history
            WHERE started_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY event_type, severity
            ORDER BY incidents DESC
        """), {"days": days}).mappings().all()
        by_center = db.execute(text("""
            SELECT COALESCE(center_name, foss_id, center_id, 'unknown') AS center,
                   foss_id, COUNT(*) AS incidents, SUM(occurrence_count) AS occurrences,
                   MAX(started_at) AS last_incident
            FROM incident_history
            WHERE started_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY center, foss_id
            ORDER BY incidents DESC
            LIMIT 50
        """), {"days": days}).mappings().all()
        return {
            "days": days,
            "by_type": [dict(r) for r in by_type],
            "top_centers": [dict(r) for r in by_center],
        }
    except Exception:
        return {"days": days, "by_type": [], "top_centers": []}
