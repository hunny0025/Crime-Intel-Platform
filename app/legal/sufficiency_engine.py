"""Evidence Sufficiency Engine — admissibility, corroboration, integrity scoring.

Goes beyond element_coverage to assess court-scrutiny readiness under BSA 2023.
Combined sufficiency = 0.4×admissibility + 0.35×corroboration + 0.25×integrity.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def generate_sufficiency_report(case_id: str, section_id: str,
                                db: Optional[Session] = None) -> dict:
    """Generate EvidenceSufficiencyReport for a section."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    report_id = str(uuid.uuid4())

    elements = client.execute_read(
        """
        MATCH (ls:LegalSection {id: $sid})-[:HAS_ELEMENT]->(le:LegalElement)
        OPTIONAL MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
        WHERE m.confirmation_status IN ['auto_suggested', 'investigator_confirmed']
        RETURN le.id AS element_id, le.element_text AS element_text,
               collect({
                   mapping_id: m.id, evidence_ref: m.evidence_ref,
                   score: r.satisfaction_score, evidence_type: m.evidence_type
               }) AS mappings
        """,
        {"sid": section_id, "cid": case_id},
    )

    per_element = []
    gaps_created = 0

    for elem in elements:
        mappings = [m for m in elem["mappings"] if m.get("mapping_id")]

        admissibility = _compute_admissibility(client, case_id, mappings)
        corroboration = _compute_corroboration(client, case_id, mappings, db)
        integrity = _compute_integrity(client, case_id, mappings)

        sufficiency = (0.4 * admissibility + 0.35 * corroboration + 0.25 * integrity)

        weakness_flags = []
        if admissibility < 0.5:
            weakness_flags.append("chain_of_custody_gap")
        if corroboration <= 0.4:
            weakness_flags.append("single_source_only")
        if integrity < 0.5:
            weakness_flags.append("timestamp_integrity_low")
        # Check legal_process documentation
        has_legal_process = any(
            _check_legal_process(client, m.get("evidence_ref", ""))
            for m in mappings
        )
        if not has_legal_process and mappings:
            weakness_flags.append("legal_process_undocumented")

        per_element.append({
            "element_id": elem["element_id"],
            "element_text": elem.get("element_text", ""),
            "sufficiency_score": round(sufficiency, 4),
            "admissibility_score": round(admissibility, 4),
            "corroboration_score": round(corroboration, 4),
            "integrity_score": round(integrity, 4),
            "weakness_flags": weakness_flags,
        })

        # Auto-create EvidenceGap for single-source elements
        if "single_source_only" in weakness_flags and sufficiency < 0.6:
            _create_corroboration_gap(client, case_id, elem, now)
            gaps_created += 1

    # Store report node
    client.execute_write(
        """
        CREATE (r:EvidenceSufficiencyReport {
            id: $rid, case_id: $cid, legal_section_id: $sid,
            generated_at: $now,
            per_element_scores: $scores,
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "rid": report_id, "cid": case_id, "sid": section_id,
            "now": now, "scores": json.dumps(per_element),
        },
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Sufficiency report generated for section {section_id}",
            actor="system:sufficiency_engine",
            graph_refs=[report_id],
        )
        db.commit()

    return {
        "report_id": report_id,
        "case_id": case_id,
        "section_id": section_id,
        "generated_at": now,
        "per_element_scores": per_element,
        "gaps_auto_created": gaps_created,
    }


def get_sufficiency_report(case_id: str, section_id: str) -> dict:
    """Return latest sufficiency report with weakness recommendations."""
    client = get_neo4j_client()

    report = client.execute_read(
        """
        MATCH (r:EvidenceSufficiencyReport {case_id: $cid, legal_section_id: $sid})
        RETURN r.id AS id, r.generated_at AS at, r.per_element_scores AS scores
        ORDER BY r.generated_at DESC LIMIT 1
        """,
        {"cid": case_id, "sid": section_id},
    )

    if not report:
        return {"error": "No sufficiency report found for this section"}

    scores = json.loads(report[0].get("scores", "[]").replace("'", '"')) \
        if report[0].get("scores") else []

    # Add recommendations for each weakness
    for elem in scores:
        recs = []
        for flag in elem.get("weakness_flags", []):
            recs.append(_weakness_recommendation(flag, elem))
        elem["recommendations"] = recs

    return {
        "report_id": report[0]["id"],
        "generated_at": report[0]["at"],
        "per_element_scores": scores,
    }


def _compute_admissibility(client, case_id: str, mappings: list) -> float:
    """Admissibility score based on chain of custody and legal process."""
    if not mappings:
        return 0.0

    scores = []
    for m in mappings:
        ref = m.get("evidence_ref", "")
        # Check chain of custody
        chain_ok = _check_chain_integrity(client, ref)
        legal_process = _check_legal_process(client, ref)

        score = 1.0
        if not chain_ok:
            score = 0.0  # Broken chain = inadmissible
        elif not legal_process:
            score = 0.5  # No documented legal process = warning
        scores.append(score)

    return sum(scores) / len(scores) if scores else 0.0


def _compute_corroboration(client, case_id: str, mappings: list, db: Optional[Session] = None) -> float:
    """Corroboration: count distinct source tools. 1=0.4, 2=0.7, 3+=1.0."""
    if not mappings:
        return 0.0

    if db:
        reliability_scores = []
        for m in mappings:
            ref = m.get("evidence_ref", "")
            try:
                res = client.execute_read(
                    "MATCH (n {id: $nid}) RETURN n.artifact_id AS artifact_id",
                    {"nid": ref}
                )
                artifact_id = None
                if res and res[0].get("artifact_id"):
                    artifact_id = res[0]["artifact_id"]
                else:
                    artifact_id = ref

                if artifact_id:
                    import uuid as pyuuid
                    aid = pyuuid.UUID(str(artifact_id))
                    from app.intelligence.reliability import compute_reliability
                    score = compute_reliability(str(aid), case_id, db)
                    if score is not None:
                        reliability_scores.append(score.corroboration_score)
            except Exception as e:
                logger.error(f"Error getting corroboration from reliability score: {e}")

        if reliability_scores:
            return sum(reliability_scores) / len(reliability_scores)

    source_tools = set()
    for m in mappings:
        ref = m.get("evidence_ref", "")
        sources = client.execute_read(
            "MATCH (n {id: $ref}) RETURN n.source_tool AS st",
            {"ref": ref},
        )
        if sources and sources[0].get("st"):
            source_tools.add(sources[0]["st"])

    count = len(source_tools)
    if count >= 3:
        return 1.0
    elif count == 2:
        return 0.7
    elif count == 1:
        return 0.4
    return 0.0


def _compute_integrity(client, case_id: str, mappings: list) -> float:
    """Mean timestamp_integrity_score across supporting evidence."""
    if not mappings:
        return 0.0

    scores = []
    for m in mappings:
        ref = m.get("evidence_ref", "")
        result = client.execute_read(
            "MATCH ()-[r {id: $ref}]->() RETURN r.timestamp_integrity_score AS tis",
            {"ref": ref},
        )
        if result and result[0].get("tis") is not None:
            scores.append(result[0]["tis"])
        else:
            scores.append(0.5)  # Default if not scored

    return sum(scores) / len(scores) if scores else 0.5


def _check_chain_integrity(client, evidence_ref: str) -> bool:
    """Check if evidence chain of custody is intact."""
    # In production this queries the chain_of_custody_log table
    # Simplified: check for a hash_verified property
    result = client.execute_read(
        "MATCH (n {id: $ref}) RETURN n.hash_verified AS hv",
        {"ref": evidence_ref},
    )
    if result and result[0].get("hv") is not None:
        return result[0]["hv"]
    return True  # Assume intact if not explicitly broken


def _check_legal_process(client, evidence_ref: str) -> bool:
    """Check if evidence has legal_process_reference."""
    result = client.execute_read(
        "MATCH (n {id: $ref}) RETURN n.legal_process_reference AS lpr",
        {"ref": evidence_ref},
    )
    return bool(result and result[0].get("lpr"))


def _create_corroboration_gap(client, case_id: str, elem: dict, now: str):
    """Auto-create EvidenceGap for single-source elements."""
    gap_id = str(uuid.uuid4())
    client.execute_write(
        """
        CREATE (g:EvidenceGap {
            id: $gid, case_id: $cid,
            gap_type: 'corroboration_needed',
            description: $desc,
            urgency: 'medium', status: 'open',
            expected_value: 'high',
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "gid": gap_id, "cid": case_id,
            "desc": f"Corroborating evidence needed for legal element "
                    f"'{elem.get('element_text', elem['element_id'])}' — "
                    f"currently single-source, insufficient for strong admissibility.",
            "now": now,
        },
    )


def _weakness_recommendation(flag: str, elem: dict) -> str:
    """Generate plain-language recommendation for a weakness flag."""
    recs = {
        "chain_of_custody_gap": (
            "Chain of custody gap detected — verify handling between "
            "all custodians in the custody log to establish unbroken chain"
        ),
        "single_source_only": (
            f"Element '{elem.get('element_text', '')[:40]}' has single-source evidence — "
            f"seek independent corroboration via alternative evidence types"
        ),
        "timestamp_integrity_low": (
            "Timestamp integrity is low — seek corroborating timestamps from "
            "independent sources (CDR, CCTV, GPS)"
        ),
        "legal_process_undocumented": (
            "Legal process documentation missing — ensure seizure/collection "
            "has proper legal authorization documented in the case file"
        ),
    }
    return recs.get(flag, f"Address weakness: {flag}")
