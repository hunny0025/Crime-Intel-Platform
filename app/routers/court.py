"""Phase 7 — Court Intelligence Layer API endpoints.

All outputs are advisory, labeled SIMULATION where applicable,
and require prosecutorial review.
"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case

from app.court.defense_simulator import run_defense_simulation, get_latest_simulation
from app.court.integrity_engine import (
    run_integrity_audit, get_integrity_audit,
    get_artifact_certificate, get_weak_artifacts,
)
from app.court.court_readiness import (
    generate_court_readiness, get_court_readiness, get_preparation_checklist,
)
from app.court.prosecution_support import (
    generate_prosecution_narrative, get_expert_preparation_guide,
    get_counter_narratives,
)
from app.court.conviction_risk import generate_conviction_risk, get_conviction_risk

router = APIRouter(tags=["court-intelligence"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Prompt 37: Defense Simulation ────────────────────────────────────────

class DefenseSimulationRequest(BaseModel):
    categories: Optional[list[str]] = None


@router.post("/cases/{case_id}/court/defense-simulation")
def defense_simulation(case_id: str, body: Optional[DefenseSimulationRequest] = None, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    categories = body.categories if body else None
    return run_defense_simulation(case_id, db, categories)


@router.get("/cases/{case_id}/court/defense-simulation/latest")
def latest_simulation(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_latest_simulation(case_id)


# ── Prompt 38: Evidence Integrity ────────────────────────────────────────

@router.post("/cases/{case_id}/court/integrity-audit")
def integrity_audit(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return run_integrity_audit(case_id, db)


@router.get("/cases/{case_id}/court/integrity-audit")
def view_integrity(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_integrity_audit(case_id)


@router.get("/evidence/{artifact_id}/integrity-certificate")
def artifact_cert(artifact_id: str):
    return get_artifact_certificate(artifact_id)


@router.get("/cases/{case_id}/court/integrity-audit/weak")
def weak_artifacts(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_weak_artifacts(case_id)


# ── Prompt 39: Court Readiness ───────────────────────────────────────────

@router.post("/cases/{case_id}/court/readiness")
def court_readiness(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_court_readiness(case_id, db)


@router.get("/cases/{case_id}/court/readiness")
def view_court_readiness(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_court_readiness(case_id)


@router.get("/cases/{case_id}/court/readiness/checklist")
def checklist(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_preparation_checklist(case_id)


# ── Prompt 40: Prosecution Support ───────────────────────────────────────

@router.post("/cases/{case_id}/court/prosecution-narrative")
def prosecution_narrative(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_prosecution_narrative(case_id)


@router.get("/cases/{case_id}/court/expert-preparation")
def expert_prep(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_expert_preparation_guide(case_id)


@router.get("/cases/{case_id}/court/counter-narratives")
def counter_narratives(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_counter_narratives(case_id)


# ── Prompt 41: Conviction Risk ───────────────────────────────────────────

@router.post("/cases/{case_id}/court/conviction-risk")
def conviction_risk(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_conviction_risk(case_id, db)


@router.get("/cases/{case_id}/court/conviction-risk")
def view_conviction_risk(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_conviction_risk(case_id)
