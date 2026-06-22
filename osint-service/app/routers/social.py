"""Social Graph Intelligence — expand connections, community detection."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.graph_client import get_neo4j_client
from app.adapters.social_adapter import SocialAdapter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["social-graph"])


@router.post("/cases/{case_id}/osint/social-graph/{account_node_id}/expand")
def expand_social_graph(
    case_id: str,
    account_node_id: str,
    max_connections: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Expand a social graph from an Account/IdentityFacet node.
    Fetches public connections and creates FOLLOWS relationships.
    """
    client = get_neo4j_client()

    # Get the account node
    node_result = client.execute_read(
        """
        MATCH (n {id: $nid, case_id: $cid})
        RETURN n.value AS value, n.facet_type AS facet_type,
               labels(n)[0] AS label
        """,
        {"nid": account_node_id, "cid": case_id},
    )
    if not node_result:
        return {"error": "Account node not found"}

    node = node_result[0]
    handle = node.get("value", "")
    facet_type = node.get("facet_type", "")

    # Determine platform
    platform = "generic"
    if "github" in facet_type.lower() or "github" in handle.lower():
        platform = "github"
    elif "twitter" in facet_type.lower() or "x.com" in handle.lower():
        platform = "twitter"

    adapter = SocialAdapter(platform=platform)
    if not adapter.is_available():
        return {
            "error": f"unavailable — credentials not configured for {platform}",
            "account": handle,
        }

    # Fetch connections
    conn_result = adapter.expand_connections(handle, max_connections)
    now = datetime.now(timezone.utc).isoformat()
    created_count = 0

    for entity in conn_result.extracted_entities[:max_connections]:
        conn_value = entity.get("value", "")
        conn_id = str(uuid.uuid4())

        # Create Account node for connection
        client.execute_write(
            """
            MERGE (a:Account {display_name: $name, case_id: $cid})
            ON CREATE SET a.id = $id, a.account_type = $platform,
                          a.classification_tag = 'public_osint', a.created_at = $now
            """,
            {"name": conn_value, "cid": case_id, "id": conn_id,
             "platform": platform, "now": now},
        )

        # Create FOLLOWS relationship
        client.execute_write(
            """
            MATCH (src {id: $src_id}), (tgt:Account {display_name: $name, case_id: $cid})
            MERGE (src)-[r:FOLLOWS]->(tgt)
            ON CREATE SET r.confidence = 0.5, r.classification_tag = 'public_osint',
                          r.created_at = $now
            """,
            {"src_id": account_node_id, "name": conn_value, "cid": case_id, "now": now},
        )
        created_count += 1

    return {
        "account": handle,
        "platform": platform,
        "connections_created": created_count,
        "max_connections": max_connections,
    }


@router.get("/cases/{case_id}/osint/social-graph/{account_node_id}/communities")
def get_communities(case_id: str, account_node_id: str):
    """
    Run Louvain community detection on the OSINT social subgraph
    and return communities the given account belongs to.
    """
    client = get_neo4j_client()

    # Build graph of FOLLOWS/MEMBER_OF relationships
    edges = client.execute_read(
        """
        MATCH (a)-[r:FOLLOWS|MEMBER_OF]->(b)
        WHERE (a.case_id = $cid OR a.classification_tag = 'public_osint')
          AND (b.case_id = $cid OR b.classification_tag = 'public_osint')
        RETURN a.id AS source, b.id AS target,
               coalesce(a.display_name, a.value, a.id) AS source_name,
               coalesce(b.display_name, b.value, b.id) AS target_name
        """,
        {"cid": case_id},
    )

    if not edges:
        return {"communities": [], "message": "No social graph edges found"}

    import networkx as nx
    try:
        import community as community_louvain
    except ImportError:
        return {"error": "python-louvain not installed"}

    # Build undirected graph for community detection
    G = nx.Graph()
    node_names = {}
    for edge in edges:
        G.add_edge(edge["source"], edge["target"])
        node_names[edge["source"]] = edge["source_name"]
        node_names[edge["target"]] = edge["target_name"]

    if len(G.nodes()) < 2:
        return {"communities": [], "message": "Graph too small for community detection"}

    # Run Louvain
    partition = community_louvain.best_partition(G)

    # Store community_id on nodes
    for node_id, comm_id in partition.items():
        client.execute_write(
            "MATCH (n {id: $nid}) SET n.community_id = $cid",
            {"nid": node_id, "cid": comm_id},
        )

    # Find target's community
    target_comm = partition.get(account_node_id)
    if target_comm is None:
        return {"communities": [], "message": "Account not found in social graph"}

    # Gather community members
    members = [
        {"node_id": nid, "display": node_names.get(nid, nid)}
        for nid, cid in partition.items()
        if cid == target_comm and nid != account_node_id
    ]

    # Also return all communities summary
    comm_summary = {}
    for nid, cid in partition.items():
        comm_summary.setdefault(cid, []).append(node_names.get(nid, nid))

    return {
        "account_community_id": target_comm,
        "community_members": members,
        "all_communities": {
            str(k): {"size": len(v), "members": v[:10]}
            for k, v in comm_summary.items()
        },
    }
