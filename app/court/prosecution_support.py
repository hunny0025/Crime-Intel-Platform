"""Prosecution Support Engine — structured prosecution materials.

Generates prosecution narrative, expert preparation guide, and
counter-narrative documentation from eliminated hypotheses.
"""

import json
import logging
from datetime import datetime, timezone

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def generate_prosecution_narrative(case_id: str) -> dict:
    """Structured prosecution narrative from Crime Twin + causal chain."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get ordered events from Crime Twin
    events = client.execute_read(
        """
        MATCH (e:Event {case_id: $cid})
        OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(e)
        OPTIONAL MATCH (e)-[:AT]->(l:Location)
        RETURN e.id AS id, e.event_type AS type,
               e.valid_from AS ts,
               coalesce(e.display_name, e.event_type) AS display,
               collect(DISTINCT coalesce(p.display_name, p.id)) AS participants,
               collect(DISTINCT coalesce(l.display_name, l.id)) AS locations
        ORDER BY e.valid_from
        """,
        {"cid": case_id},
    )

    # Build event sequence
    event_sequence = []
    for e in events:
        # Get integrity grades for supporting evidence
        grades = client.execute_read(
            """
            MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
            WHERE c.artifact_id IN $refs
            RETURN c.overall_integrity_grade AS grade
            """,
            {"cid": case_id, "refs": [e["id"]]},
        )

        event_sequence.append({
            "event_description": f"{e['display']} at {e.get('ts', 'unknown time')}",
            "participants": e.get("participants", []),
            "locations": e.get("locations", []),
            "supporting_evidence_refs": [e["id"]],
            "integrity_grades": [g["grade"] for g in grades] if grades else [],
            "timestamp_confidence": "high" if e.get("ts") else "unknown",
        })

    # Key assertions — top satisfied elements
    assertions = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le:LegalElement)
        WHERE r.satisfaction_score >= 0.7
        RETURN le.element_text AS text, r.satisfaction_score AS score,
               m.evidence_ref AS evidence_ref, le.id AS element_id
        ORDER BY r.satisfaction_score DESC LIMIT 5
        """,
        {"cid": case_id},
    )

    key_assertions = [{
        "assertion_text": a["text"],
        "supporting_evidence_refs": [a["evidence_ref"]],
        "element_ids_it_satisfies": [a["element_id"]],
        "satisfaction_score": a["score"],
        "vulnerability_to_defense": "low" if a["score"] >= 0.8 else "medium",
    } for a in assertions]

    # Evidence summary by type
    evidence_by_type = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        WHERE c.overall_integrity_grade IN ['A', 'B']
        RETURN c.artifact_id AS aid, c.overall_integrity_grade AS grade
        """,
        {"cid": case_id},
    )

    # Gaps in narrative (time periods with no events)
    gaps_in_narrative = []
    for i in range(len(event_sequence) - 1):
        curr = event_sequence[i]
        nxt = event_sequence[i + 1]
        if curr.get("timestamp_confidence") == "unknown" or nxt.get("timestamp_confidence") == "unknown":
            gaps_in_narrative.append({
                "between_events": [curr["event_description"][:40], nxt["event_description"][:40]],
                "note": "Time gap with no documented events",
            })

    return {
        "case_id": case_id,
        "generated_at": now,
        "event_sequence": event_sequence,
        "key_assertions": key_assertions,
        "evidence_summary_by_type": {
            "grade_a_b_artifacts": len(evidence_by_type),
        },
        "gaps_in_narrative": gaps_in_narrative,
    }


def get_expert_preparation_guide(case_id: str) -> dict:
    """Expert/witness preparation framework for prosecution."""
    client = get_neo4j_client()

    # Get Grade A/B artifacts satisfying critical elements
    strong = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        WHERE c.overall_integrity_grade IN ['A', 'B']
        MATCH (m:EvidenceMapping {case_id: $cid, evidence_ref: c.artifact_id})
              -[r:SATISFIES_ELEMENT]->(le:LegalElement)
        WHERE r.satisfaction_score >= 0.7
        RETURN c.artifact_id AS aid, c.overall_integrity_grade AS grade,
               le.element_text AS element_text, r.satisfaction_score AS score
        """,
        {"cid": case_id},
    )

    preparation = []
    for s in strong:
        preparation.append({
            "artifact_id": s["aid"],
            "integrity_grade": s["grade"],
            "what_it_proves": s["element_text"],
            "satisfaction_score": s["score"],
            "suggested_examination_points": [
                f"Establish the source and collection method of this evidence",
                f"Confirm the chain of custody was maintained throughout",
                f"Explain how this evidence demonstrates: {s['element_text'][:60]}",
                f"Confirm no alterations were made to the original evidence",
            ],
        })

    return {"case_id": case_id, "preparation_entries": preparation}


def get_counter_narratives(case_id: str) -> dict:
    """Counter-narrative documentation from eliminated hypotheses."""
    client = get_neo4j_client()

    eliminated = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'eliminated'})
        RETURN h.id AS id, h.narrative AS narrative,
               h.decisive_evidence_id AS evidence_id,
               h.decisive_evidence_reasoning AS reasoning,
               h.eliminated_at AS at
        ORDER BY h.eliminated_at
        """,
        {"cid": case_id},
    )

    counter_narratives = []
    for e in eliminated:
        counter_narratives.append({
            "hypothesis_narrative": e["narrative"],
            "why_eliminated": e.get("reasoning", ""),
            "decisive_evidence_ref": e.get("evidence_id", ""),
            "eliminated_at": e.get("at", ""),
            "this_establishes": f"This demonstrates that the investigation considered "
                                f"and ruled out '{e['narrative'][:60]}' because "
                                f"{e.get('reasoning', 'decisive evidence contradicted it')[:80]}.",
        })

    return {"case_id": case_id, "counter_narratives": counter_narratives}
