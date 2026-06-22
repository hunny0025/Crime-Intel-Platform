"""OSINT Records listing endpoint."""

import uuid
import json
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["osint-records"])


@router.get("/cases/{case_id}/osint/records")
def list_osint_records(
    case_id: str,
    source_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """List OSINT records for a case, filterable by source_type."""
    params = {"cid": uuid.UUID(case_id)}
    where = "WHERE case_id = :cid"

    if source_type:
        where += " AND source_type = :st"
        params["st"] = source_type

    total_row = db.execute(
        text(f"SELECT count(*) FROM osint_records {where}"), params,
    ).scalar()

    rows = db.execute(
        text(f"""
            SELECT record_id, case_id, source_type, query, retrieved_at,
                   raw_result, extracted_entities, classification_tag
            FROM osint_records {where}
            ORDER BY retrieved_at DESC
            OFFSET :offset LIMIT :limit
        """),
        {**params, "offset": (page - 1) * page_size, "limit": page_size},
    ).fetchall()

    records = []
    for r in rows:
        records.append({
            "record_id": str(r[0]),
            "case_id": str(r[1]),
            "source_type": r[2],
            "query": r[3],
            "retrieved_at": r[4].isoformat() if r[4] else None,
            "raw_result": r[5],
            "extracted_entities": r[6],
            "classification_tag": r[7],
        })

    return {"total": total_row, "page": page, "page_size": page_size, "records": records}
