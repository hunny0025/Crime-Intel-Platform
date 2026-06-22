"""Phase 6 — Legal Intelligence Layer API endpoints.

All legal outputs are ADVISORY ONLY and require investigator + prosecutorial review.
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case

from app.legal.element_mapper import (
    map_elements_for_case, get_element_map, get_evidence_law_map,
    confirm_mapping, reject_mapping, get_evidence_strength_matrix,
)
from app.legal.qualification_engine import (
    qualify_sections, get_recommended_sections, set_qualification_status,
)
from app.legal.sufficiency_engine import (
    generate_sufficiency_report, get_sufficiency_report,
)
from app.legal.procedural_engine import (
    scan_compliance, get_compliance_report, confirm_requirement,
    get_procedural_timeline, generate_compliance_alerts,
)
from app.legal.chargesheet_engine import (
    generate_chargesheet_readiness, get_chargesheet_readiness,
    get_readiness_history,
    generate_chargesheet_package, get_chargesheet, get_chargesheet_history,
    get_filing_readiness,
)
from app.legal.chargesheet_export import export_chargesheet_text
from app.legal.recommendation_engine import generate_investigation_recommendations
from app.legal.explainable_reasoning import get_reasoning_traces

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legal-intelligence"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Prompt 31: Element Mapping ──────────────────────────────────────────

class MapElementsRequest(BaseModel):
    threshold: float = 0.4


class RejectMappingRequest(BaseModel):
    rejection_reason: str


@router.post("/cases/{case_id}/legal/map-elements")
def map_elements(case_id: str, body: MapElementsRequest = MapElementsRequest(),
                 db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return map_elements_for_case(case_id, body.threshold, db)


@router.get("/cases/{case_id}/legal/element-map")
def element_map(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_element_map(case_id)


@router.get("/cases/{case_id}/legal/evidence-law-map")
def evidence_law_map(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_evidence_law_map(case_id)


@router.post("/cases/{case_id}/legal/element-map/{mapping_id}/confirm")
def confirm_element(case_id: str, mapping_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return confirm_mapping(case_id, mapping_id, db)


@router.post("/cases/{case_id}/legal/element-map/{mapping_id}/reject")
def reject_element(case_id: str, mapping_id: str,
                   body: RejectMappingRequest, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return reject_mapping(case_id, mapping_id, body.rejection_reason, db)


# ── Prompt 32: Qualification + Recommendation ───────────────────────────

class QualificationStatusRequest(BaseModel):
    status: str  # applicable / not_applicable


@router.post("/cases/{case_id}/legal/qualify")
def qualify(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return qualify_sections(case_id, db)


@router.get("/cases/{case_id}/legal/recommended-sections")
def recommended_sections(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_recommended_sections(case_id)


@router.post("/cases/{case_id}/legal/qualifications/{qual_id}/set-status")
def set_status(case_id: str, qual_id: str,
               body: QualificationStatusRequest, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return set_qualification_status(case_id, qual_id, body.status, db)


# ── Prompt 33: Sufficiency ──────────────────────────────────────────────

@router.post("/cases/{case_id}/legal/sufficiency-report/{section_id}")
def create_sufficiency(case_id: str, section_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_sufficiency_report(case_id, section_id, db)


@router.get("/cases/{case_id}/legal/sufficiency-report/{section_id}")
def view_sufficiency(case_id: str, section_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_sufficiency_report(case_id, section_id)


# ── Prompt 34: Procedural Compliance ────────────────────────────────────

class ComplianceConfirmRequest(BaseModel):
    confirmation_notes: str


@router.post("/cases/{case_id}/legal/compliance/scan")
def compliance_scan(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return scan_compliance(case_id, db)


@router.get("/cases/{case_id}/legal/compliance/report")
def compliance_report(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_compliance_report(case_id)


@router.get("/cases/{case_id}/legal/procedural-timeline")
def procedural_timeline(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_procedural_timeline(case_id, db)


@router.post("/cases/{case_id}/legal/compliance/{requirement_id}/confirm")
def compliance_confirm(case_id: str, requirement_id: str,
                       body: ComplianceConfirmRequest, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return confirm_requirement(case_id, requirement_id, body.confirmation_notes, db)


# ── Prompt 35: Chargesheet Readiness ────────────────────────────────────

@router.post("/cases/{case_id}/legal/chargesheet-readiness")
def create_readiness(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_chargesheet_readiness(case_id, db)


@router.get("/cases/{case_id}/legal/chargesheet-readiness")
def view_readiness(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_chargesheet_readiness(case_id)


@router.get("/cases/{case_id}/legal/chargesheet-readiness/history")
def readiness_history(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_readiness_history(case_id)


@router.get("/cases/{case_id}/legal/recommendations")
def legal_recommendations(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_investigation_recommendations(case_id, db)


# ── Chargesheet Package Endpoints ───────────────────────────────────────

@router.post("/cases/{case_id}/legal/chargesheet/generate")
def create_chargesheet(case_id: str, db: Session = Depends(get_db)):
    """Generate a full chargesheet package for the case."""
    _validate_case(case_id, db)
    return generate_chargesheet_package(case_id, db)


@router.get("/cases/{case_id}/legal/chargesheet")
def view_chargesheet(case_id: str, db: Session = Depends(get_db)):
    """Get the latest chargesheet package."""
    _validate_case(case_id, db)
    return get_chargesheet(case_id)


@router.get("/cases/{case_id}/legal/chargesheet/history")
def chargesheet_history(case_id: str, db: Session = Depends(get_db)):
    """List all chargesheet versions."""
    _validate_case(case_id, db)
    return get_chargesheet_history(case_id)


@router.get("/cases/{case_id}/legal/chargesheet/filing-readiness")
def chargesheet_filing_readiness(case_id: str, db: Session = Depends(get_db)):
    """Operational filing readiness summary."""
    _validate_case(case_id, db)
    return get_filing_readiness(case_id)


@router.get("/cases/{case_id}/legal/chargesheet/export")
def chargesheet_export(case_id: str, db: Session = Depends(get_db)):
    """Export the latest chargesheet as structured text."""
    _validate_case(case_id, db)
    package = get_chargesheet(case_id)
    if "error" in package:
        raise HTTPException(status_code=404, detail=package["error"])
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=export_chargesheet_text(package),
        media_type="text/plain",
    )


@router.get("/cases/{case_id}/legal/chargesheet/{chargesheet_id}")
def view_chargesheet_by_id(case_id: str, chargesheet_id: str,
                           db: Session = Depends(get_db)):
    """Get a specific chargesheet by ID."""
    _validate_case(case_id, db)
    return get_chargesheet(case_id, chargesheet_id)


class AllegationNoteRequest(BaseModel):
    author: str
    note_text: str


@router.post("/cases/{case_id}/legal/chargesheet/allegations/{allegation_id}/note")
def add_allegation_note(case_id: str, allegation_id: str,
                        body: AllegationNoteRequest,
                        db: Session = Depends(get_db)):
    """Add a prosecutor note to an allegation."""
    _validate_case(case_id, db)
    from sqlalchemy import text as sql_text
    try:
        db.execute(sql_text("""
            INSERT INTO chargesheet_notes (note_id, allegation_id, case_id, author, note_text)
            VALUES (:nid, :aid, :cid, :author, :text)
        """), {
            "nid": uuid.uuid4(),
            "aid": uuid.UUID(allegation_id),
            "cid": uuid.UUID(case_id),
            "author": body.author,
            "text": body.note_text,
        })
        db.commit()
        return {"status": "note_added", "allegation_id": allegation_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ── Legal Intelligence Subsystem Upgraded Routes ────────────────────────

@router.get("/cases/{case_id}/legal/evidence-strength-matrix")
def evidence_strength_matrix(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_evidence_strength_matrix(case_id)


@router.get("/cases/{case_id}/legal/compliance/alerts")
def compliance_alerts(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return generate_compliance_alerts(case_id, db)


@router.get("/cases/{case_id}/legal/reasoning-traces")
def reasoning_traces(case_id: str, engine_source: Optional[str] = None,
                     limit: int = 50, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    return get_reasoning_traces(case_id, engine_source, limit)


@router.post("/cases/{case_id}/legal/full-analysis")
def full_analysis(case_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    
    # Run all engines
    mappings = map_elements_for_case(case_id, threshold=0.4, db=db)
    qualifications = qualify_sections(case_id, db=db)
    compliance = scan_compliance(case_id, db=db)
    readiness = generate_chargesheet_readiness(case_id, db=db)
    recs = generate_investigation_recommendations(case_id, db=db)
    
    # Gather reports
    strength_matrix = get_evidence_strength_matrix(case_id)
    timeline = get_procedural_timeline(case_id, db)
    alerts = generate_compliance_alerts(case_id, db)
    recommended_sects = get_recommended_sections(case_id)
    traces = get_reasoning_traces(case_id, limit=20)
    
    return {
        "case_id": case_id,
        "unified_legal_analysis": {
            "evidence_mappings": mappings,
            "evidence_strength_matrix": strength_matrix,
            "qualifications": recommended_sects,
            "procedural_compliance": compliance,
            "procedural_timeline": timeline,
            "compliance_alerts": alerts,
            "chargesheet_readiness": readiness,
            "recommendations": recs,
            "explainable_reasoning_traces": traces,
        },
        "disclaimer": "This analysis is automatically generated for investigative support. All outputs are advisory only and require independent legal, prosecutorial, and judicial review.",
    }


class Section65BSubmitRequest(BaseModel):
    artifact_id: str
    investigator_id: str
    signature_metadata: str
    date: str
    hash: str


@router.get("/cases/{case_id}/legal/section-65b/draft")
def get_section_65b_draft(
    case_id: str,
    artifact_id: str,
    investigator_name: str = "investigator",
    db: Session = Depends(get_db),
):
    _validate_case(case_id, db)
    from app.legal.section_65b import generate_65b_certificate_draft
    try:
        draft = generate_65b_certificate_draft(case_id, artifact_id, investigator_name, db)
        return draft
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/cases/{case_id}/legal/section-65b/pdf")
def get_section_65b_pdf(
    case_id: str,
    artifact_id: str,
    investigator_name: str = "investigator",
    db: Session = Depends(get_db),
):
    _validate_case(case_id, db)
    from app.legal.section_65b import generate_65b_certificate_draft, generate_65b_pdf
    try:
        draft = generate_65b_certificate_draft(case_id, artifact_id, investigator_name, db)
        pdf_bytes = generate_65b_pdf(draft)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=section_65b_{artifact_id}.pdf"}
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/cases/{case_id}/legal/section-65b/submit")
def submit_section_65b(
    case_id: str,
    body: Section65BSubmitRequest,
    db: Session = Depends(get_db),
):
    _validate_case(case_id, db)

    try:
        art_uuid = uuid.UUID(body.artifact_id)
        case_uuid = uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    from app.db.models import EvidenceArtifact, MemoryRecordType
    from app.memory.writer import write_memory_record
    from app.graph.driver import get_neo4j_client
    from datetime import datetime, timezone

    artifact = db.query(EvidenceArtifact).filter(
        EvidenceArtifact.artifact_id == art_uuid,
        EvidenceArtifact.case_id == case_uuid
    ).first()
    if not artifact:
        raise HTTPException(status_code=404, detail="Evidence artifact not found")

    client = get_neo4j_client()
    try:
        client.execute_write(
            """
            MATCH (n {id: $aid, case_id: $cid})
            SET n.section_65b_certified = true,
                n.section_65b_signature = $sig,
                n.section_65b_signed_by = $signed_by
            """,
            {"aid": body.artifact_id, "cid": case_id, "sig": body.signature_metadata, "signed_by": body.investigator_id}
        )

        client.execute_write(
            """
            MERGE (r:ProceduralComplianceRecord {case_id: $cid, requirement_id: 'section_65b_bsa_2023'})
            SET r.status = 'compliant',
                r.confirmed_at = $now,
                r.confirmed_by = $investigator,
                r.confirmation_notes = $notes
            """,
            {
                "cid": case_id,
                "now": datetime.now(timezone.utc).isoformat(),
                "investigator": body.investigator_id,
                "notes": f"Signed certificate submitted. Signature hash: {body.hash[:10]}..."
            }
        )
    except Exception as e:
        logger.warning("Failed to update Neo4j for 65B submission: %s", e)

    write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType.decision_made,
        description=f"Section 65B BSA certificate submitted and verified for artifact {body.artifact_id}.",
        actor=body.investigator_id,
        evidence_basis=[body.artifact_id],
        reasoning=f"Signature Metadata: {body.signature_metadata}. Hash: {body.hash}."
    )
    db.commit()

    return {"status": "certified", "artifact_id": body.artifact_id}
