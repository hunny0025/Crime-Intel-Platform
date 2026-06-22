"""Legal Qualification Engine + Section Recommendation Engine.

Qualification: computes element_coverage and qualification_score per section.
Recommendation: ranks sections by evidential strength with gap recoverability.
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
from app.legal.explainable_reasoning import create_reasoning_trace

logger = logging.getLogger(__name__)


def qualify_sections(case_id: str, db: Optional[Session] = None) -> dict:
    """Run qualification scoring for all relevant sections."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    sections = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
              -[:MAPS_TO_LEGAL_SECTION]->(ls:LegalSection)
        RETURN ls.id AS section_id, ls.section_reference AS section_ref, ls.title AS title
        """,
        {"cid": case_id},
    )

    if not sections:
        sections = client.execute_read(
            "MATCH (ls:LegalSection) RETURN ls.id AS section_id, "
            "ls.section_reference AS section_ref, ls.title AS title",
        )

    qualifications = []
    for sec in sections:
        qual = _compute_qualification(client, case_id, sec["section_id"])
        qual_id = str(uuid.uuid4())

        # Create/update LegalQualification node
        client.execute_write(
            """
            MERGE (q:LegalQualification {case_id: $cid, legal_section_id: $sid})
            ON CREATE SET q.id = $qid, q.created_at = $now
            SET q.qualification_score = $qscore,
                q.element_coverage = $ecov,
                q.missing_elements = $missing,
                q.computed_at = $now,
                q.status = 'under_review',
                q.classification_tag = 'case_sensitive'
            """,
            {
                "cid": case_id, "sid": sec["section_id"],
                "qid": qual_id, "now": now,
                "qscore": qual["qualification_score"],
                "ecov": qual["element_coverage"],
                "missing": json.dumps(qual["missing_elements"]),
            },
        )

        qualifications.append({
            "section_id": sec["section_id"],
            "section_reference": sec.get("section_ref", ""),
            "title": sec.get("title", ""),
            **qual,
        })

        # Create explainable reasoning trace for each qualification
        conf_level = qual.get("confidence_level", "low")
        create_reasoning_trace(
            case_id=case_id,
            engine_source="qualification_engine",
            recommendation_text=f"Section {sec.get('section_ref', sec['section_id'])} — "
                                f"qualification score {qual['qualification_score']:.2f} ({conf_level})",
            why=qual.get("legal_basis", f"Element coverage {qual['element_coverage']:.0%}"),
            supporting_evidence=qual.get("supporting_reasons", []),
            satisfied_elements=[
                {"id": e["id"], "text": e["text"]}
                for e in qual.get("satisfied_detail", [])
            ],
            unsatisfied_elements=[
                {"id": mi["element_id"], "text": mi.get("element_text", "")}
                for mi in qual.get("missing_ingredients", [])
            ],
            improvement_suggestions=[
                mi.get("suggested_action", "")
                for mi in qual.get("missing_ingredients", []) if mi.get("suggested_action")
            ],
            confidence_level=conf_level,
            legal_basis=qual.get("legal_basis", ""),
        )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Legal qualification computed for {len(qualifications)} sections",
            actor="system:qualification_engine",
        )
        db.commit()

    return {"case_id": case_id, "qualifications": qualifications}


def get_recommended_sections(case_id: str) -> dict:
    """Return ranked section list with gap recoverability analysis."""
    client = get_neo4j_client()

    quals = client.execute_read(
        """
        MATCH (q:LegalQualification {case_id: $cid})
        MATCH (ls:LegalSection {id: q.legal_section_id})
        RETURN q.id AS qual_id, q.legal_section_id AS section_id,
               q.qualification_score AS qscore, q.element_coverage AS ecov,
               q.missing_elements AS missing, q.status AS status,
               ls.section_reference AS section_ref, ls.title AS title
        ORDER BY q.qualification_score DESC, q.element_coverage DESC
        """,
        {"cid": case_id},
    )

    recommendations = []
    for q in quals:
        missing = json.loads(q.get("missing", "[]").replace("'", '"')) if q.get("missing") else []

        # Analyze recoverability of missing elements
        missing_analysis = []
        for elem_id in missing:
            elem_info = client.execute_read(
                """
                MATCH (le:LegalElement {id: $eid})
                OPTIONAL MATCH (g:EvidenceGap {case_id: $cid})-[:RELATES_TO]->(le)
                WHERE g.status = 'open'
                RETURN le.element_text AS text,
                       le.evidence_types_typically_required AS req,
                       count(g) AS open_gaps
                """,
                {"eid": elem_id, "cid": case_id},
            )
            if elem_info:
                has_gap = elem_info[0].get("open_gaps", 0) > 0
                missing_analysis.append({
                    "element_id": elem_id,
                    "element_text": elem_info[0].get("text", ""),
                    "evidence_types_needed": elem_info[0].get("req", ""),
                    "has_open_evidence_gap": has_gap,
                    "recoverability": "recoverable" if has_gap else "structural_weakness",
                })

        # Build recommendation basis
        ecov = q.get("ecov", 0) or 0
        qscore = q.get("qscore", 0) or 0
        warning = ""
        if ecov < 0.5:
            warning = "WARNING: insufficient_coverage — fewer than half the elements have support. "

        basis = (
            f"{warning}{q.get('section_ref', '')} "
            f"{'applicable' if qscore >= 0.6 else 'under review'} — "
            f"element coverage {ecov:.0%}, qualification score {qscore:.2f}"
        )

        recoverable = sum(1 for m in missing_analysis if m["recoverability"] == "recoverable")
        structural = sum(1 for m in missing_analysis if m["recoverability"] == "structural_weakness")
        if recoverable:
            basis += f"; {recoverable} missing element(s) have open evidence gaps (recoverable)"
        if structural:
            basis += f"; {structural} missing element(s) are structural weaknesses"

        recommendations.append({
            "qualification_id": q["qual_id"],
            "section_id": q["section_id"],
            "section_reference": q.get("section_ref", ""),
            "title": q.get("title", ""),
            "qualification_score": qscore,
            "element_coverage": ecov,
            "status": q.get("status", "under_review"),
            "missing_elements": missing_analysis,
            "recommendation_basis": basis,
        })

    return {"case_id": case_id, "recommendations": recommendations}


def set_qualification_status(case_id: str, qual_id: str, status: str,
                             db: Optional[Session] = None) -> dict:
    """Investigator marks a section applicable or not_applicable."""
    if status not in ("applicable", "not_applicable"):
        return {"error": "Status must be 'applicable' or 'not_applicable'"}

    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        "MATCH (q:LegalQualification {id: $qid, case_id: $cid}) "
        "SET q.status = $status, q.status_set_at = $now",
        {"qid": qual_id, "cid": case_id, "status": status, "now": now},
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Qualification {qual_id} set to {status}",
            actor="system:qualification_engine",
            graph_refs=[qual_id],
        )
        db.commit()

    return {"qualification_id": qual_id, "status": status}


def _compute_qualification(client, case_id: str, section_id: str) -> dict:
    """Compute qualification_score, element_coverage, confidence, and detailed analysis."""
    elements = client.execute_read(
        """
        MATCH (ls:LegalSection {id: $sid})-[:HAS_ELEMENT]->(le:LegalElement)
        OPTIONAL MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
        WHERE m.confirmation_status IN ['auto_suggested', 'investigator_confirmed']
        RETURN le.id AS element_id,
               le.element_text AS element_text,
               le.evidence_types_typically_required AS required_types,
               max(r.satisfaction_score) AS max_score,
               collect(DISTINCT {ref: m.evidence_ref, type: m.evidence_type, score: r.satisfaction_score}) AS evidence
        """,
        {"sid": section_id, "cid": case_id},
    )

    if not elements:
        return {
            "qualification_score": 0.0, "element_coverage": 0.0,
            "confidence_level": "low",
            "missing_elements": [],
            "missing_ingredients": [],
            "supporting_reasons": [],
            "satisfied_detail": [],
            "legal_basis": "",
            "judicial_interpretations": [],
        }

    total = len(elements)
    satisfied = 0
    score_sum = 0.0
    missing = []
    missing_ingredients = []
    supporting_reasons = []
    satisfied_detail = []

    for e in elements:
        max_score = e.get("max_score") or 0
        evidence_list = [ev for ev in (e.get("evidence") or []) if ev.get("ref")]

        if max_score >= 0.4:
            satisfied += 1
            score_sum += max_score
            satisfied_detail.append({
                "id": e["element_id"],
                "text": e.get("element_text", ""),
                "max_score": max_score,
            })
            for ev in evidence_list:
                if ev.get("ref"):
                    supporting_reasons.append({
                        "element_id": e["element_id"],
                        "evidence_ref": ev["ref"],
                        "evidence_type": ev.get("type", ""),
                        "score": ev.get("score", 0),
                    })
        else:
            missing.append(e["element_id"])
            req_types = e.get("required_types", "")
            if isinstance(req_types, str):
                try:
                    req_types = json.loads(req_types.replace("'", '"'))
                except (json.JSONDecodeError, ValueError):
                    req_types = [req_types] if req_types else []
            elif not isinstance(req_types, list):
                req_types = list(req_types) if req_types else []

            suggested = _suggest_action(e.get("element_text", ""), req_types)
            missing_ingredients.append({
                "element_id": e["element_id"],
                "element_text": e.get("element_text", ""),
                "required_evidence_types": req_types,
                "suggested_action": suggested,
                "priority": "high" if max_score == 0 else "medium",
            })

    coverage = satisfied / total if total > 0 else 0
    qual_score = score_sum / total if total > 0 else 0

    # Confidence level
    if qual_score >= 0.8 and coverage >= 0.8:
        confidence_level = "high"
    elif qual_score >= 0.6 or coverage >= 0.6:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # Legal basis description
    section_info = client.execute_read(
        "MATCH (ls:LegalSection {id: $sid}) RETURN ls.summary AS summary, ls.title AS title, ls.section_number AS snum",
        {"sid": section_id},
    )
    legal_basis = ""
    if section_info:
        legal_basis = f"Section {section_info[0].get('snum', '')} — {section_info[0].get('title', '')}: {section_info[0].get('summary', '')[:200]}"

    # Judicial interpretations
    ji_rows = client.execute_read(
        """
        MATCH (ji:JudicialInterpretation)-[:INTERPRETS]->(ls:LegalSection {id: $sid})
        OPTIONAL MATCH (ji)-[:DERIVED_FROM]->(cl:CaseLaw)
        RETURN ji.rule AS rule, ji.holding AS holding,
               cl.citation AS citation, cl.title AS case_title
        """,
        {"sid": section_id},
    )
    judicial_interpretations = [
        {
            "rule": ji.get("rule", ""),
            "holding": ji.get("holding", ""),
            "citation": ji.get("citation", ""),
            "case_title": ji.get("case_title", ""),
        }
        for ji in ji_rows
    ]

    return {
        "qualification_score": round(qual_score, 4),
        "element_coverage": round(coverage, 4),
        "confidence_level": confidence_level,
        "missing_elements": missing,
        "missing_ingredients": missing_ingredients,
        "supporting_reasons": supporting_reasons,
        "satisfied_detail": satisfied_detail,
        "legal_basis": legal_basis,
        "judicial_interpretations": judicial_interpretations,
    }


def _suggest_action(element_text: str, req_types: list) -> str:
    """Generate a suggested investigation action for a missing element."""
    text_lower = element_text.lower()
    if "intent" in text_lower or "dishonest" in text_lower or "fraudulent" in text_lower:
        return ("Obtain communication records (emails, messages, call logs) showing "
                "pre-existing plan or deliberate misrepresentation at the time of the act.")
    if "consent" in text_lower:
        return ("Record victim's statement under BNSS Section 183 confirming "
                "absence of consent. Corroborate with independent witness testimony.")
    if "delivery" in text_lower or "property" in text_lower:
        return ("Obtain financial records, bank statements, and transaction logs "
                "showing transfer of property or funds from victim to accused.")
    if "document" in text_lower or "electronic record" in text_lower:
        return ("Seize the device containing the forged document/record. "
                "Submit for forensic examination with BSA Section 63 certificate.")
    if "threat" in text_lower or "fear" in text_lower:
        return ("Preserve all threatening communications (screenshots, call recordings). "
                "Record victim statement describing the nature and impact of the threats.")

    # Default suggestion based on required types
    if req_types:
        return f"Collect evidence of type(s): {', '.join(req_types[:3])} to satisfy this element."
    return "Investigate further to establish this element with corroborating evidence."
