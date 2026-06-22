"""Causal Reasoning Layer — causal chains and counterfactual simulation.

Reasons about what *caused* what, not just what happened when.
The CAUSED relationship is distinct from temporal ordering.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType
from app.graph import GRAPH_MAX_TRAVERSAL_DEPTH

logger = logging.getLogger(__name__)


def create_causal_link(
    case_id: str,
    cause_event_id: str,
    effect_event_id: str,
    mechanism: str,
    confidence: float,
    evidence_basis: list[str] = None,
) -> dict:
    """Create a CAUSED relationship between two Event nodes."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (cause:Event {id: $cause_id, case_id: $cid}),
              (effect:Event {id: $effect_id, case_id: $cid})
        CREATE (cause)-[r:CAUSED {
            confidence: $conf,
            mechanism: $mechanism,
            evidence_basis: $eb,
            created_at: $now
        }]->(effect)
        """,
        {
            "cause_id": cause_event_id, "effect_id": effect_event_id,
            "cid": case_id, "conf": confidence,
            "mechanism": mechanism,
            "eb": evidence_basis or [],
            "now": now,
        },
    )

    return {
        "cause": cause_event_id,
        "effect": effect_event_id,
        "mechanism": mechanism,
        "confidence": confidence,
    }


def build_causal_chain(case_id: str, focal_event_id: str) -> dict:
    """
    Traverse backward through CAUSED relationships to construct the full
    causal chain leading to the focal event.

    Returns ordered list with confidence (chain confidence = product of steps).
    """
    client = get_neo4j_client()

    # Find all causal paths to the focal event (max depth 10)
    paths = client.execute_read(
        f"""
        MATCH path = (root:Event)-[:CAUSED*1..{GRAPH_MAX_TRAVERSAL_DEPTH}]->(focal:Event {id: $fid, case_id: $cid})
        WHERE NOT EXISTS {{ MATCH (:Event)-[:CAUSED]->(root) }}
        RETURN [n IN nodes(path) | {{
            id: n.id,
            event_type: n.event_type,
            valid_from: n.valid_from,
            display: coalesce(n.display_name, n.event_type, n.id)
        }}] AS chain,
        [r IN relationships(path) | {{
            confidence: r.confidence,
            mechanism: r.mechanism
        }}] AS links,
        reduce(acc = 1.0, r IN relationships(path) | acc * r.confidence) AS chain_confidence
        ORDER BY chain_confidence DESC
        """,
        {"fid": focal_event_id, "cid": case_id},
    )

    if not paths:
        # Check for immediate causes only
        immediate = client.execute_read(
            """
            MATCH (cause:Event)-[r:CAUSED]->(focal:Event {id: $fid, case_id: $cid})
            RETURN cause.id AS cause_id,
                   coalesce(cause.display_name, cause.event_type) AS cause_display,
                   r.confidence AS confidence, r.mechanism AS mechanism
            """,
            {"fid": focal_event_id, "cid": case_id},
        )
        return {
            "focal_event_id": focal_event_id,
            "chains": [],
            "immediate_causes": immediate,
        }

    return {
        "focal_event_id": focal_event_id,
        "chains": [
            {
                "events": p["chain"],
                "links": p["links"],
                "chain_confidence": p["chain_confidence"],
            }
            for p in paths
        ],
    }


def counterfactual_simulation(
    case_id: str,
    focal_event_id: str,
    removed_event_id: str,
    actor: str = "system",
    db: Optional[Session] = None,
) -> dict:
    """
    Counterfactual: if removed_event were not in the causal chain,
    would the focal event still have occurred?

    Check if alternative causal paths exist bypassing the removed event.
    """
    client = get_neo4j_client()

    # Check if removed event is in any causal path to focal
    in_chain = client.execute_read(
        f"""
        MATCH path = (removed:Event {{id: $rid}})-[:CAUSED*1..{GRAPH_MAX_TRAVERSAL_DEPTH}]->(focal:Event {{id: $fid}})
        RETURN count(path) AS cnt
        """,
        {"rid": removed_event_id, "fid": focal_event_id},
    )

    if not in_chain or in_chain[0]["cnt"] == 0:
        return {
            "counterfactual_result": "focal_event_unchanged",
            "reasoning": f"Event {removed_event_id} is not in any causal chain "
                         f"leading to {focal_event_id}",
            "confidence": 1.0,
        }

    # Check for alternative paths that don't go through removed event
    alt_paths = client.execute_read(
        f"""
        MATCH path = (root:Event)-[:CAUSED*1..{GRAPH_MAX_TRAVERSAL_DEPTH}]->(focal:Event {{id: $fid, case_id: $cid}})
        WHERE NOT EXISTS {{ MATCH (:Event)-[:CAUSED]->(root) }}
        AND NONE(n IN nodes(path) WHERE n.id = $rid)
        RETURN count(path) AS cnt,
               [p IN collect(path)[..1] |
                reduce(acc=1.0, r IN relationships(p) | acc * r.confidence)
               ] AS confidences
        """,
        {"fid": focal_event_id, "cid": case_id, "rid": removed_event_id},
    )

    if alt_paths and alt_paths[0]["cnt"] > 0:
        result = "focal_event_unchanged"
        reasoning = (
            f"Alternative causal path(s) exist bypassing {removed_event_id}. "
            f"Found {alt_paths[0]['cnt']} alternative path(s)."
        )
        conf = alt_paths[0]["confidences"][0] if alt_paths[0]["confidences"] else 0.5
    else:
        result = "focal_event_prevented"
        reasoning = (
            f"No alternative causal paths found. Removing {removed_event_id} "
            f"would prevent {focal_event_id}."
        )
        conf = 0.8  # High confidence in prevention

    output = {
        "counterfactual_result": result,
        "reasoning": reasoning,
        "confidence": conf,
        "focal_event_id": focal_event_id,
        "removed_event_id": removed_event_id,
    }

    # Write to Investigation Memory
    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Counterfactual simulation: remove {removed_event_id}",
            actor=actor,
            graph_refs=[focal_event_id, removed_event_id],
            reasoning=str(output),
        )
        db.commit()

    return output
