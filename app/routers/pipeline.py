"""Investigation Pipeline API — End-to-End Workflow Endpoint.

Exposes the unified investigation pipeline as an API endpoint.
This is the single entry point that runs all 12 stages of an
investigation in sequence.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.db.session import get_db
from app.db.models import Case

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"], prefix="/pipeline")


class PipelineRequest(BaseModel):
    """Optional configuration for pipeline execution."""
    skip_stages: list[str] = []  # Stage names to skip
    force_rebuild: bool = False   # Force graph rebuild even if already populated


@router.post("/cases/{case_id}/run")
def run_investigation_pipeline(
    case_id: str,
    body: Optional[PipelineRequest] = None,
    db: Session = Depends(get_db),
):
    """Execute the full 12-stage investigation pipeline for a case.

    Stages:
    1. INTAKE - Validate case, load evidence
    2. GRAPH_BUILD - Populate knowledge graph
    3. IDENTITY - Resolve identities
    4. NLP_ENRICH - Run NER, sentiment, intent
    5. CONTRADICT - Scan for contradictions
    6. BEHAVIOR - Detect behavioral anomalies
    7. THEORIZE - Generate hypotheses
    8. HPL_CHECK - Validate hypothesis predicates
    9. LEGAL_MAP - Map evidence to legal elements
    10. LEGAL_PROC - Check procedural compliance
    11. COURT_READY - Score court readiness
    12. REPORT - Generate ORACLE report

    Returns detailed results for each stage including timing,
    success/failure status, and result summaries.
    """
    # Validate case exists
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    from app.pipeline.investigation_pipeline import run_full_pipeline
    result = run_full_pipeline(case_id, db)
    return result


@router.get("/cases/{case_id}/status")
def get_pipeline_status(
    case_id: str,
    db: Session = Depends(get_db),
):
    """Get the latest pipeline execution status for a case."""
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Check memory for pipeline records
    from app.db.models import MemoryRecord
    latest = db.query(MemoryRecord).filter(
        MemoryRecord.case_id == uuid.UUID(case_id),
        MemoryRecord.record_type == "pipeline_execution",
    ).order_by(MemoryRecord.timestamp.desc()).first()

    if not latest:
        return {"case_id": case_id, "status": "never_run", "last_execution": None}

    return {
        "case_id": case_id,
        "status": "completed",
        "last_execution": {
            "timestamp": latest.timestamp.isoformat(),
            "details": latest.content,
        },
    }
