"""Behavioral Intelligence endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.db.models import Case
from app.intelligence.behavioral import compute_baseline, scan_anomalies
import uuid

router = APIRouter(tags=["behavioral"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


@router.post("/cases/{case_id}/graph/person/{person_id}/baseline/compute")
def compute_person_baseline(
    case_id: str,
    person_id: str,
    min_events: int = Query(10, ge=1),
    db: Session = Depends(get_db),
):
    """
    Compute behavioral baseline from Event participation.
    Requires minimum event count for reliability.
    """
    _validate_case(case_id, db)
    return compute_baseline(case_id, person_id, db, min_events)


@router.post("/cases/{case_id}/graph/person/{person_id}/anomalies/scan")
def scan_person_anomalies(
    case_id: str,
    person_id: str,
    from_ts: str = Query(..., alias="from"),
    to_ts: str = Query(..., alias="to"),
    z_threshold: float = Query(2.0, ge=0.5),
    db: Session = Depends(get_db),
):
    """
    Scan for behavioral anomalies in the given time window.
    Requires a computed baseline.
    """
    _validate_case(case_id, db)
    return scan_anomalies(case_id, person_id, from_ts, to_ts, db, z_threshold)
