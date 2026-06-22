"""Deception detection orchestration — unified single-source implementation.

Consolidation: Previously, deception scoring existed in two places:
  1. app/ai/models.py::score_deception (LIWC-inspired psycholinguistic analysis)
  2. deception-detection-service/ (separate Flask microservice)

This router now uses ONLY app/ai/models.py as the canonical scorer.
The separate microservice is deprecated — all deception logic lives in one place.

Stores DeceptionAssessment nodes in Neo4j, wires into Attention Engine.

NOTE: High deception_score assessments (>0.7) should generate an
InvestigationAction prompting human review. Automated deception findings
should NEVER silently downgrade evidence without investigator awareness.
"""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.db.models import Case, EvidenceArtifact
from app.graph.driver import get_neo4j_client
from app.ai.models import score_deception  # Single source of truth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["deception"])

DECEPTION_THRESHOLD = 0.7  # Above this → high attention + action


class AssessRequest(BaseModel):
    artifact_id: Optional[str] = None
    osint_record_id: Optional[str] = None
    content_type: Optional[str] = "text"
    text_content: Optional[str] = None  # Direct text for analysis


class BatchAssessRequest(BaseModel):
    artifact_ids: list[str]


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


def _fetch_text_content(target_id: str, target_type: str, db: Session) -> str:
    """Fetch text content for analysis from the evidence store."""
    if target_type == "evidence_artifact":
        try:
            artifact = db.query(EvidenceArtifact).filter(
                EvidenceArtifact.artifact_id == uuid.UUID(target_id)
            ).first()
            if artifact:
                # Try to get text from MinIO
                try:
                    from app.storage.minio_client import get_minio_client
                    import json
                    minio = get_minio_client()
                    raw = minio.download_bytes(artifact.content_pointer)
                    content = json.loads(raw.decode("utf-8"))
                    # Extract text fields from canonical content
                    text_fields = []
                    for key in ("body", "text", "content", "message", "description", "notes"):
                        if key in content and isinstance(content[key], str):
                            text_fields.append(content[key])
                    if text_fields:
                        return " ".join(text_fields)
                except Exception:
                    pass
        except Exception:
            pass
    return ""


@router.post("/cases/{case_id}/deception/assess")
def assess_deception(
    case_id: str,
    body: AssessRequest,
    db: Session = Depends(get_db),
):
    """
    Assess evidence for deception using psycholinguistic analysis.

    Uses the unified deception scorer (app/ai/models.py) which implements
    7-dimension LIWC-inspired analysis based on Newman et al. (2003),
    Pennebaker (2003), and Vrij (2010).

    Provide either:
    - text_content directly for analysis, OR
    - artifact_id / osint_record_id to fetch text from evidence store
    """
    _validate_case(case_id, db)

    target_type = "evidence_artifact" if body.artifact_id else "osint_record"
    target_id = body.artifact_id or body.osint_record_id
    if not target_id and not body.text_content:
        raise HTTPException(
            status_code=400,
            detail="Provide artifact_id, osint_record_id, or text_content",
        )

    # Get text for analysis
    text = body.text_content or ""
    if not text and target_id:
        text = _fetch_text_content(target_id, target_type, db)

    if not text or len(text) < 30:
        return {
            "assessment_id": str(uuid.uuid4()),
            "target_type": target_type,
            "target_id": target_id,
            "deception_score": 0.0,
            "error": "Insufficient text content for deception analysis (minimum 30 characters)",
        }

    # Run unified deception scorer
    detection = score_deception(text)

    # Store DeceptionAssessment node
    assessment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    neo4j = get_neo4j_client()

    neo4j.execute_write(
        """
        CREATE (d:DeceptionAssessment {
            id: $aid, case_id: $cid,
            target_type: $ttype, target_id: $tid,
            model_name: $model, model_version: '3.0',
            deception_score: $score,
            verdict: $verdict,
            assessed_at: $now,
            methodology: $methodology,
            classification_tag: 'case_sensitive',
            created_at: $now
        })
        """,
        {
            "aid": assessment_id, "cid": case_id,
            "ttype": target_type, "tid": target_id or "direct_text",
            "model": detection.get("model", "deception_scorer_v3"),
            "score": detection.get("deception_score", 0.0),
            "verdict": detection.get("verdict", "unknown"),
            "now": now,
            "methodology": detection.get("methodology", ""),
        },
    )

    # If target_id exists, link assessment to the evidence node
    if target_id:
        neo4j.execute_write(
            """
            MATCH (d:DeceptionAssessment {id: $aid})
            MATCH (e {id: $tid, case_id: $cid})
            MERGE (d)-[:ASSESSES]->(e)
            """,
            {"aid": assessment_id, "tid": target_id, "cid": case_id},
        )

    # If high deception score, create InvestigationAction for human review
    if detection.get("deception_score", 0) >= DECEPTION_THRESHOLD:
        action_id = str(uuid.uuid4())
        neo4j.execute_write(
            """
            CREATE (a:InvestigationAction {
                id: $action_id, case_id: $cid,
                action_type: 'review_deception_finding',
                description: $desc,
                priority: 'high',
                status: 'pending',
                source_assessment_id: $aid,
                created_at: $now
            })
            """,
            {
                "action_id": action_id, "cid": case_id,
                "desc": f"High deception score ({detection['deception_score']:.2f}) detected. "
                        f"Verdict: {detection.get('verdict')}. Manual review required.",
                "aid": assessment_id, "now": now,
            },
        )
        logger.warning(
            "High deception score %.2f for case %s target %s — action created",
            detection["deception_score"], case_id, target_id,
        )

    return {
        "assessment_id": assessment_id,
        "target_type": target_type,
        "target_id": target_id or "direct_text",
        "deception_score": detection.get("deception_score"),
        "verdict": detection.get("verdict"),
        "dimensions": detection.get("dimensions"),
        "methodology": detection.get("methodology"),
        "limitations": detection.get("limitations"),
        "forensic_disclaimer": detection.get("forensic_disclaimer"),
        "model": detection.get("model"),
    }


@router.post("/cases/{case_id}/deception/batch")
def batch_assess_deception(
    case_id: str,
    body: BatchAssessRequest,
    db: Session = Depends(get_db),
):
    """Batch deception assessment for multiple artifacts."""
    _validate_case(case_id, db)
    results = []
    for aid in body.artifact_ids:
        try:
            result = assess_deception(
                case_id,
                AssessRequest(artifact_id=aid),
                db,
            )
            results.append(result)
        except Exception as e:
            results.append({"artifact_id": aid, "error": str(e)})
    return {
        "case_id": case_id,
        "total": len(results),
        "high_deception_count": sum(
            1 for r in results
            if isinstance(r.get("deception_score"), (int, float))
            and r["deception_score"] >= DECEPTION_THRESHOLD
        ),
        "results": results,
    }


@router.get("/cases/{case_id}/deception/assessments")
def list_deception_assessments(
    case_id: str,
    db: Session = Depends(get_db),
):
    """List all deception assessments for a case."""
    _validate_case(case_id, db)
    neo4j = get_neo4j_client()
    results = neo4j.execute_read(
        """
        MATCH (d:DeceptionAssessment {case_id: $cid})
        RETURN d ORDER BY d.assessed_at DESC
        """,
        {"cid": case_id},
    )
    return {
        "case_id": case_id,
        "assessments": [r["d"] for r in results],
        "total": len(results),
    }
