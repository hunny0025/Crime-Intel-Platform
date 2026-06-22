"""Cryptocurrency Intelligence — wallet tracing, clustering, flow analysis."""

import uuid
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db import get_db
from app.graph_client import get_neo4j_client
from app.adapters.crypto_adapter import BitcoinAdapter, EthereumAdapter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["crypto-intelligence"])

_btc = BitcoinAdapter()
_eth = EthereumAdapter()


@router.post("/cases/{case_id}/osint/crypto/{wallet_facet_id}/trace")
def trace_wallet(
    case_id: str, wallet_facet_id: str, db: Session = Depends(get_db),
):
    """
    Trace a crypto wallet: fetch transactions, create counterparty Account nodes,
    create TRANSFERRED_TO relationships, apply common-input-ownership clustering.
    """
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get wallet address from facet
    facet_result = client.execute_read(
        """
        MATCH (f:IdentityFacet {id: $fid, case_id: $cid})
        RETURN f.value AS address, f.facet_type AS ftype
        """,
        {"fid": wallet_facet_id, "cid": case_id},
    )
    if not facet_result:
        raise HTTPException(status_code=404, detail="Wallet facet not found")

    address = facet_result[0]["address"]
    ftype = facet_result[0].get("ftype", "")

    # Determine blockchain
    is_eth = address.startswith("0x") and len(address) == 42
    adapter = _eth if is_eth else _btc

    if not adapter.is_available():
        return {"error": f"unavailable — credentials not configured for {adapter.source_type}"}

    result = adapter.execute(address)

    # Store OSINT record
    db.execute(
        text("""
            INSERT INTO osint_records
                (record_id, case_id, source_type, query, retrieved_at,
                 raw_result, extracted_entities, classification_tag)
            VALUES (:rid, :cid, :st, :q, :rat, :rr::jsonb, :ee::jsonb, :ct)
        """),
        {
            "rid": uuid.UUID(result.record_id), "cid": uuid.UUID(case_id),
            "st": result.source_type, "q": address,
            "rat": result.retrieved_at,
            "rr": json.dumps(result.raw_result),
            "ee": json.dumps(result.extracted_entities),
            "ct": "public_osint",
        },
    )
    db.commit()

    # Create counterparty nodes and TRANSFERRED_TO relationships
    created_nodes = 0
    created_rels = 0

    # Ensure source wallet has an Account node
    client.execute_write(
        """
        MERGE (a:Account {display_name: $addr, case_id: $cid})
        ON CREATE SET a.id = $id, a.account_type = 'crypto_wallet',
                      a.classification_tag = 'public_osint', a.created_at = $now
        """,
        {"addr": address, "cid": case_id, "id": str(uuid.uuid4()), "now": now},
    )

    for entity in result.extracted_entities:
        addr = entity.get("value", "")
        if not addr:
            continue

        # Create Account node for counterparty
        cp_id = str(uuid.uuid4())
        client.execute_write(
            """
            MERGE (a:Account {display_name: $addr, case_id: $cid})
            ON CREATE SET a.id = $id, a.account_type = 'crypto_wallet',
                          a.classification_tag = 'public_osint', a.created_at = $now
            """,
            {"addr": addr, "cid": case_id, "id": cp_id, "now": now},
        )

        # Create IdentityFacet
        client.execute_write(
            """
            MERGE (f:IdentityFacet {value: $addr, facet_type: 'crypto_wallet_address', case_id: $cid})
            ON CREATE SET f.id = $fid, f.classification_tag = 'public_osint', f.created_at = $now
            """,
            {"addr": addr, "cid": case_id, "fid": str(uuid.uuid4()), "now": now},
        )

        # TRANSFERRED_TO relationship
        rel = entity.get("relationship", "output")
        tx_hash = entity.get("tx_hash", "")

        if rel == "output":
            # Source → Counterparty
            client.execute_write(
                """
                MATCH (src:Account {display_name: $src_addr, case_id: $cid}),
                      (tgt:Account {display_name: $tgt_addr, case_id: $cid})
                MERGE (src)-[r:TRANSFERRED_TO {tx_hash: $tx}]->(tgt)
                ON CREATE SET r.confidence = 1.0, r.classification_tag = 'public_osint',
                              r.created_at = $now
                """,
                {"src_addr": address, "tgt_addr": addr, "cid": case_id,
                 "tx": tx_hash, "now": now},
            )
        else:
            # Counterparty → Source
            client.execute_write(
                """
                MATCH (src:Account {display_name: $src_addr, case_id: $cid}),
                      (tgt:Account {display_name: $tgt_addr, case_id: $cid})
                MERGE (src)-[r:TRANSFERRED_TO {tx_hash: $tx}]->(tgt)
                ON CREATE SET r.confidence = 1.0, r.classification_tag = 'public_osint',
                              r.created_at = $now
                """,
                {"src_addr": addr, "tgt_addr": address, "cid": case_id,
                 "tx": tx_hash, "now": now},
            )

        created_nodes += 1
        created_rels += 1

    # Apply common-input-ownership clustering (Bitcoin only)
    clusters = []
    if not is_eth and hasattr(adapter, "find_common_input_clusters"):
        clusters = adapter.find_common_input_clusters(result.raw_result)
        for cluster in clusters:
            cluster_id = str(uuid.uuid4())
            addrs = cluster["addresses"]
            # Set cluster_id on all addresses in the cluster
            for addr in addrs:
                client.execute_write(
                    """
                    MATCH (a:Account {display_name: $addr, case_id: $cid})
                    SET a.cluster_id = $cluster_id
                    """,
                    {"addr": addr, "cid": case_id, "cluster_id": cluster_id},
                )
            # Create SAME_ENTITY_CLUSTER relationships between all pairs
            for i in range(len(addrs)):
                for j in range(i + 1, len(addrs)):
                    client.execute_write(
                        """
                        MATCH (a:Account {display_name: $a1, case_id: $cid}),
                              (b:Account {display_name: $a2, case_id: $cid})
                        MERGE (a)-[r:SAME_ENTITY_CLUSTER]-(b)
                        ON CREATE SET r.confidence = 0.8,
                                      r.evidence_basis = $tx,
                                      r.created_at = $now
                        """,
                        {"a1": addrs[i], "a2": addrs[j], "cid": case_id,
                         "tx": cluster["tx_hash"], "now": now},
                    )

    return {
        "address": address,
        "blockchain": "ethereum" if is_eth else "bitcoin",
        "nodes_created": created_nodes,
        "relationships_created": created_rels,
        "clusters_found": len(clusters),
    }


@router.get("/cases/{case_id}/osint/crypto/{wallet_facet_id}/cluster")
def get_wallet_cluster(case_id: str, wallet_facet_id: str):
    """Return all Account nodes sharing a cluster_id with the given wallet."""
    client = get_neo4j_client()

    facet = client.execute_read(
        "MATCH (f:IdentityFacet {id: $fid}) RETURN f.value AS address",
        {"fid": wallet_facet_id},
    )
    if not facet:
        raise HTTPException(status_code=404, detail="Wallet facet not found")

    address = facet[0]["address"]

    cluster = client.execute_read(
        """
        MATCH (src:Account {display_name: $addr, case_id: $cid})
        WHERE src.cluster_id IS NOT NULL
        WITH src.cluster_id AS cid
        MATCH (a:Account {cluster_id: cid, case_id: $case_id})
        OPTIONAL MATCH (a)-[r:SAME_ENTITY_CLUSTER]-(b:Account)
        RETURN a.display_name AS address, a.cluster_id AS cluster_id,
               collect(DISTINCT {peer: b.display_name, tx: r.evidence_basis}) AS links
        """,
        {"addr": address, "cid": case_id, "case_id": case_id},
    )

    return {"address": address, "cluster": cluster}


@router.get("/cases/{case_id}/osint/crypto/{wallet_facet_id}/flow")
def get_money_flow(
    case_id: str,
    wallet_facet_id: str,
    depth: int = Query(2, ge=1, le=5),
):
    """Return TRANSFERRED_TO subgraph reachable from this wallet up to depth hops."""
    client = get_neo4j_client()

    facet = client.execute_read(
        "MATCH (f:IdentityFacet {id: $fid}) RETURN f.value AS address",
        {"fid": wallet_facet_id},
    )
    if not facet:
        raise HTTPException(status_code=404, detail="Wallet facet not found")

    address = facet[0]["address"]

    flow = client.execute_read(
        f"""
        MATCH path = (src:Account {{display_name: $addr, case_id: $cid}})
                      -[:TRANSFERRED_TO*1..{depth}]->(dst:Account)
        UNWIND relationships(path) AS r
        WITH DISTINCT r, startNode(r) AS from_node, endNode(r) AS to_node
        RETURN from_node.display_name AS from_addr,
               to_node.display_name AS to_addr,
               r.tx_hash AS tx_hash,
               r.created_at AS timestamp
        ORDER BY r.created_at
        """,
        {"addr": address, "cid": case_id},
    )

    return {"address": address, "depth": depth, "flow": flow}
