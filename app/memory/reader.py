import uuid
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models import Case, EvidenceArtifact, MemoryRecord
from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

def get_investigation_state(case_id: str, as_of: Optional[datetime] = None, db: Optional[Session] = None) -> dict:
    """
    Unified state reader for an investigation case.
    Reconstructs the timeline, database records, memory traces, and graph state
    for the case as of the optional `as_of` timestamp.
    """
    if db is None:
        from app.db.session import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        case_uuid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id

        # 1. Fetch Case metadata
        case = db.query(Case).filter(Case.case_id == case_uuid).first()
        if not case:
            return {"error": "Case not found"}

        case_meta = {
            "case_id": str(case.case_id),
            "case_type": case.case_type,
            "status": case.status.value if hasattr(case.status, "value") else case.status,
            "classification_tag": case.classification_tag.value if hasattr(case.classification_tag, "value") else case.classification_tag,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "created_by": case.created_by,
            "agency_id": str(case.agency_id) if case.agency_id else None,
        }

        # 2. Fetch Evidence Artifacts
        artifacts_query = db.query(EvidenceArtifact).filter(EvidenceArtifact.case_id == case_uuid)
        if as_of:
            artifacts_query = artifacts_query.filter(EvidenceArtifact.created_at <= as_of)
        artifacts = artifacts_query.order_by(EvidenceArtifact.created_at.asc()).all()

        evidence_list = []
        for a in artifacts:
            evidence_list.append({
                "artifact_id": str(a.artifact_id),
                "source_tool": a.source_tool,
                "source_device_id": a.source_device_id,
                "collection_timestamp_utc": a.collection_timestamp_utc.isoformat() if a.collection_timestamp_utc else None,
                "original_timezone": a.original_timezone,
                "content_hash": a.content_hash,
                "record_hash": a.record_hash,
                "content_pointer": a.content_pointer,
                "classification_tag": a.classification_tag.value if hasattr(a.classification_tag, "value") else a.classification_tag,
                "composite_reliability_score": a.composite_reliability_score,
                "acquisition_method": a.acquisition_method,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })

        # 3. Fetch Memory Records (Case Diary)
        memory_query = db.query(MemoryRecord).filter(MemoryRecord.case_id == case_uuid)
        if as_of:
            memory_query = memory_query.filter(MemoryRecord.timestamp <= as_of)
        memory_records = memory_query.order_by(MemoryRecord.timestamp.asc()).all()

        diary = []
        beliefs = {}
        for r in memory_records:
            if r.beliefs_after:
                beliefs = r.beliefs_after
            diary.append({
                "record_id": str(r.record_id),
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "record_type": r.record_type.value if hasattr(r.record_type, "value") else str(r.record_type),
                "description": r.description,
                "evidence_basis": r.evidence_basis,
                "graph_refs": r.graph_refs,
                "beliefs_before": r.beliefs_before,
                "beliefs_after": r.beliefs_after,
                "actor": r.actor,
                "reasoning": r.reasoning,
                "tags": r.memory_tags,
            })

        # 4. Fetch Graph State from Neo4j
        client = get_neo4j_client()

        # Hypotheses
        hypotheses = client.execute_read(
            """
            MATCH (h:Hypothesis {case_id: $cid})
            RETURN h.id AS id, h.probability AS prob, h.narrative AS narrative, h.status AS status
            ORDER BY h.probability DESC
            """,
            {"cid": str(case_uuid)},
        )

        hyp_list = []
        for h in hypotheses:
            prob = h["prob"]
            if as_of and h["id"] in beliefs:
                prob = beliefs[h["id"]]
            hyp_list.append({
                "hypothesis_id": h["id"],
                "narrative": h["narrative"],
                "probability": prob,
                "status": h["status"]
            })

        # Key Contradictions
        contradictions = client.execute_read(
            """
            MATCH (c:Contradiction {case_id: $cid})
            RETURN c.id AS id, c.description AS description, c.severity AS severity, c.status AS status
            ORDER BY CASE c.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
            """,
            {"cid": str(case_uuid)},
        )

        # Evidence Gaps
        gaps = client.execute_read(
            """
            MATCH (g:EvidenceGap {case_id: $cid})
            RETURN g.id AS id, g.description AS description, g.urgency AS urgency, g.status AS status
            ORDER BY CASE g.urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
            """,
            {"cid": str(case_uuid)},
        )

        # Assumptions
        assumptions = client.execute_read(
            """
            MATCH (h:Hypothesis {case_id: $cid, status: 'active'})-[:REQUIRES_ASSUMPTION]->(a:Assumption)
            RETURN a.id AS id, a.statement AS statement, a.criticality AS criticality,
                   a.verification_status AS verification_status, h.narrative AS hypothesis
            """,
            {"cid": str(case_uuid)},
        )

        # Attention entities
        attention = client.execute_read(
            """
            MATCH (n)
            WHERE n.case_id = $cid AND n.attention_value IS NOT NULL AND n.attention_value > 0
            RETURN n.id AS id, labels(n)[0] AS label,
                   coalesce(n.display_name, n.id) AS display,
                   n.attention_value AS score
            ORDER BY n.attention_value DESC
            LIMIT 10
            """,
            {"cid": str(case_uuid)},
        )

        return {
            "case_metadata": case_meta,
            "evidence_artifacts": evidence_list,
            "diary": diary,
            "hypotheses": hyp_list,
            "contradictions": contradictions,
            "gaps": gaps,
            "assumptions": assumptions,
            "attention_entities": attention,
            "current_beliefs": beliefs,
        }

    finally:
        if should_close:
            db.close()
