"""CRUD operations for Neo4j graph nodes and relationships.

Provides generic create/get/list operations for all node types, relationship
creation with evidence_basis validation, and neighbor queries.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import EvidenceArtifact
from app.graph.driver import get_neo4j_client
from app.graph.relationships import (
    ALL_RELATIONSHIP_TYPES,
    GLOBAL_RELATIONSHIP_TYPES,
    EVIDENCE_BACKED_RELATIONSHIP_TYPES,
)

logger = logging.getLogger(__name__)

# ── Helper: ensure Case anchor node exists ───────────────────────────────

def ensure_case_anchor(case_id: str) -> dict:
    """Create or return the CaseAnchor node for a case."""
    client = get_neo4j_client()
    result = client.execute_write(
        """
        MERGE (c:CaseAnchor {id: $case_id, case_id: $case_id})
        ON CREATE SET c.created_at = datetime()
        RETURN c {.*} AS node
        """,
        {"case_id": case_id},
    )
    return result[0]["node"] if result else {"id": case_id}


import json

def deserialize_person(node: dict) -> dict:
    if not node:
        return node
    if "merge_log" in node and isinstance(node["merge_log"], list):
        parsed = []
        for item in node["merge_log"]:
            if isinstance(item, str):
                try:
                    parsed.append(json.loads(item))
                except Exception:
                    parsed.append({"raw": item})
            else:
                parsed.append(item)
        node["merge_log"] = parsed
    return node


# ── Generic Node CRUD ────────────────────────────────────────────────────

def create_node(label: str, properties: dict) -> dict:
    """Create a node with the given label and properties."""
    client = get_neo4j_client()

    # Ensure id exists
    if "id" not in properties:
        properties["id"] = str(uuid.uuid4())
    if "created_at" not in properties:
        properties["created_at"] = datetime.now(timezone.utc).isoformat()
    elif isinstance(properties["created_at"], datetime):
        properties["created_at"] = properties["created_at"].isoformat()

    # Convert datetimes to ISO strings for Neo4j
    for key, value in properties.items():
        if isinstance(value, datetime):
            properties[key] = value.isoformat()

    # Ensure case anchor exists for case-scoped nodes
    if "case_id" in properties:
        ensure_case_anchor(properties["case_id"])

    result = client.execute_write(
        f"CREATE (n:{label} $props) RETURN n {{.*}} AS node",
        {"props": properties},
    )
    node = result[0]["node"] if result else {}
    if label == "Person":
        deserialize_person(node)
    return node


def get_node(label: str, node_id: str) -> Optional[dict]:
    """Get a node by label and id."""
    client = get_neo4j_client()
    result = client.execute_read(
        f"MATCH (n:{label} {{id: $id}}) RETURN n {{.*}} AS node",
        {"id": node_id},
    )
    node = result[0]["node"] if result else None
    if label == "Person" and node:
        deserialize_person(node)
    return node


def list_nodes(label: str, case_id: str, **filters) -> list[dict]:
    """List all nodes of a given label within a case."""
    client = get_neo4j_client()
    where_clauses = ["n.case_id = $case_id"]
    params = {"case_id": case_id}

    for key, value in filters.items():
        param_name = f"f_{key}"
        where_clauses.append(f"n.{key} = ${param_name}")
        params[param_name] = value

    where_str = " AND ".join(where_clauses)
    result = client.execute_read(
        f"MATCH (n:{label}) WHERE {where_str} RETURN n {{.*}} AS node ORDER BY n.created_at",
        params,
    )
    nodes = [r["node"] for r in result]
    if label == "Person":
        for node in nodes:
            deserialize_person(node)
    return nodes


def delete_node(label: str, node_id: str) -> bool:
    """Delete a node and all its relationships."""
    client = get_neo4j_client()
    result = client.execute_write(
        f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n RETURN count(n) AS deleted",
        {"id": node_id},
    )
    return result[0]["deleted"] > 0 if result else False


# ── Relationship CRUD ────────────────────────────────────────────────────

def validate_evidence_basis(db: Session, artifact_ids: list[str]) -> list[str]:
    """
    Validate that all artifact_ids exist in the evidence_artifacts table.
    Returns a list of invalid artifact_ids.
    """
    invalid = []
    for aid_str in artifact_ids:
        try:
            aid = uuid.UUID(aid_str)
        except ValueError:
            invalid.append(aid_str)
            continue
        exists = db.query(EvidenceArtifact).filter(
            EvidenceArtifact.artifact_id == aid
        ).first()
        if not exists:
            invalid.append(aid_str)
    return invalid


def create_relationship(
    from_id: str,
    to_id: str,
    rel_type: str,
    properties: dict = None,
) -> dict:
    """
    Create a relationship between two nodes (any labels).
    The nodes are matched by their 'id' property.
    """
    client = get_neo4j_client()
    props = properties or {}

    # Convert datetimes
    for key, value in props.items():
        if isinstance(value, datetime):
            props[key] = value.isoformat()

    result = client.execute_write(
        f"""
        MATCH (a {{id: $from_id}})
        MATCH (b {{id: $to_id}})
        CREATE (a)-[r:{rel_type} $props]->(b)
        RETURN a.id AS from_id, b.id AS to_id, type(r) AS rel_type,
               properties(r) AS rel_props
        """,
        {"from_id": from_id, "to_id": to_id, "props": props},
    )
    if not result:
        return {}
    r = result[0]
    return {
        "from_node_id": r["from_id"],
        "to_node_id": r["to_id"],
        "relationship_type": r["rel_type"],
        **r.get("rel_props", {}),
    }


def get_neighbors(case_id: str, node_id: str) -> list[dict]:
    """
    Get all directly connected nodes and their connecting relationships
    for a given node within a case.
    """
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (n {id: $node_id})-[r]-(m)
        WHERE m.case_id = $case_id OR m.case_id IS NULL
        RETURN m {.*} AS neighbor, labels(m)[0] AS node_label,
               type(r) AS rel_type,
               properties(r) AS rel_props,
               startNode(r).id AS from_id, endNode(r).id AS to_id
        """,
        {"node_id": node_id, "case_id": case_id},
    )
    neighbors = []
    seen_edges = set()
    for row in result:
        neighbor = dict(row["neighbor"])
        # Inject the Neo4j label so the frontend can route to the correct node component
        if row.get("node_label"):
            neighbor["label"] = row["node_label"]
        # Deduplicate edges (bidirectional traversal returns duplicates)
        edge_key = (row["from_id"], row["to_id"], row["rel_type"])
        if edge_key in seen_edges:
            neighbors.append({"node": neighbor, "relationship": None})
            continue
        seen_edges.add(edge_key)
        neighbors.append({
            "node": neighbor,
            "relationship": {
                "type": row["rel_type"],
                "relationship_type": row["rel_type"],
                "from_node_id": row["from_id"],
                "to_node_id": row["to_id"],
                **row.get("rel_props", {}),
            },
        })
    return neighbors


# ── Graph Summary ────────────────────────────────────────────────────────

def get_graph_summary(case_id: str) -> dict:
    """Get counts of nodes by label and relationships by type for a case."""
    client = get_neo4j_client()

    # Node counts
    node_result = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $case_id
        RETURN labels(n)[0] AS label, count(n) AS count
        """,
        {"case_id": case_id},
    )
    node_counts = {r["label"]: r["count"] for r in node_result}

    # Relationship counts
    rel_result = client.execute_read(
        """
        MATCH (n {case_id: $case_id})-[r]-()
        RETURN type(r) AS rel_type, count(r) AS count
        """,
        {"case_id": case_id},
    )
    rel_counts = {r["rel_type"]: r["count"] for r in rel_result}

    # Unprocessed file artifacts
    file_result = client.execute_read(
        """
        MATCH (e:Event {case_id: $case_id, event_type: 'file_artifact'})
        RETURN count(e) AS count
        """,
        {"case_id": case_id},
    )
    unprocessed = file_result[0]["count"] if file_result else 0

    return {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "unprocessed_file_artifacts": unprocessed,
    }
