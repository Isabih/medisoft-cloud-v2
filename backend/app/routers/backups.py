from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("")
def list_backups(
    center_id: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    db: Session = Depends(get_db)
):
    sql = "SELECT * FROM backups WHERE 1=1"
    params = {}

    if center_id:
        sql += " AND center_id = :center_id"
        params["center_id"] = center_id

    sql += " ORDER BY created_at DESC"

    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/center/{center_id}")
def backups_by_center(center_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT * FROM backups WHERE center_id = :center_id ORDER BY created_at DESC"),
        {"center_id": center_id}
    ).mappings().all()

    return [dict(r) for r in rows]