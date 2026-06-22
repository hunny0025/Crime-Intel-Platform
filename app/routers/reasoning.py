"""Reasoning layer endpoints — Hypothesis, Assumption, Contradiction, EvidenceGap, Timeline."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.graph import hypothesis as hyp
from app.graph import crud
from app.graph.schemas import (
    HypothesisCreate,
    AssumptionCreate,
    ContradictionCreate,
    EvidenceGapCreate,
    PredictedByRequest,
)

router = APIRouter(tags=["reasoning"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Hypothesis ───────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/hypotheses", status_code=201)
def create_hypothesis(case_id: str, body: HypothesisCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return hyp.create_hypothesis(body.model_dump())

@router.get("/cases/{case_id}/hypotheses")
def list_hypotheses(case_id: str, db: Session = Depends(get_db)):
    """List all hypotheses for a case, sorted by probability descending."""
    _validate_case(case_id, db)
    return hyp.list_hypotheses(case_id)

@router.get("/cases/{case_id}/hypotheses/{hypothesis_id}")
def get_hypothesis(case_id: str, hypothesis_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = hyp.get_hypothesis(hypothesis_id)
    if not node:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return node

@router.post("/cases/{case_id}/graph/hypothesis/{hypothesis_id}/predicted-by", status_code=201)
def add_predicted_by(
    case_id: str,
    hypothesis_id: str,
    body: PredictedByRequest,
    db: Session = Depends(get_db),
):
    """Link a hypothesis to a predicted entity via PREDICTED_BY."""
    _validate_case(case_id, db)
    return hyp.add_predicted_by(hypothesis_id, body.target_node_id)


# ── Assumption ───────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/assumptions", status_code=201)
def create_assumption(case_id: str, body: AssumptionCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return hyp.create_assumption(body.model_dump())

@router.get("/cases/{case_id}/assumptions")
def list_assumptions(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return hyp.list_assumptions(case_id)


# ── Contradiction ────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/contradictions", status_code=201)
def create_contradiction(case_id: str, body: ContradictionCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return hyp.create_contradiction(body.model_dump())

@router.get("/cases/{case_id}/contradictions")
def list_contradictions(case_id: str, db: Session = Depends(get_db)):
    """List all contradictions for a case, sorted by severity."""
    _validate_case(case_id, db)
    return hyp.list_contradictions(case_id)

@router.post("/cases/{case_id}/contradictions/{contradiction_id}/involves", status_code=201)
def add_involves(
    case_id: str,
    contradiction_id: str,
    body: PredictedByRequest,
    db: Session = Depends(get_db),
):
    """Link a contradiction to an involved node via INVOLVES."""
    _validate_case(case_id, db)
    return hyp.add_involves(contradiction_id, body.target_node_id)


# ── Evidence Gap ─────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/evidence-gaps", status_code=201)
def create_evidence_gap(case_id: str, body: EvidenceGapCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return hyp.create_evidence_gap(body.model_dump())

@router.get("/cases/{case_id}/evidence-gaps")
def list_evidence_gaps(case_id: str, db: Session = Depends(get_db)):
    """List open evidence gaps, sorted by urgency."""
    _validate_case(case_id, db)
    return hyp.list_evidence_gaps(case_id)

@router.post("/cases/{case_id}/evidence-gaps/{gap_id}/relates-to", status_code=201)
def add_relates_to(
    case_id: str,
    gap_id: str,
    body: PredictedByRequest,
    db: Session = Depends(get_db),
):
    """Link an evidence gap to a related node via RELATES_TO."""
    _validate_case(case_id, db)
    return hyp.add_relates_to(gap_id, body.target_node_id)


# ── Timeline ─────────────────────────────────────────────────────────────

@router.get("/cases/{case_id}/graph/timeline")
def query_timeline(
    case_id: str,
    from_ts: str = Query(..., alias="from", description="ISO timestamp start"),
    to_ts: str = Query(..., alias="to", description="ISO timestamp end"),
    db: Session = Depends(get_db),
):
    """
    Return all Event nodes whose valid_from/valid_to overlaps the window,
    with connected Persons/Locations/Accounts, ordered by valid_from.
    """
    _validate_case(case_id, db)
    return hyp.query_timeline(case_id, from_ts, to_ts)
