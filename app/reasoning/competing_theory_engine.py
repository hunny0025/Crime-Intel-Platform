"""Competing Theory Engine — Bayesian update pipeline for hypothesis probabilities.

For each evidence event, computes P(H|evidence) for all active hypotheses
simultaneously, normalizes, and stores updated probabilities with full audit
trail in Investigation Memory.
"""

import math
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Likelihood weights for evidence-hypothesis relationships
LIKELIHOOD_IMPLIES_MATCH = 1.2     # Predicted evidence found
LIKELIHOOD_FORBIDS_MATCH = 0.3     # Forbidden evidence found (strong downward)
LIKELIHOOD_CONTRADICTION = 0.5     # Indirect negative from contradiction
LIKELIHOOD_NEUTRAL = 1.0           # No relationship to hypothesis


def bayesian_update(
    case_id: str,
    evidence_node_id: str,
    evidence_type: str,
    db: Optional[Session] = None,
) -> list[dict]:
    """
    Core Bayesian update: propagate new evidence through all active hypotheses.

    Returns list of {hypothesis_id, prior, likelihood, posterior, bucket}.
    """
    client = get_neo4j_client()

    # Get all active hypotheses
    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.probability AS prob, h.narrative AS narrative,
               h.implied_evidence AS implied, h.forbidden_evidence AS forbidden
        """,
        {"cid": case_id},
    )

    if not hypotheses:
        return []

    beliefs_before = {h["id"]: h["prob"] for h in hypotheses}
    updates = []

    # Fetch composite_reliability_score for the evidence_node_id
    reliability_score = 0.7
    if db:
        try:
            res = client.execute_read(
                "MATCH (n {id: $nid}) RETURN n.artifact_id AS artifact_id",
                {"nid": evidence_node_id}
            )
            artifact_id = None
            if res and res[0].get("artifact_id"):
                artifact_id = res[0]["artifact_id"]
            else:
                artifact_id = evidence_node_id

            if artifact_id:
                import uuid as pyuuid
                from app.db.models import EvidenceArtifact
                artifact = db.query(EvidenceArtifact).filter(
                    EvidenceArtifact.artifact_id == pyuuid.UUID(str(artifact_id))
                ).first()
                if artifact and artifact.composite_reliability_score is not None:
                    reliability_score = artifact.composite_reliability_score
        except Exception as e:
            logger.error(f"Error fetching composite_reliability_score in bayesian_update: {e}")

    for h in hypotheses:
        implied = _safe_json(h.get("implied", "[]"))
        forbidden = _safe_json(h.get("forbidden", "[]"))

        # Determine likelihood bucket
        likelihood = LIKELIHOOD_NEUTRAL
        bucket = "neutral"

        # Check IMPLIES match
        for item in implied:
            if _evidence_matches(evidence_type, evidence_node_id, item, client, case_id):
                likelihood = LIKELIHOOD_IMPLIES_MATCH
                bucket = "implies_match"
                break

        # Check FORBIDS match (overrides neutral, but IMPLIES takes priority)
        if bucket == "neutral":
            for item in forbidden:
                if _evidence_matches(evidence_type, evidence_node_id, item, client, case_id):
                    likelihood = LIKELIHOOD_FORBIDS_MATCH
                    bucket = "forbids_match"
                    break

        # Check contradiction involvement
        if bucket == "neutral":
            contra_check = client.execute_read(
                """
                MATCH (c:Contradiction)-[:INVOLVES]->(h:Hypothesis {id: $hid})
                MATCH (c)-[:INVOLVES]->(n {id: $nid})
                RETURN count(c) AS cnt
                """,
                {"hid": h["id"], "nid": evidence_node_id},
            )
            if contra_check and contra_check[0]["cnt"] > 0:
                likelihood = LIKELIHOOD_CONTRADICTION
                bucket = "contradiction_indirect"

        # Multiply evidence likelihood weight by composite_reliability_score
        likelihood = likelihood * reliability_score

        updates.append({
            "hypothesis_id": h["id"],
            "prior": h["prob"],
            "likelihood": likelihood,
            "unnormalized": h["prob"] * likelihood,
            "bucket": bucket,
            "narrative": h.get("narrative", ""),
        })

    # Normalize
    total = sum(u["unnormalized"] for u in updates)
    if total > 0:
        for u in updates:
            u["posterior"] = u["unnormalized"] / total
    else:
        n = len(updates)
        for u in updates:
            u["posterior"] = 1.0 / n

    # Store updated probabilities
    for u in updates:
        client.execute_write(
            "MATCH (h:Hypothesis {id: $hid}) SET h.probability = $p",
            {"hid": u["hypothesis_id"], "p": u["posterior"]},
        )

    beliefs_after = {u["hypothesis_id"]: u["posterior"] for u in updates}

    # Write memory record
    if db:
        reasoning = (
            f"Bayesian update from evidence {evidence_node_id} ({evidence_type}). "
            f"Likelihood buckets: " +
            ", ".join(f"{u['narrative'][:30]}={u['bucket']}" for u in updates)
        )
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.probability_updated,
            description=f"Probability update from new evidence: {evidence_type}",
            actor="system:competing_theory_engine",
            graph_refs=[evidence_node_id],
            beliefs_before=beliefs_before,
            beliefs_after=beliefs_after,
            reasoning=reasoning,
        )
        db.commit()

    return updates


def compute_sensitivity(case_id: str, hypothesis_id: str) -> list[dict]:
    """
    SENSITIVITY(hypothesis) — compute the top 5 most weight-bearing evidence items.

    For each supporting evidence, compute the counterfactual: what would the
    probability be if this evidence's contribution were set to neutral (1.0)?
    """
    client = get_neo4j_client()

    # Get all evidence supporting this hypothesis
    supporting = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid, case_id: $cid})<-[:SUPPORTED_BY]-(n)
        RETURN n.id AS id, labels(n)[0] AS label,
               coalesce(n.display_name, n.event_type, n.id) AS display
        """,
        {"hid": hypothesis_id, "cid": case_id},
    )

    hyp = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid}) RETURN h.probability AS prob",
        {"hid": hypothesis_id},
    )
    if not hyp:
        return []

    current_prob = hyp[0]["prob"]
    sensitivities = []

    for ev in supporting:
        # Counterfactual: set this evidence to neutral and renormalize
        # Approximate by reducing the boost this evidence provided
        counterfactual_prob = current_prob * (LIKELIHOOD_NEUTRAL / LIKELIHOOD_IMPLIES_MATCH)
        delta = abs(current_prob - counterfactual_prob)

        sensitivities.append({
            "evidence_id": ev["id"],
            "evidence_label": ev["label"],
            "evidence_display": ev["display"],
            "current_contribution": "implies_match",
            "sensitivity_delta": round(delta, 4),
            "counterfactual_probability": round(counterfactual_prob, 4),
        })

    sensitivities.sort(key=lambda s: s["sensitivity_delta"], reverse=True)
    return sensitivities[:5]


def challenge_hypothesis(case_id: str, hypothesis_id: str) -> dict:
    """
    CHALLENGE(hypothesis) — find the most vulnerable assumption and compute
    the counterfactual probability if that assumption were false.
    """
    client = get_neo4j_client()

    hyp = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid}) "
        "RETURN h.probability AS prob, h.narrative AS narrative",
        {"hid": hypothesis_id},
    )
    if not hyp:
        return {"error": "Hypothesis not found"}

    current_prob = hyp[0]["prob"]
    narrative = hyp[0]["narrative"]

    # Find highest-criticality unverified assumption
    assumptions = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:REQUIRES_ASSUMPTION]->(a:Assumption)
        WHERE a.verification_status = 'unverified'
        RETURN a.id AS id, a.statement AS statement, a.criticality AS criticality
        ORDER BY CASE criticality WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT 1
        """,
        {"hid": hypothesis_id},
    )

    if not assumptions:
        return {
            "hypothesis_id": hypothesis_id,
            "message": "No unverified assumptions found — hypothesis is well-grounded",
            "current_probability": current_prob,
        }

    assumption = assumptions[0]

    # Counterfactual: if assumption were false, treat as FORBIDS match
    counterfactual_prob = current_prob * LIKELIHOOD_FORBIDS_MATCH
    # Simple renormalization estimate
    remaining_mass = 1.0 - current_prob + counterfactual_prob
    if remaining_mass > 0:
        counterfactual_prob = counterfactual_prob / remaining_mass

    # Find verification path
    gaps = client.execute_read(
        """
        MATCH (g:EvidenceGap)-[:RELATES_TO]->(a:Assumption {id: $aid})
        RETURN g.description AS gap_desc
        """,
        {"aid": assumption["id"]},
    )
    verification = (gaps[0]["gap_desc"] if gaps
                    else "No specific evidence gap identified — manual verification needed")

    output = (
        f"The most vulnerable point of Hypothesis '{narrative}' is the assumption "
        f"that {assumption['statement']}. If this assumption is false, probability "
        f"would drop from {current_prob:.2f} to {counterfactual_prob:.2f}. "
        f"This assumption can be verified by: {verification}."
    )

    return {
        "hypothesis_id": hypothesis_id,
        "current_probability": current_prob,
        "counterfactual_probability": round(counterfactual_prob, 4),
        "vulnerable_assumption": assumption,
        "verification_path": verification,
        "narrative": output,
    }


def get_ranked_hypotheses(case_id: str) -> list[dict]:
    """Return all active hypotheses sorted by probability descending."""
    client = get_neo4j_client()
    from app.reasoning.theory_engine import explain_hypothesis

    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.probability AS prob, h.narrative AS narrative
        ORDER BY h.probability DESC
        """,
        {"cid": case_id},
    )

    ranked = []
    for h in hypotheses:
        expl = explain_hypothesis(case_id, h["id"])
        ranked.append({
            "hypothesis_id": h["id"],
            "probability": h["prob"],
            "narrative": h["narrative"],
            "summary": expl.get("narrative", ""),
        })

    return ranked


# ── Helpers ──────────────────────────────────────────────────────────────

def _safe_json(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _evidence_matches(evidence_type: str, evidence_id: str,
                      item: dict, client, case_id: str) -> bool:
    """Check if an evidence node matches an implied/forbidden evidence item."""
    item_type = item.get("evidence_type", "")

    # Simple type matching — refined checkers in HPL grammar handle the details
    type_map = {
        "CellTowerPing": ["cell_tower", "cell_tower_ping"],
        "GPSRecord": ["gps", "gps_record"],
        "CCTVFrame": ["cctv", "video", "cctv_frame"],
        "CommunicationRecord": ["communication", "call", "sms", "message"],
    }

    expected_types = type_map.get(item_type, [item_type.lower()])
    return evidence_type.lower() in expected_types
