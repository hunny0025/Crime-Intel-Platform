"""Theory Engine — Hypothesis lifecycle: SPAWN, ELIMINATE, EXPLAIN.

The Theory Engine never writes to the Evidence Plane — it only reads from it
and writes to the Theory Plane (Hypothesis nodes, probability history in
Investigation Memory). Every output carries a confidence score, an evidence
basis, and a plain-language explanation.
"""

import uuid
import math
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType
from app.reasoning.hpl.grammar import (
    parse_hpl, extract_evidence_lists, check_implied_evidence_status,
    validate_hpl_entities,
)

logger = logging.getLogger(__name__)


def compute_prior(case_id: str) -> dict:
    """
    Compute hypothesis prior from CrimeCategory prior_distribution.
    Returns {scenario_key: probability} or uniform distribution.
    """
    client = get_neo4j_client()

    # Get case's crime category
    category_result = client.execute_read(
        """
        MATCH (c:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.prior_distribution AS priors, cat.name AS name
        """,
        {"cid": case_id},
    )

    if category_result and category_result[0].get("priors"):
        import json
        priors_str = str(category_result[0]["priors"])
        try:
            return json.loads(priors_str.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            pass

    return {}  # Empty means use uniform 1/N


def spawn_hypothesis(
    case_id: str,
    narrative: str,
    predicates: list[str],
    scenario_type: Optional[str] = None,
    db: Optional[Session] = None,
) -> dict:
    """
    SPAWN(hypothesis) — the formal TOS operation.

    1. Creates Hypothesis node with HPL predicates
    2. Assigns initial probability from prior
    3. Generates implied/forbidden evidence
    4. Checks for absent implied evidence → creates EvidenceGaps
    5. Checks for present forbidden evidence → creates Contradictions
    6. Writes memory records
    """
    client = get_neo4j_client()
    hyp_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Parse predicates
    implied_ev, forbidden_ev = extract_evidence_lists(predicates)

    # Compute prior probability
    has_stronger_prior = False
    cross_case_prior = {}
    try:
        from app.cross_case.integration import get_cross_case_prior
        cross_case_prior = get_cross_case_prior(case_id)
        if cross_case_prior.get("use_historical_prior"):
            has_stronger_prior = True
    except Exception as e:
        logger.warning("Failed to get cross-case prior: %s", e)

    if has_stronger_prior:
        initial_prob = 0.7
        if db:
            reasoning_text = (
                f"Elevated prior probability to 0.7 based on cross-case historical patterns: "
                f"{cross_case_prior.get('reason')}. Aligned conviction/outcome confidence: "
                f"{cross_case_prior.get('confidence', 0.0) * 100:.1f}%."
            )
            write_memory_record(
                db=db, case_id=case_id,
                record_type=MemoryRecordType.theory_revised,
                description=f"Prior probability for hypothesis elevated due to cross-case pattern match.",
                actor="system:competing_theories",
                reasoning=reasoning_text,
            )
    else:
        priors = compute_prior(case_id)
        if priors and scenario_type and scenario_type in priors:
            initial_prob = priors[scenario_type]
        else:
            # Uniform over all active hypotheses + this new one
            active = client.execute_read(
                "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) RETURN count(h) AS cnt",
                {"cid": case_id},
            )
            n = (active[0]["cnt"] if active else 0) + 1
            initial_prob = 1.0 / n

    # Re-normalize existing hypotheses
    _renormalize_with_new(client, case_id, initial_prob)

    # Create Hypothesis node
    import json
    client.execute_write(
        """
        CREATE (h:Hypothesis {
            id: $hid, case_id: $cid,
            narrative: $narrative, status: 'active',
            probability: $prob,
            predicates: $preds,
            implied_evidence: $implied,
            forbidden_evidence: $forbidden,
            classification_tag: 'case_sensitive',
            created_at: $now
        })
        """,
        {
            "hid": hyp_id, "cid": case_id,
            "narrative": narrative, "prob": initial_prob,
            "preds": json.dumps(predicates),
            "implied": json.dumps(implied_ev),
            "forbidden": json.dumps(forbidden_ev),
            "now": now,
        },
    )

    # Check implied_evidence_status
    statuses = check_implied_evidence_status(case_id, implied_ev)
    gaps_created = []
    for item in statuses:
        if item["status"] == "absent":
            gap_id = str(uuid.uuid4())
            client.execute_write(
                """
                CREATE (g:EvidenceGap {
                    id: $gid, case_id: $cid,
                    gap_type: $gtype, description: $desc,
                    urgency: 'medium', status: 'open',
                    classification_tag: 'case_sensitive', created_at: $now
                })
                """,
                {
                    "gid": gap_id, "cid": case_id,
                    "gtype": item["evidence_type"],
                    "desc": f"Implied by hypothesis: {narrative[:50]} — "
                            f"{item['evidence_type']}({item['params']})",
                    "now": now,
                },
            )
            # Link gap to hypothesis
            client.execute_write(
                """
                MATCH (h:Hypothesis {id: $hid}), (g:EvidenceGap {id: $gid})
                CREATE (g)-[:RELATES_TO]->(h)
                """,
                {"hid": hyp_id, "gid": gap_id},
            )
            gaps_created.append(gap_id)

    # Check forbidden evidence against existing graph
    contradictions_created = []
    for item in forbidden_ev:
        found = check_implied_evidence_status(case_id, [item])
        if found and found[0]["status"] == "found":
            contra_id = str(uuid.uuid4())
            client.execute_write(
                """
                CREATE (c:Contradiction {
                    id: $cid_c, case_id: $cid,
                    contradiction_type: 'logical',
                    description: $desc,
                    severity: 'high', status: 'open',
                    classification_tag: 'case_sensitive', created_at: $now
                })
                """,
                {
                    "cid_c": contra_id, "cid": case_id,
                    "desc": f"Forbidden evidence {item['evidence_type']} found at "
                            f"hypothesis creation for: {narrative[:50]}",
                    "now": now,
                },
            )
            client.execute_write(
                "MATCH (h:Hypothesis {id: $hid}), (c:Contradiction {id: $cid_c}) "
                "CREATE (c)-[:INVOLVES]->(h)",
                {"hid": hyp_id, "cid_c": contra_id},
            )
            contradictions_created.append(contra_id)
            # Reduce probability
            initial_prob *= 0.5
            client.execute_write(
                "MATCH (h:Hypothesis {id: $hid}) SET h.probability = $p",
                {"hid": hyp_id, "p": initial_prob},
            )

    # Write memory records
    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.hypothesis_created,
            description=f"Hypothesis spawned: {narrative[:100]}",
            actor="system:theory_engine",
            graph_refs=[hyp_id],
            beliefs_after={hyp_id: initial_prob},
        )
        db.commit()

    return {
        "hypothesis_id": hyp_id,
        "narrative": narrative,
        "probability": initial_prob,
        "predicates_count": len(predicates),
        "implied_evidence_count": len(implied_ev),
        "forbidden_evidence_count": len(forbidden_ev),
        "gaps_created": gaps_created,
        "contradictions_created": contradictions_created,
    }


def eliminate_hypothesis(
    case_id: str,
    hypothesis_id: str,
    evidence_id: str,
    reasoning: str,
    db: Optional[Session] = None,
) -> dict:
    """
    ELIMINATE(hypothesis) — the formal TOS operation.

    Sets status=eliminated, redistributes probability mass proportionally.
    """
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get current state
    current = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid, case_id: $cid}) "
        "RETURN h.probability AS prob, h.narrative AS narrative",
        {"hid": hypothesis_id, "cid": case_id},
    )
    if not current:
        return {"error": "Hypothesis not found"}

    eliminated_prob = current[0]["prob"]
    beliefs_before = _get_all_probabilities(client, case_id)

    # Eliminate
    client.execute_write(
        """
        MATCH (h:Hypothesis {id: $hid})
        SET h.status = 'eliminated',
            h.decisive_evidence_id = $eid,
            h.decisive_evidence_reasoning = $reason,
            h.eliminated_at = $now
        """,
        {"hid": hypothesis_id, "eid": evidence_id, "reason": reasoning, "now": now},
    )

    # Redistribute probability mass proportionally
    remaining = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) "
        "RETURN h.id AS id, h.probability AS prob",
        {"cid": case_id},
    )

    if remaining:
        total_remaining = sum(r["prob"] for r in remaining)
        for r in remaining:
            new_prob = r["prob"] / total_remaining if total_remaining > 0 else 1.0 / len(remaining)
            client.execute_write(
                "MATCH (h:Hypothesis {id: $hid}) SET h.probability = $p",
                {"hid": r["id"], "p": new_prob},
            )

    beliefs_after = _get_all_probabilities(client, case_id)

    # Resolve exclusive EvidenceGaps
    client.execute_write(
        """
        MATCH (g:EvidenceGap)-[:RELATES_TO]->(h:Hypothesis {id: $hid})
        WHERE NOT EXISTS {
            MATCH (g)-[:RELATES_TO]->(other:Hypothesis {status: 'active'})
            WHERE other.id <> $hid
        }
        SET g.status = 'resolved', g.resolution_note = 'parent hypothesis eliminated'
        """,
        {"hid": hypothesis_id},
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.hypothesis_eliminated,
            description=f"Hypothesis eliminated: {current[0]['narrative'][:80]}",
            actor="system:theory_engine",
            graph_refs=[hypothesis_id, evidence_id],
            beliefs_before=beliefs_before,
            beliefs_after=beliefs_after,
            reasoning=reasoning,
        )
        db.commit()

    return {
        "status": "eliminated",
        "hypothesis_id": hypothesis_id,
        "redistributed_mass": eliminated_prob,
        "beliefs_after": beliefs_after,
    }


def explain_hypothesis(case_id: str, hypothesis_id: str) -> dict:
    """
    EXPLAIN(hypothesis) — structured explanation of current state.
    """
    client = get_neo4j_client()

    hyp = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid, case_id: $cid}) "
        "RETURN h.narrative AS narrative, h.probability AS prob, h.status AS status",
        {"hid": hypothesis_id, "cid": case_id},
    )
    if not hyp:
        return {"error": "Hypothesis not found"}

    narrative = hyp[0]["narrative"]
    prob = hyp[0]["prob"]

    # Top supporting evidence
    supporting = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})<-[:SUPPORTED_BY]-(n)
        RETURN n.id AS id, labels(n)[0] AS label,
               coalesce(n.display_name, n.event_type, n.id) AS display
        LIMIT 3
        """,
        {"hid": hypothesis_id},
    )

    # Top contradicting
    contradicting = client.execute_read(
        """
        MATCH (c:Contradiction)-[:INVOLVES]->(h:Hypothesis {id: $hid})
        RETURN c.id AS id, c.description AS description, c.severity AS severity
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END
        LIMIT 3
        """,
        {"hid": hypothesis_id},
    )

    # Key unverified assumptions
    assumptions = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:REQUIRES_ASSUMPTION]->(a:Assumption)
        WHERE a.verification_status = 'unverified' AND a.criticality = 'high'
        RETURN a.id AS id, a.statement AS statement, a.criticality AS criticality
        """,
        {"hid": hypothesis_id},
    )

    # Build narrative
    support_text = ", ".join(s["display"] for s in supporting) or "no direct supporting evidence yet"
    contra_text = contradicting[0]["description"] if contradicting else "no active contradictions"
    assumption_text = (assumptions[0]["statement"] if assumptions
                       else "no unverified high-criticality assumptions")

    auto_narrative = (
        f"Hypothesis '{narrative}' currently has probability {prob:.2f}. "
        f"Its strongest support comes from {support_text}. "
        f"Its main challenge is: {contra_text}. "
        f"Its most critical unverified assumption: {assumption_text}."
    )

    return {
        "hypothesis_id": hypothesis_id,
        "probability": prob,
        "status": hyp[0]["status"],
        "top_supporting": supporting,
        "top_contradicting": contradicting,
        "key_assumptions": assumptions,
        "narrative": auto_narrative,
    }


def _get_all_probabilities(client, case_id: str) -> dict:
    """Get probability map for all active hypotheses."""
    result = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) "
        "RETURN h.id AS id, h.probability AS prob",
        {"cid": case_id},
    )
    return {r["id"]: r["prob"] for r in result}


def _renormalize_with_new(client, case_id: str, new_prob: float):
    """Renormalize existing active hypotheses to make room for new_prob."""
    existing = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) "
        "RETURN h.id AS id, h.probability AS prob",
        {"cid": case_id},
    )
    if not existing:
        return

    # Scale down existing to sum to (1 - new_prob)
    total = sum(h["prob"] for h in existing)
    scale = (1.0 - new_prob) / total if total > 0 else 0

    for h in existing:
        client.execute_write(
            "MATCH (h:Hypothesis {id: $hid}) SET h.probability = $p",
            {"hid": h["id"], "p": h["prob"] * scale},
        )
