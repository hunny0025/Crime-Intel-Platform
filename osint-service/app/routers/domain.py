"""Domain Intelligence endpoint — runs WHOIS, DNS, and crt.sh adapters."""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.graph_client import get_neo4j_client
from app.adapters.whois_adapter import WhoisAdapter
from app.adapters.dns_adapter import DNSAdapter
from app.adapters.crt_sh_adapter import CrtShAdapter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["domain-intelligence"])

# Adapter instances
_whois = WhoisAdapter()
_dns = DNSAdapter()
_crt_sh = CrtShAdapter()


class DomainLookupRequest(BaseModel):
    domain: str


class OSINTRecordCreate(BaseModel):
    record_id: str
    case_id: str
    source_type: str
    query: str
    raw_result: dict
    extracted_entities: list[dict]
    classification_tag: str = "public_osint"


def _store_osint_record(db: Session, case_id: str, result) -> dict:
    """Store an OSINTRecord in postgres."""
    from sqlalchemy import text
    record_id = result.record_id
    db.execute(
        text("""
            INSERT INTO osint_records
                (record_id, case_id, source_type, query, retrieved_at,
                 raw_result, extracted_entities, classification_tag)
            VALUES
                (:record_id, :case_id, :source_type, :query, :retrieved_at,
                 :raw_result, :extracted_entities, :classification_tag)
        """),
        {
            "record_id": uuid.UUID(record_id),
            "case_id": uuid.UUID(case_id),
            "source_type": result.source_type,
            "query": result.query,
            "retrieved_at": result.retrieved_at,
            "raw_result": str(result.raw_result).replace("'", '"') if not isinstance(result.raw_result, str) else result.raw_result,
            "extracted_entities": str(result.extracted_entities).replace("'", '"') if not isinstance(result.extracted_entities, str) else result.extracted_entities,
            "classification_tag": result.classification_tag,
        },
    )
    return result.to_dict()


def _store_record_via_orm(db: Session, case_id: str, result) -> dict:
    """Store an OSINTRecord using raw SQL to avoid needing ORM models in osint-service."""
    import json
    from sqlalchemy import text
    record_id = uuid.UUID(result.record_id)
    db.execute(
        text("""
            INSERT INTO osint_records
                (record_id, case_id, source_type, query, retrieved_at,
                 raw_result, extracted_entities, classification_tag)
            VALUES
                (:rid, :cid, :st, :q, :rat, :rr::jsonb, :ee::jsonb, :ct)
        """),
        {
            "rid": record_id,
            "cid": uuid.UUID(case_id),
            "st": result.source_type,
            "q": result.query,
            "rat": result.retrieved_at,
            "rr": json.dumps(result.raw_result),
            "ee": json.dumps(result.extracted_entities),
            "ct": result.classification_tag,
        },
    )
    db.commit()
    return result.to_dict()


def _link_entity_to_graph(case_id: str, entity: dict):
    """Link an extracted entity into the case graph via identity facets."""
    client = get_neo4j_client()
    etype = entity.get("entity_type", "")
    value = entity.get("value", "")
    confidence = entity.get("confidence", 0.5)

    # Map entity types to IdentityFacet types
    facet_type_map = {
        "email": "email",
        "ip_address": "ip_address",
        "ip_address_v6": "ip_address",
        "organization": "organization",
        "related_domain": "domain",
        "social_handle": "social_handle",
        "crypto_wallet_address": "crypto_wallet_address",
    }

    facet_type = facet_type_map.get(etype)
    if not facet_type:
        return

    facet_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    if facet_type == "organization":
        # Create Organization node
        client.execute_write(
            """
            MERGE (o:Organization {display_name: $value, case_id: $case_id})
            ON CREATE SET o.id = $id, o.classification_tag = 'public_osint',
                          o.created_at = $now
            """,
            {"value": value, "case_id": case_id, "id": str(uuid.uuid4()), "now": now},
        )
    else:
        # Create IdentityFacet
        client.execute_write(
            """
            MERGE (f:IdentityFacet {facet_type: $facet_type, value: $value, case_id: $case_id})
            ON CREATE SET f.id = $id, f.classification_tag = 'public_osint',
                          f.confidence = $confidence, f.created_at = $now
            """,
            {
                "facet_type": facet_type, "value": value, "case_id": case_id,
                "id": facet_id, "confidence": confidence, "now": now,
            },
        )


@router.post("/cases/{case_id}/osint/domain-lookup")
def domain_lookup(case_id: str, body: DomainLookupRequest, db: Session = Depends(get_db)):
    """
    Run all domain intelligence adapters (WHOIS, DNS, crt.sh) for a domain.
    Stores OSINTRecords, extracts entities, links into case graph.
    """
    domain = body.domain
    results = []

    for adapter in [_whois, _dns, _crt_sh]:
        if adapter.is_available():
            result = adapter.execute(domain)
        else:
            result = adapter.unavailable_result(domain)

        stored = _store_record_via_orm(db, case_id, result)
        results.append(stored)

        # Link extracted entities into graph
        if not result.error:
            for entity in result.extracted_entities:
                try:
                    _link_entity_to_graph(case_id, entity)
                except Exception as e:
                    logger.warning("Failed to link entity %s: %s", entity, e)

    return {"domain": domain, "records": results}
