import json
from datetime import datetime
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.hybrid_ai import analyze_hybrid
from app.models.hybrid_monitoring import (
    SourceAgentReport,
    CloudReplicaReport,
    HybridDiagnosis,
)

router = APIRouter(prefix="/api/v1/hybrid", tags=["Hybrid Monitoring"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SourceAgentReportIn(BaseModel):
    foss_id: str
    db_name: Optional[str] = None
    channel_name: Optional[str] = None
    hostname: Optional[str] = None

    mysql_status: str
    internet_status: str
    cloud_connection: str

    cpu_usage: float
    ram_usage: float
    disk_usage: float
    database_size_mb: float = 0
    local_size_mb: Optional[float] = None
    local_table_count: int = 0
    local_rows_count: Optional[int] = None
    local_row_count: Optional[int] = None
    local_latest_time: Optional[datetime] = None
    agent_version: Optional[str] = None

    source_config_ok: bool = False
    connected_replicas: int = 0
    replica_hosts: List[str] = []

    io_running: str = "No"
    sql_running: str = "No"
    seconds_behind: Optional[float] = None

    last_io_error: Optional[str] = ""
    last_sql_error: Optional[str] = ""

    sent_at: Optional[datetime] = None


class CloudReplicaReportIn(BaseModel):
    foss_id: str
    db_name: Optional[str] = None
    channel_name: Optional[str] = None
    source_host: Optional[str] = None

    io_running: str
    sql_running: str
    seconds_behind: Optional[float] = None

    last_io_error: Optional[str] = ""
    last_sql_error: Optional[str] = ""

    checked_at: Optional[datetime] = None


def create_diagnosis(db: Session, foss_id: str):
    source = (
        db.query(SourceAgentReport)
        .filter(SourceAgentReport.foss_id == foss_id)
        .order_by(SourceAgentReport.created_at.desc())
        .first()
    )

    cloud = (
        db.query(CloudReplicaReport)
        .filter(CloudReplicaReport.foss_id == foss_id)
        .order_by(CloudReplicaReport.created_at.desc())
        .first()
    )

    result = analyze_hybrid(source, cloud)

    diagnosis = HybridDiagnosis(
        foss_id=foss_id,
        severity=result["severity"],
        diagnosis_code=result["diagnosis_code"],
        title=result["title"],
        summary=result["summary"],
        probable_cause=result["probable_cause"],
        recommended_actions_json=result["recommended_actions_json"],
        confidence=result["confidence"],
        source_report_id=source.id if source else None,
        cloud_report_id=cloud.id if cloud else None,
    )
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@router.post("/source-report")
def receive_source_report(payload: SourceAgentReportIn, db: Session = Depends(get_db)):
    report = SourceAgentReport(
        foss_id=payload.foss_id,
        db_name=payload.db_name,
        channel_name=payload.channel_name,
        hostname=payload.hostname,

        mysql_status=payload.mysql_status,
        internet_status=payload.internet_status,
        cloud_connection=payload.cloud_connection,

        cpu_usage=payload.cpu_usage,
        ram_usage=payload.ram_usage,
        disk_usage=payload.disk_usage,
        database_size_mb=payload.database_size_mb or 0,
        local_size_mb=payload.local_size_mb if payload.local_size_mb is not None else (payload.database_size_mb or 0),
        local_table_count=payload.local_table_count or 0,
        local_rows_count=(payload.local_rows_count if payload.local_rows_count is not None else (payload.local_row_count or 0)),
        local_latest_time=payload.local_latest_time,
        agent_version=payload.agent_version,

        source_config_ok=payload.source_config_ok,
        connected_replicas=payload.connected_replicas,
        replica_hosts_json=json.dumps(payload.replica_hosts),

        io_running=payload.io_running,
        sql_running=payload.sql_running,
        seconds_behind=payload.seconds_behind,

        last_io_error=payload.last_io_error,
        last_sql_error=payload.last_sql_error,

        sent_at=payload.sent_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    diagnosis = create_diagnosis(db, payload.foss_id)

    # Keep registered health center live even before the background cloud collector runs.
    try:
        local_rows = payload.local_rows_count if payload.local_rows_count is not None else (payload.local_row_count or 0)
        local_size = payload.local_size_mb if payload.local_size_mb is not None else (payload.database_size_mb or 0)
        db.execute(text("""
            UPDATE health_centers SET
              mysql_status=:mysql, internet_status=:internet, cloud_connection=:cloud,
              last_seen=NOW(), data_size_mb=:size, cpu_usage=:cpu, ram_usage=:ram, disk_usage=:disk,
              agent_version=:agent_version
            WHERE foss_id=:foss_id
        """), {
            "mysql": payload.mysql_status, "internet": payload.internet_status, "cloud": payload.cloud_connection,
            "size": local_size, "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage,
            "agent_version": payload.agent_version or "local-agent", "foss_id": payload.foss_id,
        })
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "ok",
        "source_report_id": report.id,
        "diagnosis_id": diagnosis.id,
        "diagnosis_code": diagnosis.diagnosis_code,
        "severity": diagnosis.severity,
    }


@router.post("/cloud-report")
def receive_cloud_report(payload: CloudReplicaReportIn, db: Session = Depends(get_db)):
    report = CloudReplicaReport(
        foss_id=payload.foss_id,
        db_name=payload.db_name,
        channel_name=payload.channel_name,
        source_host=payload.source_host,

        io_running=payload.io_running,
        sql_running=payload.sql_running,
        seconds_behind=payload.seconds_behind,

        last_io_error=payload.last_io_error,
        last_sql_error=payload.last_sql_error,

        checked_at=payload.checked_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    diagnosis = create_diagnosis(db, payload.foss_id)

    # Keep registered health center live even before the background cloud collector runs.
    try:
        local_rows = payload.local_rows_count if payload.local_rows_count is not None else (payload.local_row_count or 0)
        local_size = payload.local_size_mb if payload.local_size_mb is not None else (payload.database_size_mb or 0)
        db.execute(text("""
            UPDATE health_centers SET
              mysql_status=:mysql, internet_status=:internet, cloud_connection=:cloud,
              last_seen=NOW(), data_size_mb=:size, cpu_usage=:cpu, ram_usage=:ram, disk_usage=:disk,
              agent_version=:agent_version
            WHERE foss_id=:foss_id
        """), {
            "mysql": payload.mysql_status, "internet": payload.internet_status, "cloud": payload.cloud_connection,
            "size": local_size, "cpu": payload.cpu_usage, "ram": payload.ram_usage, "disk": payload.disk_usage,
            "agent_version": payload.agent_version or "local-agent", "foss_id": payload.foss_id,
        })
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "ok",
        "cloud_report_id": report.id,
        "diagnosis_id": diagnosis.id,
        "diagnosis_code": diagnosis.diagnosis_code,
        "severity": diagnosis.severity,
    }


@router.get("/diagnosis/{foss_id}")
def get_latest_diagnosis(foss_id: str, db: Session = Depends(get_db)):
    diagnosis = (
        db.query(HybridDiagnosis)
        .filter(HybridDiagnosis.foss_id == foss_id)
        .order_by(HybridDiagnosis.created_at.desc())
        .first()
    )
    if not diagnosis:
        raise HTTPException(status_code=404, detail="No diagnosis found for this foss_id")

    return {
        "foss_id": diagnosis.foss_id,
        "severity": diagnosis.severity,
        "diagnosis_code": diagnosis.diagnosis_code,
        "title": diagnosis.title,
        "summary": diagnosis.summary,
        "probable_cause": diagnosis.probable_cause,
        "recommended_actions": json.loads(diagnosis.recommended_actions_json or "[]"),
        "confidence": diagnosis.confidence,
        "created_at": diagnosis.created_at,
    }


@router.get("/centers/summary")
def get_hybrid_summary(db: Session = Depends(get_db)):
    latest = (
        db.query(HybridDiagnosis)
        .order_by(HybridDiagnosis.created_at.desc())
        .all()
    )

    seen = set()
    results = []

    for item in latest:
        if item.foss_id in seen:
            continue
        seen.add(item.foss_id)

        results.append({
            "foss_id": item.foss_id,
            "severity": item.severity,
            "diagnosis_code": item.diagnosis_code,
            "title": item.title,
            "summary": item.summary,
            "probable_cause": item.probable_cause,
            "recommended_actions": json.loads(item.recommended_actions_json or "[]"),
            "confidence": item.confidence,
            "created_at": item.created_at,
        })

    return results