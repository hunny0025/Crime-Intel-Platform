"""Investigation Memory endpoints — append-only reasoning audit log."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.db.models import Case, MemoryRecord, MemoryRecordType
from app.memory.writer import write_memory_record
from app.memory.replay import replay_beliefs_as_of

router = APIRouter(tags=["memory"])


# ── Schemas ──────────────────────────────────────────────────────────────

class MemoryRecordCreate(BaseModel):
    record_type: str  # Must be decision_made or lead_status_changed for manual
    description: str
    actor: str        # Must be a human investigator id (not system:*)
    evidence_basis: Optional[list[str]] = None
    graph_refs: Optional[list[str]] = None
    reasoning: Optional[str] = None

class MemoryRecordResponse(BaseModel):
    record_id: str
    case_id: str
    timestamp: str
    record_type: str
    description: str
    evidence_basis: Optional[list[str]] = None
    graph_refs: Optional[list[str]] = None
    beliefs_before: Optional[dict] = None
    beliefs_after: Optional[dict] = None
    actor: str
    reasoning: Optional[str] = None


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


def _record_to_dict(r: MemoryRecord) -> dict:
    return {
        "record_id": str(r.record_id),
        "case_id": str(r.case_id),
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "record_type": r.record_type.value if hasattr(r.record_type, "value") else r.record_type,
        "description": r.description,
        "evidence_basis": r.evidence_basis,
        "graph_refs": r.graph_refs,
        "beliefs_before": r.beliefs_before,
        "beliefs_after": r.beliefs_after,
        "actor": r.actor,
        "reasoning": r.reasoning,
    }


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/memory", status_code=201)
def create_memory_record(
    case_id: str,
    body: MemoryRecordCreate,
    db: Session = Depends(get_db),
):
    """
    Create a memory record manually.
    For human-recorded decisions — actor must NOT start with 'system:'.
    record_type must be decision_made or lead_status_changed.
    """
    _validate_case(case_id, db)

    # Validate manual record constraints
    allowed_types = {"decision_made", "lead_status_changed"}
    if body.record_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Manual memory records must be: {sorted(allowed_types)}",
        )
    if body.actor.startswith("system:"):
        raise HTTPException(
            status_code=400,
            detail="Manual records must have a human actor, not 'system:*'",
        )

    record = write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType(body.record_type),
        description=body.description,
        actor=body.actor,
        evidence_basis=body.evidence_basis,
        graph_refs=body.graph_refs,
        reasoning=body.reasoning,
    )
    db.commit()
    return _record_to_dict(record)


@router.get("/cases/{case_id}/memory")
def list_memory_records(
    case_id: str,
    record_type: Optional[str] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """
    List memory records, filterable by record_type and date range.
    Paginated, ordered chronologically (newest first).
    """
    _validate_case(case_id, db)

    query = db.query(MemoryRecord).filter(
        MemoryRecord.case_id == uuid.UUID(case_id),
    )

    if record_type:
        try:
            rt = MemoryRecordType(record_type)
            query = query.filter(MemoryRecord.record_type == rt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid record_type: {record_type}")

    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date)
            query = query.filter(MemoryRecord.timestamp >= from_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'from' timestamp")

    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date)
            query = query.filter(MemoryRecord.timestamp <= to_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'to' timestamp")

    total = query.count()
    records = (
        query
        .order_by(desc(MemoryRecord.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [_record_to_dict(r) for r in records],
    }


@router.get("/cases/{case_id}/memory/replay")
def replay_beliefs(
    case_id: str,
    as_of: str = Query(..., description="ISO timestamp to replay beliefs up to"),
    db: Session = Depends(get_db),
):
    """
    Reconstruct hypothesis probabilities as they existed at a given timestamp
    by replaying probability_updated memory records.
    """
    _validate_case(case_id, db)

    try:
        ts = datetime.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid 'as_of' timestamp")

    beliefs = replay_beliefs_as_of(db, case_id, ts)
    return {
        "as_of": as_of,
        "hypothesis_probabilities": beliefs,
    }


@router.get("/cases/{case_id}/diary")
def get_case_diary(
    case_id: str,
    as_of: Optional[str] = Query(None, description="ISO timestamp to reconstruct diary up to"),
    db: Session = Depends(get_db),
):
    """
    Exposes a chronological reconstruction of the investigation's history.
    """
    _validate_case(case_id, db)

    as_of_dt = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'as_of' timestamp")

    from app.memory.reader import get_investigation_state
    state = get_investigation_state(case_id, as_of=as_of_dt, db=db)
    return state
