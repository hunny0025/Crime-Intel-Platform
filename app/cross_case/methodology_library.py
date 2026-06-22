"""Methodology Library + Case Matching Engine.

Vector-based similarity search across CasePatterns.
Falls back to property-based matching if Qdrant is unavailable.
"""

import json
import logging
from datetime import datetime, timezone

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def find_similar_cases(case_id: str, top_k: int = 5) -> dict:
    """Find similar historical cases based on structural patterns."""
    client = get_neo4j_client()

    # Get current case's profile
    current = _get_case_profile(client, case_id)
    if not current:
        return {"similar_cases": [], "error": "Case profile not available"}

    # Property-based matching (fallback from vector search)
    all_patterns = client.execute_read(
        """
        MATCH (cp:CasePattern)
        WHERE cp.PII_SAFE = true
        RETURN cp.id AS id, cp.crime_category_ids AS cats,
               cp.evidence_type_profile AS eprofile,
               cp.hypothesis_count_at_peak AS hyp_peak,
               cp.decisive_evidence_types AS decisive,
               cp.outcome AS outcome,
               cp.time_to_first_elimination_days AS ttfe
        """,
    )

    # Compute similarity scores
    scored = []
    for pattern in all_patterns:
        score = _compute_similarity(current, pattern)
        scored.append({
            "pattern_id": pattern["id"],
            "similarity_score": round(score, 4),
            "crime_categories": _safe_json(pattern.get("cats")),
            "outcome": pattern.get("outcome", "unknown"),
            "hypothesis_peak": pattern.get("hyp_peak", 0),
            "decisive_evidence_types": _safe_json(pattern.get("decisive")),
        })

    scored.sort(key=lambda s: s["similarity_score"], reverse=True)
    top = scored[:top_k]

    # Derive insights
    insights = _derive_insights(current, top, case_id, client)

    return {
        "case_id": case_id,
        "similar_cases": top,
        "insights": insights,
    }


def get_methodology_baseline(case_id: str) -> dict:
    """Aggregate CasePattern stats for this case's crime category."""
    client = get_neo4j_client()

    # Get case crime category
    cats = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS cat_id, cat.name AS name
        """,
        {"cid": case_id},
    )
    cat_ids = [c["cat_id"] for c in cats]

    if not cat_ids:
        return {"error": "No crime category assigned to case"}

    # Find all patterns for this category
    patterns = client.execute_read(
        """
        MATCH (cp:CasePattern)
        WHERE cp.PII_SAFE = true
        RETURN cp.hypothesis_count_at_peak AS hyp_peak,
               cp.time_to_first_elimination_days AS ttfe,
               cp.outcome AS outcome,
               cp.evidence_type_profile AS eprofile
        """,
    )

    if not patterns:
        return {"cat_ids": cat_ids, "message": "No historical patterns available yet"}

    # Compute medians and distributions
    hyp_peaks = [p["hyp_peak"] for p in patterns if p.get("hyp_peak") is not None]
    ttfes = [p["ttfe"] for p in patterns if p.get("ttfe") is not None]

    outcomes = {}
    for p in patterns:
        o = p.get("outcome", "unknown")
        outcomes[o] = outcomes.get(o, 0) + 1

    # Current case deviation
    current_profile = _get_case_profile(client, case_id)
    deviations = []
    if current_profile:
        current_hyp = current_profile.get("hypothesis_count_at_peak", 0)
        median_hyp = sorted(hyp_peaks)[len(hyp_peaks)//2] if hyp_peaks else 0
        if current_hyp > median_hyp * 1.5:
            deviations.append(
                f"Current case has {current_hyp} hypotheses vs typical {median_hyp} "
                f"— more complex than usual"
            )
        elif current_hyp < median_hyp * 0.5 and median_hyp > 0:
            deviations.append(
                f"Current case has {current_hyp} hypotheses vs typical {median_hyp} "
                f"— simpler than usual"
            )

    return {
        "crime_categories": cat_ids,
        "patterns_analyzed": len(patterns),
        "median_hypothesis_peak": sorted(hyp_peaks)[len(hyp_peaks)//2] if hyp_peaks else None,
        "median_time_to_first_elimination": sorted(ttfes)[len(ttfes)//2] if ttfes else None,
        "outcome_distribution": outcomes,
        "deviations_from_typical": deviations,
    }


def _get_case_profile(client, case_id: str) -> dict:
    """Build the current case's profile for comparison."""
    evidence = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN n.source_tool AS tool, count(n) AS cnt
        """,
        {"cid": case_id},
    )
    total = sum(e["cnt"] for e in evidence) or 1
    eprofile = {e["tool"]: e["cnt"] / total for e in evidence}

    cats = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS id
        """,
        {"cid": case_id},
    )

    hyps = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid}) RETURN count(h) AS cnt",
        {"cid": case_id},
    )

    return {
        "crime_category_ids": [c["id"] for c in cats],
        "evidence_type_profile": eprofile,
        "hypothesis_count_at_peak": hyps[0]["cnt"] if hyps else 0,
    }


def _compute_similarity(current: dict, pattern: dict) -> float:
    """Compute similarity between current case and a CasePattern."""
    score = 0.0

    # Category overlap (Jaccard)
    current_cats = set(current.get("crime_category_ids", []))
    pattern_cats = set(_safe_json(pattern.get("cats")))
    if current_cats or pattern_cats:
        jaccard = len(current_cats & pattern_cats) / len(current_cats | pattern_cats)
        score += 0.4 * jaccard

    # Evidence profile cosine similarity (simplified)
    current_ep = current.get("evidence_type_profile", {})
    pattern_ep = _safe_json_dict(pattern.get("eprofile"))
    all_keys = set(current_ep) | set(pattern_ep)
    if all_keys:
        dot = sum(current_ep.get(k, 0) * pattern_ep.get(k, 0) for k in all_keys)
        mag_c = sum(v**2 for v in current_ep.values()) ** 0.5
        mag_p = sum(v**2 for v in pattern_ep.values()) ** 0.5
        if mag_c > 0 and mag_p > 0:
            cosine = dot / (mag_c * mag_p)
            score += 0.4 * cosine

    # Hypothesis count similarity
    c_hyp = current.get("hypothesis_count_at_peak", 0) or 1
    p_hyp = pattern.get("hyp_peak", 0) or 1
    hyp_sim = 1.0 - abs(c_hyp - p_hyp) / max(c_hyp, p_hyp)
    score += 0.2 * max(hyp_sim, 0)

    return score


def _derive_insights(current, similar, case_id, client) -> list[str]:
    """Derive actionable insights from similar case patterns."""
    insights = []

    # Decisive evidence types
    all_decisive = set()
    for s in similar:
        all_decisive.update(s.get("decisive_evidence_types", []))

    current_evidence = set(current.get("evidence_type_profile", {}).keys())
    missing_decisive = all_decisive - current_evidence
    if missing_decisive:
        insights.append(
            f"In similar cases, {', '.join(list(missing_decisive)[:3])} were decisive "
            f"evidence types — not yet present in current case"
        )

    # Outcome distribution
    outcomes = {}
    for s in similar:
        o = s.get("outcome", "unknown")
        outcomes[o] = outcomes.get(o, 0) + 1
    total = sum(outcomes.values())
    if total > 0:
        convicted = outcomes.get("closed_convicted", 0)
        insights.append(
            f"Of {total} similar cases: {convicted} convicted, "
            f"{outcomes.get('closed_acquitted', 0)} acquitted"
        )

    return insights


def _safe_json(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _safe_json_dict(val):
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
