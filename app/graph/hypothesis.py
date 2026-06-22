"""Reasoning layer primitives — Hypothesis, Assumption, Contradiction, EvidenceGap.

CRUD and timeline query operations for Phase 3's reasoning engines.
At this stage, only manual creation is supported — automated reasoning comes in Phase 5.
"""

import logging
from datetime import datetime

from app.graph.driver import get_neo4j_client
from app.graph import crud

logger = logging.getLogger(__name__)


# ── Hypothesis Operations ────────────────────────────────────────────────

def create_hypothesis(properties: dict) -> dict:
    """Create a Hypothesis node."""
    return crud.create_node("Hypothesis", properties)


def get_hypothesis(hypothesis_id: str) -> dict:
    return crud.get_node("Hypothesis", hypothesis_id)


def list_hypotheses(case_id: str) -> list[dict]:
    """List all hypotheses for a case, sorted by probability descending."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $case_id})
        RETURN h {.*} AS node
        ORDER BY h.probability DESC
        """,
        {"case_id": case_id},
    )
    return [r["node"] for r in result]


def add_predicted_by(hypothesis_id: str, target_node_id: str) -> dict:
    """Link a Hypothesis to a predicted entity via PREDICTED_BY."""
    return crud.create_relationship(
        hypothesis_id, target_node_id, "PREDICTED_BY",
        properties={"created_at": datetime.utcnow().isoformat()},
    )


# ── Assumption Operations ────────────────────────────────────────────────

def create_assumption(properties: dict) -> dict:
    return crud.create_node("Assumption", properties)


def get_assumption(assumption_id: str) -> dict:
    return crud.get_node("Assumption", assumption_id)


def list_assumptions(case_id: str) -> list[dict]:
    return crud.list_nodes("Assumption", case_id)


# ── Contradiction Operations ─────────────────────────────────────────────

def create_contradiction(properties: dict) -> dict:
    return crud.create_node("Contradiction", properties)


def get_contradiction(contradiction_id: str) -> dict:
    return crud.get_node("Contradiction", contradiction_id)


def list_contradictions(case_id: str) -> list[dict]:
    """List all contradictions for a case, sorted by severity."""
    client = get_neo4j_client()
    severity_order = {"high": 0, "medium": 1, "low": 2}
    result = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $case_id})
        RETURN c {.*} AS node
        """,
        {"case_id": case_id},
    )
    nodes = [r["node"] for r in result]
    nodes.sort(key=lambda n: severity_order.get(n.get("severity", "low"), 2))
    return nodes


def add_involves(contradiction_id: str, node_id: str, nature: str = "") -> dict:
    """Link a Contradiction to an involved node via INVOLVES."""
    return crud.create_relationship(
        contradiction_id, node_id, "INVOLVES",
        properties={"nature": nature, "created_at": datetime.utcnow().isoformat()},
    )


# ── Evidence Gap Operations ──────────────────────────────────────────────

def create_evidence_gap(properties: dict) -> dict:
    return crud.create_node("EvidenceGap", properties)


def get_evidence_gap(gap_id: str) -> dict:
    return crud.get_node("EvidenceGap", gap_id)


def list_evidence_gaps(case_id: str) -> list[dict]:
    """List open evidence gaps, sorted by urgency."""
    client = get_neo4j_client()
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    result = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $case_id, status: 'open'})
        RETURN g {.*} AS node
        """,
        {"case_id": case_id},
    )
    nodes = [r["node"] for r in result]
    nodes.sort(key=lambda n: urgency_order.get(n.get("urgency", "low"), 2))
    return nodes


def add_relates_to(gap_id: str, node_id: str) -> dict:
    """Link an EvidenceGap to a related node via RELATES_TO."""
    return crud.create_relationship(
        gap_id, node_id, "RELATES_TO",
        properties={"created_at": datetime.utcnow().isoformat()},
    )


# ── Timeline Query ───────────────────────────────────────────────────────

def query_timeline(case_id: str, from_ts: str, to_ts: str) -> list[dict]:
    """
    Return all Event nodes whose valid_from/valid_to interval overlaps the
    requested window, with connected Persons/Locations/Accounts via
    PARTICIPATED_IN/AT, ordered by valid_from.

    Each result is annotated with confidence and evidence_basis from the
    connecting relationships.
    """
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (e:Event {case_id: $case_id})
        WHERE (e.valid_from IS NULL OR e.valid_from <= $to_ts)
          AND (e.valid_to IS NULL OR e.valid_to >= $from_ts)
        OPTIONAL MATCH (e)<-[r:PARTICIPATED_IN|AT]-(connected)
        RETURN e {.*} AS event,
               e.valid_from AS valid_from,
               collect(DISTINCT {
                   node: connected {.*},
                   rel_type: type(r),
                   confidence: r.confidence,
                   evidence_basis: r.evidence_basis
               }) AS connected_entities
        ORDER BY valid_from
        """,
        {"case_id": case_id, "from_ts": from_ts, "to_ts": to_ts},
    )

    timeline = []
    for row in result:
        connected = [
            c for c in row["connected_entities"]
            if c.get("node") is not None
        ]
        timeline.append({
            "event": row["event"],
            "connected_entities": connected,
            "confidence": row["event"].get("confidence"),
            "evidence_basis": [],
        })
    return timeline
