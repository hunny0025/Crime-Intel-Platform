"""Attention Engine — computes attention_value scores for graph entities.

Scoring formula (simplified — full Bayesian information-gain depends on
Phase 5 hypothesis probabilities):
    +0.4 if involved in any Contradiction (via INVOLVES)
    +0.3 if related to any open EvidenceGap (via RELATES_TO)
    +0.25 if involved in any BehavioralAnomaly (via HAS_ANOMALY/INVOLVES)
    +0.2 if predicted by any active Hypothesis (via PREDICTED_BY)
    +0.1 if created within the last 24h of case time (recency)
    +0.3 if assessed with high deception_score (>0.7)
    Capped at 1.0
"""

import logging
from datetime import datetime, timedelta, timezone

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

# Score weights
W_CONTRADICTION = 0.4
W_EVIDENCE_GAP = 0.3
W_BEHAVIORAL_ANOMALY = 0.25
W_HYPOTHESIS = 0.2
W_RECENCY = 0.1
W_DECEPTION = 0.3
DECEPTION_THRESHOLD = 0.7


def compute_attention_value(case_id: str, node_id: str) -> dict:
    """
    Compute attention_value for a single node.

    Returns dict with:
        - attention_value (float, 0-1)
        - breakdown (dict with individual factor values)
    """
    client = get_neo4j_client()
    breakdown = {
        "contradiction_factor": 0.0,
        "evidence_gap_factor": 0.0,
        "behavioral_anomaly_factor": 0.0,
        "hypothesis_factor": 0.0,
        "recency_factor": 0.0,
        "deception_factor": 0.0,
    }

    # Check if involved in any Contradiction
    contra_result = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $case_id})-[:INVOLVES]->(n {id: $node_id})
        RETURN count(c) AS count
        """,
        {"case_id": case_id, "node_id": node_id},
    )
    if contra_result and contra_result[0]["count"] > 0:
        breakdown["contradiction_factor"] = W_CONTRADICTION

    # Check if related to any open EvidenceGap
    gap_result = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $case_id, status: 'open'})-[:RELATES_TO]->(n {id: $node_id})
        RETURN count(g) AS count
        """,
        {"case_id": case_id, "node_id": node_id},
    )
    if gap_result and gap_result[0]["count"] > 0:
        breakdown["evidence_gap_factor"] = W_EVIDENCE_GAP

    # Check if predicted by any active Hypothesis
    hyp_result = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $case_id, status: 'active'})-[:PREDICTED_BY]->(n {id: $node_id})
        RETURN count(h) AS count
        """,
        {"case_id": case_id, "node_id": node_id},
    )
    if hyp_result and hyp_result[0]["count"] > 0:
        breakdown["hypothesis_factor"] = W_HYPOTHESIS

    # Check if involved in any BehavioralAnomaly
    anomaly_result = client.execute_read(
        """
        MATCH (n {id: $node_id})-[:HAS_ANOMALY|INVOLVES]-(a:BehavioralAnomaly {case_id: $case_id})
        RETURN count(a) AS count
        """,
        {"case_id": case_id, "node_id": node_id},
    )
    if anomaly_result and anomaly_result[0]["count"] > 0:
        breakdown["behavioral_anomaly_factor"] = W_BEHAVIORAL_ANOMALY

    # Check for high deception_score assessment
    deception_result = client.execute_read(
        """
        MATCH (d:DeceptionAssessment {case_id: $case_id})
        WHERE d.target_id = $node_id AND d.deception_score > $threshold
        RETURN count(d) AS count
        """,
        {"case_id": case_id, "node_id": node_id, "threshold": DECEPTION_THRESHOLD},
    )
    if deception_result and deception_result[0]["count"] > 0:
        breakdown["deception_factor"] = W_DECEPTION

    # Recency: created within last 24h of case time
    # Use the most recent event timestamp as "case now"
    recent_result = client.execute_read(
        """
        MATCH (e:Event {case_id: $case_id})
        WHERE e.valid_from IS NOT NULL
        RETURN max(e.valid_from) AS latest
        """,
        {"case_id": case_id},
    )
    if recent_result and recent_result[0]["latest"]:
        try:
            case_now_str = str(recent_result[0]["latest"])
            case_now = datetime.fromisoformat(case_now_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            case_now = datetime.now(timezone.utc)

        node_result = client.execute_read(
            "MATCH (n {id: $node_id}) RETURN n.created_at AS created_at",
            {"node_id": node_id},
        )
        if node_result and node_result[0]["created_at"]:
            try:
                created_str = str(node_result[0]["created_at"])
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if (case_now - created).total_seconds() < 86400:
                    breakdown["recency_factor"] = W_RECENCY
            except (ValueError, TypeError):
                pass

    score = min(1.0, sum(breakdown.values()))

    # Store on the node
    client.execute_write(
        """
        MATCH (n {id: $node_id})
        SET n.attention_value = $score,
            n.attention_updated_at = $now
        """,
        {
            "node_id": node_id,
            "score": score,
            "now": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "node_id": node_id,
        "attention_value": score,
        "breakdown": breakdown,
    }


def recompute_case_attention(case_id: str) -> list[dict]:
    """Recompute attention_value for all scored node types in a case."""
    client = get_neo4j_client()
    scored_labels = ["Person", "Event", "Location", "Account", "Device", "Organization"]
    all_scores = []

    for label in scored_labels:
        nodes = client.execute_read(
            f"MATCH (n:{label} {{case_id: $case_id}}) RETURN n.id AS id",
            {"case_id": case_id},
        )
        for node in nodes:
            score = compute_attention_value(case_id, node["id"])
            if score["attention_value"] > 0:
                all_scores.append(score)

    all_scores.sort(key=lambda s: s["attention_value"], reverse=True)
    return all_scores


def get_attention_heatmap(case_id: str) -> list[dict]:
    """Return all scored nodes sorted by attention_value descending."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $case_id AND n.attention_value IS NOT NULL AND n.attention_value > 0
        RETURN n.id AS node_id,
               labels(n)[0] AS label,
               coalesce(n.display_name, n.address, n.event_type, n.id) AS display,
               n.attention_value AS attention_value,
               n.attention_updated_at AS updated_at
        ORDER BY n.attention_value DESC
        """,
        {"case_id": case_id},
    )

    # Recompute breakdown for each
    heatmap = []
    for row in result:
        score = compute_attention_value(case_id, row["node_id"])
        score["label"] = row["label"]
        score["display"] = row["display"]
        heatmap.append(score)

    heatmap.sort(key=lambda s: s["attention_value"], reverse=True)
    return heatmap


def get_attention_changes(case_id: str, since: str) -> list[dict]:
    """Return nodes whose attention_value changed since the given timestamp."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $case_id
          AND n.attention_value IS NOT NULL
          AND n.attention_value > 0
          AND n.attention_updated_at >= $since
        RETURN n.id AS node_id,
               labels(n)[0] AS label,
               coalesce(n.display_name, n.address, n.event_type, n.id) AS display,
               n.attention_value AS attention_value,
               n.attention_updated_at AS updated_at
        ORDER BY n.attention_value DESC
        """,
        {"case_id": case_id, "since": since},
    )

    changes = []
    for row in result:
        score = compute_attention_value(case_id, row["node_id"])
        score["label"] = row["label"]
        score["display"] = row["display"]
        changes.append(score)

    return changes
