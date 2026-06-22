"""Explainable Legal Reasoning — audit trail for every legal recommendation.

Every legal recommendation, mapping, qualification, and assessment produces a
LegalReasoningTrace that documents:
  - WHY the recommendation was made
  - WHICH evidence supports it
  - WHICH legal elements are satisfied / unsatisfied
  - WHAT additional evidence would improve confidence

This module NEVER determines guilt. All outputs are advisory only.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

ADVISORY_DISCLAIMER = (
    "This reasoning trace is generated automatically for investigative support. "
    "It does not constitute legal advice and must not be used to determine guilt. "
    "Final decisions require independent prosecutorial and judicial assessment."
)


def create_reasoning_trace(
    case_id: str,
    engine_source: str,
    recommendation_text: str,
    why: str,
    supporting_evidence: list[dict] = None,
    satisfied_elements: list[dict] = None,
    unsatisfied_elements: list[dict] = None,
    improvement_suggestions: list[str] = None,
    confidence_level: str = "medium",
    legal_basis: str = "",
    linked_node_ids: list[str] = None,
) -> dict:
    """Create and persist a LegalReasoningTrace node in Neo4j.

    Args:
        case_id: The case this trace belongs to.
        engine_source: Which engine produced this (e.g., 'element_mapper').
        recommendation_text: The recommendation being explained.
        why: Plain-language explanation of why the recommendation was made.
        supporting_evidence: Evidence items that support this reasoning.
        satisfied_elements: Legal elements already satisfied.
        unsatisfied_elements: Legal elements still unsupported.
        improvement_suggestions: What additional evidence would improve confidence.
        confidence_level: 'high', 'medium', or 'low'.
        legal_basis: Statutory reference (e.g., 'BNS 2023 Section 318').
        linked_node_ids: Graph node IDs to link this trace to.
    """
    client = get_neo4j_client()
    trace_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    trace = {
        "trace_id": trace_id,
        "case_id": case_id,
        "engine_source": engine_source,
        "recommendation_text": recommendation_text,
        "why": why,
        "supporting_evidence": supporting_evidence or [],
        "satisfied_elements": satisfied_elements or [],
        "unsatisfied_elements": unsatisfied_elements or [],
        "improvement_suggestions": improvement_suggestions or [],
        "confidence_level": confidence_level,
        "legal_basis": legal_basis,
        "disclaimer": ADVISORY_DISCLAIMER,
        "created_at": now,
    }

    client.execute_write(
        """
        CREATE (t:LegalReasoningTrace {
            id: $tid, case_id: $cid,
            engine_source: $engine,
            recommendation_text: $rec,
            why: $why,
            supporting_evidence: $se,
            satisfied_elements: $sat,
            unsatisfied_elements: $unsat,
            improvement_suggestions: $impr,
            confidence_level: $conf,
            legal_basis: $basis,
            disclaimer: $disc,
            classification_tag: 'case_sensitive',
            created_at: $now
        })
        """,
        {
            "tid": trace_id, "cid": case_id,
            "engine": engine_source,
            "rec": recommendation_text,
            "why": why,
            "se": json.dumps(supporting_evidence or []),
            "sat": json.dumps(satisfied_elements or []),
            "unsat": json.dumps(unsatisfied_elements or []),
            "impr": json.dumps(improvement_suggestions or []),
            "conf": confidence_level,
            "basis": legal_basis,
            "disc": ADVISORY_DISCLAIMER,
            "now": now,
        },
    )

    # Link trace to relevant graph nodes
    for node_id in (linked_node_ids or []):
        if node_id:
            client.execute_write(
                """
                MATCH (t:LegalReasoningTrace {id: $tid})
                MATCH (n {id: $nid})
                MERGE (t)-[:EXPLAINS]->(n)
                """,
                {"tid": trace_id, "nid": node_id},
            )

    logger.info(
        "Created LegalReasoningTrace %s for case %s by %s (confidence=%s)",
        trace_id, case_id, engine_source, confidence_level,
    )
    return trace


def get_reasoning_traces(case_id: str, engine_source: str = None,
                         limit: int = 50) -> list[dict]:
    """Return all reasoning traces for a case, optionally filtered by engine."""
    client = get_neo4j_client()

    if engine_source:
        rows = client.execute_read(
            """
            MATCH (t:LegalReasoningTrace {case_id: $cid, engine_source: $engine})
            RETURN t.id AS trace_id, t.engine_source AS engine_source,
                   t.recommendation_text AS recommendation_text,
                   t.why AS why, t.confidence_level AS confidence_level,
                   t.legal_basis AS legal_basis,
                   t.supporting_evidence AS supporting_evidence,
                   t.satisfied_elements AS satisfied_elements,
                   t.unsatisfied_elements AS unsatisfied_elements,
                   t.improvement_suggestions AS improvement_suggestions,
                   t.created_at AS created_at
            ORDER BY t.created_at DESC
            LIMIT $limit
            """,
            {"cid": case_id, "engine": engine_source, "limit": limit},
        )
    else:
        rows = client.execute_read(
            """
            MATCH (t:LegalReasoningTrace {case_id: $cid})
            RETURN t.id AS trace_id, t.engine_source AS engine_source,
                   t.recommendation_text AS recommendation_text,
                   t.why AS why, t.confidence_level AS confidence_level,
                   t.legal_basis AS legal_basis,
                   t.supporting_evidence AS supporting_evidence,
                   t.satisfied_elements AS satisfied_elements,
                   t.unsatisfied_elements AS unsatisfied_elements,
                   t.improvement_suggestions AS improvement_suggestions,
                   t.created_at AS created_at
            ORDER BY t.created_at DESC
            LIMIT $limit
            """,
            {"cid": case_id, "limit": limit},
        )

    traces = []
    for row in rows:
        traces.append({
            "trace_id": row["trace_id"],
            "engine_source": row["engine_source"],
            "recommendation_text": row["recommendation_text"],
            "why": row["why"],
            "confidence_level": row["confidence_level"],
            "legal_basis": row["legal_basis"],
            "supporting_evidence": _safe_json(row.get("supporting_evidence")),
            "satisfied_elements": _safe_json(row.get("satisfied_elements")),
            "unsatisfied_elements": _safe_json(row.get("unsatisfied_elements")),
            "improvement_suggestions": _safe_json(row.get("improvement_suggestions")),
            "created_at": row["created_at"],
            "disclaimer": ADVISORY_DISCLAIMER,
        })
    return traces


def get_trace_for_recommendation(trace_id: str) -> Optional[dict]:
    """Return a specific reasoning trace by its ID."""
    client = get_neo4j_client()
    rows = client.execute_read(
        """
        MATCH (t:LegalReasoningTrace {id: $tid})
        RETURN t.id AS trace_id, t.case_id AS case_id,
               t.engine_source AS engine_source,
               t.recommendation_text AS recommendation_text,
               t.why AS why, t.confidence_level AS confidence_level,
               t.legal_basis AS legal_basis,
               t.supporting_evidence AS supporting_evidence,
               t.satisfied_elements AS satisfied_elements,
               t.unsatisfied_elements AS unsatisfied_elements,
               t.improvement_suggestions AS improvement_suggestions,
               t.created_at AS created_at
        """,
        {"tid": trace_id},
    )
    if not rows:
        return None

    row = rows[0]
    return {
        "trace_id": row["trace_id"],
        "case_id": row["case_id"],
        "engine_source": row["engine_source"],
        "recommendation_text": row["recommendation_text"],
        "why": row["why"],
        "confidence_level": row["confidence_level"],
        "legal_basis": row["legal_basis"],
        "supporting_evidence": _safe_json(row.get("supporting_evidence")),
        "satisfied_elements": _safe_json(row.get("satisfied_elements")),
        "unsatisfied_elements": _safe_json(row.get("unsatisfied_elements")),
        "improvement_suggestions": _safe_json(row.get("improvement_suggestions")),
        "created_at": row["created_at"],
        "disclaimer": ADVISORY_DISCLAIMER,
    }


def _safe_json(val) -> list:
    """Safely parse JSON string or return as-is if already a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return []
    return []
