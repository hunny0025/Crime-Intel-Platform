"""Phase 8 — Cross Case Intelligence API endpoints.

Corpus extraction, methodology library, playbooks, recidivism, MO detection.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case

from app.cross_case.corpus_extractor import extract_case_pattern, extract_all_eligible
from app.cross_case.methodology_library import find_similar_cases, get_methodology_baseline
from app.cross_case.playbook_engine import (
    get_playbook_template, get_recommended_playbook, complete_playbook_step,
)
from app.cross_case.fingerprint import (
    extract_behavioral_fingerprint, check_recidivism, detect_modus_operandi,
)

router = APIRouter(tags=["cross-case-intelligence"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Prompt 42: Corpus Extraction ────────────────────────────────────────

@router.post("/admin/corpus/extract/{case_id}")
def extract_single(case_id: str, db: Session = Depends(get_db)):
    return extract_case_pattern(case_id, db)


@router.post("/admin/corpus/extract-all")
def extract_all(db: Session = Depends(get_db)):
    return extract_all_eligible(db)


# ── Prompt 43: Similar Cases + Methodology ──────────────────────────────

@router.get("/cases/{case_id}/cross-case/similar")
def similar_cases(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return find_similar_cases(case_id)


@router.get("/cases/{case_id}/cross-case/methodology-baseline")
def methodology_baseline(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_methodology_baseline(case_id)


# ── Prompt 44: Playbooks ────────────────────────────────────────────────

@router.get("/reference/playbooks/{crime_category_id}")
def playbook_template(crime_category_id: str):
    return get_playbook_template(crime_category_id)


@router.get("/cases/{case_id}/cross-case/recommended-playbook")
def recommended_playbook(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_recommended_playbook(case_id)


@router.post("/cases/{case_id}/cross-case/playbook-step/{step_number}/complete")
def complete_step(case_id: str, step_number: int, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return complete_playbook_step(case_id, step_number, db)


# ── Prompt 45: Recidivism ───────────────────────────────────────────────

@router.post("/cases/{case_id}/cross-case/fingerprint/{person_id}")
def fingerprint(case_id: str, person_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return extract_behavioral_fingerprint(case_id, person_id)


@router.get("/cases/{case_id}/cross-case/recidivism/{person_id}")
def recidivism(case_id: str, person_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return check_recidivism(case_id, person_id)


# ── Prompt 46: MO Detection ─────────────────────────────────────────────

@router.get("/cases/{case_id}/cross-case/modus-operandi")
def modus_operandi(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return detect_modus_operandi(case_id)
