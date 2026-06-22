"""Phase 9 — Autonomous Investigation API endpoints.

Expiration monitoring, theory generation, gap resolution, dead end
detection, AIRE pipeline, and autonomy audit/level management.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.db.models import Case

from app.reasoning.expiration_model import run_expiration_scan, compute_expiration_map
from app.reasoning.theory_generator import (
    generate_theory_candidates, get_theory_candidates,
    accept_candidate, reject_candidate, check_generation_triggers,
)
from app.reasoning.gap_resolver import (
    run_gap_resolution, run_dead_end_detection,
    get_dead_ends, pivot_dead_end,
)
from app.reasoning.autonomy_engine import (
    run_full_aire_pipeline, get_autonomy_audit,
    get_autonomy_level, set_autonomy_level,
)
from app.cross_case.integration import get_full_cross_case_intelligence

router = APIRouter(tags=["autonomous-investigation"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Prompt 47: Expiration Monitoring ─────────────────────────────────────

class ExpirationScanRequest(BaseModel):
    incident_date: Optional[str] = None


@router.post("/cases/{case_id}/aire/expiration-scan")
def expiration_scan(case_id: str, body: ExpirationScanRequest = ExpirationScanRequest(),
                    db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return run_expiration_scan(case_id, body.incident_date, db)


@router.get("/cases/{case_id}/aire/expiration-map")
def expiration_map(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return compute_expiration_map(case_id)


@router.get("/cases/{case_id}/preservation-requests")
def preservation_requests(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    from app.graph.driver import get_neo4j_client
    client = get_neo4j_client()
    return client.execute_read(
        """
        MATCH (a:InvestigationAction {case_id: $cid})
        WHERE a.time_critical = true
        RETURN a.id AS id, a.target_ref AS evidence_type,
               a.status AS status, a.created_at AS requested_at,
               a.urgency AS urgency
        ORDER BY a.created_at DESC
        """,
        {"cid": case_id},
    )


# ── Prompt 48: Theory Generation ────────────────────────────────────────

@router.get("/cases/{case_id}/aire/generation-triggers")
def generation_triggers(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return check_generation_triggers(case_id)


@router.post("/cases/{case_id}/aire/generate-theories")
def generate_theories(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_theory_candidates(case_id, db)


@router.get("/cases/{case_id}/aire/theory-candidates")
def theory_candidates(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_theory_candidates(case_id)


@router.post("/cases/{case_id}/aire/theory-candidates/{candidate_id}/accept")
def accept_theory(case_id: str, candidate_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return accept_candidate(case_id, candidate_id, db)


class RejectCandidateRequest(BaseModel):
    rejection_reason: str


@router.post("/cases/{case_id}/aire/theory-candidates/{candidate_id}/reject")
def reject_theory(case_id: str, candidate_id: str,
                  body: RejectCandidateRequest, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return reject_candidate(case_id, candidate_id, body.rejection_reason, db)


# ── Prompt 49: Gap Resolution + Dead End ─────────────────────────────────

@router.post("/cases/{case_id}/aire/gap-resolution")
def gap_resolution(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return run_gap_resolution(case_id, db)


@router.post("/cases/{case_id}/aire/dead-end-detection")
def dead_end_detection(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return run_dead_end_detection(case_id, db=db)


@router.get("/cases/{case_id}/aire/dead-ends")
def dead_ends(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_dead_ends(case_id)


class PivotRequest(BaseModel):
    pivot_rationale: str
    replacement_target: Optional[str] = None


@router.post("/cases/{case_id}/aire/dead-ends/{action_id}/pivot")
def pivot(case_id: str, action_id: str,
          body: PivotRequest, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return pivot_dead_end(case_id, action_id, body.pivot_rationale,
                          body.replacement_target, db)


# ── Prompt 50: AIRE Pipeline + Autonomy ──────────────────────────────────

@router.post("/cases/{case_id}/aire/run-pipeline")
def aire_pipeline(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return run_full_aire_pipeline(case_id, db=db)


@router.get("/cases/{case_id}/aire/autonomy-audit")
def autonomy_audit(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    import sqlalchemy as sa
    try:
        current_agency_id = db.execute(sa.text("SHOW app.current_agency_id")).scalar()
    except Exception:
        current_agency_id = None
        
    agency_id = current_agency_id or (str(case.agency_id) if case.agency_id else None)
    return get_autonomy_audit(case_id, agency_id=agency_id)


class AutonomyLevelRequest(BaseModel):
    level: str  # observe / suggest / act


@router.get("/cases/{case_id}/aire/autonomy-level")
def view_autonomy_level(case_id: str):
    return {"case_id": case_id, "autonomy_level": get_autonomy_level(case_id)}


@router.put("/cases/{case_id}/aire/autonomy-level")
def update_autonomy_level(case_id: str, body: AutonomyLevelRequest,
                          db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return set_autonomy_level(case_id, body.level, "investigator", db)


# ── Cross-Case Full Intelligence (Prompt 46) ────────────────────────────

@router.get("/cases/{case_id}/cross-case/full-intelligence")
def full_intelligence(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_full_cross_case_intelligence(case_id)
