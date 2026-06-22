"""Attribution Engine — fuzzy entity resolution and SUGGESTED_IDENTIFIER management."""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db import get_db
from app.graph_client import get_neo4j_client
from app.resolution.fuzzy_match import fuzzy_match_identifiers

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attribution"])


class ConfirmRejectRequest(BaseModel):
    actor: str  # investigator id (required)
    reasoning: Optional[str] = None


@router.post("/cases/{case_id}/graph/person/{person_id}/attribution-candidates")
def get_attribution_candidates(
    case_id: str, person_id: str, db: Session = Depends(get_db),
):
    """
    Gather confirmed IdentityFacets for a Person, run fuzzy matching against
    all OSINTRecords for the case, return ranked candidates.
    Creates SUGGESTED_IDENTIFIER relationships for matches above threshold.
    """
    client = get_neo4j_client()

    # Get person's confirmed facets
    confirmed_facets = client.execute_read(
        """
        MATCH (p:Person {id: $person_id, case_id: $case_id})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
        RETURN f.id AS facet_id, f.facet_type AS facet_type, f.value AS value
        """,
        {"person_id": person_id, "case_id": case_id},
    )

    if not confirmed_facets:
        return {"candidates": [], "message": "No confirmed identifiers for this person"}

    # Get all OSINT-extracted entities from records
    from sqlalchemy import text
    osint_rows = db.execute(
        text("""
            SELECT record_id, extracted_entities FROM osint_records
            WHERE case_id = :case_id AND extracted_entities IS NOT NULL
        """),
        {"case_id": uuid.UUID(case_id)},
    ).fetchall()

    # Get already-rejected pairs to exclude
    rejected_pairs_result = client.execute_read(
        """
        MATCH (p:Person {id: $person_id})-[r:SUGGESTED_IDENTIFIER {status: 'rejected'}]->(f:IdentityFacet)
        RETURN f.value AS value
        """,
        {"person_id": person_id},
    )
    rejected_values = {r["value"].lower() for r in rejected_pairs_result}

    # Collect all existing facets in the case for matching
    all_facets = client.execute_read(
        """
        MATCH (f:IdentityFacet {case_id: $case_id})
        OPTIONAL MATCH (p:Person)-[:HAS_IDENTIFIER]->(f)
        RETURN f.id AS facet_id, f.facet_type AS facet_type, f.value AS value,
               p.id AS person_id
        """,
        {"case_id": case_id},
    )

    # Build rejected pairs set
    rejected_pairs = set()
    for cf in confirmed_facets:
        for rv in rejected_values:
            rejected_pairs.add((cf["value"].lower(), rv))

    all_candidates = []

    # For each confirmed facet, fuzzy-match against OSINT entities
    import json
    for row in osint_rows:
        entities = row[1] if isinstance(row[1], list) else json.loads(row[1]) if row[1] else []
        for entity in entities:
            e_value = entity.get("value", "")
            e_type = entity.get("entity_type", "")

            for facet in confirmed_facets:
                matches = fuzzy_match_identifiers(
                    candidate_value=e_value,
                    candidate_type=e_type,
                    existing_facets=[{
                        "facet_id": facet["facet_id"],
                        "facet_type": facet["facet_type"],
                        "value": facet["value"],
                        "person_id": person_id,
                    }],
                    rejected_pairs=rejected_pairs,
                )

                for match in matches:
                    # Create SUGGESTED_IDENTIFIER if not exists
                    sug_id = str(uuid.uuid4())
                    now = datetime.now(timezone.utc).isoformat()

                    # First ensure the OSINT entity exists as a facet
                    client.execute_write(
                        """
                        MERGE (f:IdentityFacet {value: $value, facet_type: $ftype, case_id: $case_id})
                        ON CREATE SET f.id = $fid, f.classification_tag = 'public_osint',
                                      f.created_at = $now
                        """,
                        {
                            "value": e_value, "ftype": e_type,
                            "case_id": case_id, "fid": str(uuid.uuid4()), "now": now,
                        },
                    )

                    # Create SUGGESTED_IDENTIFIER relationship
                    client.execute_write(
                        """
                        MATCH (p:Person {id: $pid}),
                              (f:IdentityFacet {value: $value, case_id: $case_id})
                        WHERE NOT EXISTS {
                            MATCH (p)-[:SUGGESTED_IDENTIFIER {status: 'rejected'}]->(f)
                        }
                        MERGE (p)-[r:SUGGESTED_IDENTIFIER]->(f)
                        ON CREATE SET r.id = $sid, r.confidence = $conf,
                                      r.match_basis = $basis, r.status = 'pending_review',
                                      r.created_at = $now
                        """,
                        {
                            "pid": person_id, "value": e_value, "case_id": case_id,
                            "sid": sug_id, "conf": match["similarity_score"],
                            "basis": match["match_basis"], "now": now,
                        },
                    )

                    all_candidates.append({
                        "osint_entity_value": e_value,
                        "osint_entity_type": e_type,
                        "matched_facet_value": facet["value"],
                        "similarity_score": match["similarity_score"],
                        "match_basis": match["match_basis"],
                    })

    # Deduplicate by osint_entity_value
    seen = set()
    unique = []
    for c in all_candidates:
        if c["osint_entity_value"] not in seen:
            seen.add(c["osint_entity_value"])
            unique.append(c)

    unique.sort(key=lambda x: x["similarity_score"], reverse=True)
    return {"candidates": unique}


@router.post("/cases/{case_id}/graph/suggested-identifier/{suggestion_id}/confirm")
def confirm_suggestion(
    case_id: str, suggestion_id: str,
    body: ConfirmRejectRequest, db: Session = Depends(get_db),
):
    """Promote SUGGESTED_IDENTIFIER to HAS_IDENTIFIER."""
    client = get_neo4j_client()

    # Find the suggestion
    result = client.execute_read(
        """
        MATCH (p:Person)-[r:SUGGESTED_IDENTIFIER {id: $sid}]->(f:IdentityFacet)
        RETURN p.id AS person_id, f.id AS facet_id, f.value AS value,
               f.facet_type AS facet_type, r.match_basis AS match_basis
        """,
        {"sid": suggestion_id},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    row = result[0]

    # Create HAS_IDENTIFIER and remove SUGGESTED_IDENTIFIER
    client.execute_write(
        """
        MATCH (p:Person {id: $pid})-[r:SUGGESTED_IDENTIFIER {id: $sid}]->(f:IdentityFacet)
        CREATE (p)-[:HAS_IDENTIFIER {confidence: r.confidence}]->(f)
        DELETE r
        """,
        {"pid": row["person_id"], "sid": suggestion_id},
    )

    return {
        "status": "confirmed",
        "person_id": row["person_id"],
        "facet_value": row["value"],
        "match_basis": row["match_basis"],
    }


@router.post("/cases/{case_id}/graph/suggested-identifier/{suggestion_id}/reject")
def reject_suggestion(
    case_id: str, suggestion_id: str,
    body: ConfirmRejectRequest, db: Session = Depends(get_db),
):
    """Mark SUGGESTED_IDENTIFIER as rejected (excluded from future runs)."""
    client = get_neo4j_client()

    result = client.execute_read(
        """
        MATCH (p:Person)-[r:SUGGESTED_IDENTIFIER {id: $sid}]->(f:IdentityFacet)
        RETURN p.id AS person_id, f.value AS value
        """,
        {"sid": suggestion_id},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    client.execute_write(
        """
        MATCH (p:Person)-[r:SUGGESTED_IDENTIFIER {id: $sid}]->(f:IdentityFacet)
        SET r.status = 'rejected', r.rejected_by = $actor, r.rejected_reason = $reason
        """,
        {"sid": suggestion_id, "actor": body.actor, "reason": body.reasoning},
    )

    return {"status": "rejected", "suggestion_id": suggestion_id}


@router.get("/cases/{case_id}/graph/person/{person_id}/attribution-profile")
def attribution_profile(case_id: str, person_id: str):
    """
    Structured summary: confirmed facets, pending suggestions, rejected candidates.
    """
    client = get_neo4j_client()

    confirmed = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
        RETURN f.facet_type AS type, f.value AS value, f.classification_tag AS tag
        """,
        {"pid": person_id, "cid": case_id},
    )

    pending = client.execute_read(
        """
        MATCH (p:Person {id: $pid})-[r:SUGGESTED_IDENTIFIER {status: 'pending_review'}]->(f:IdentityFacet)
        RETURN r.id AS suggestion_id, f.facet_type AS type, f.value AS value,
               r.confidence AS score, r.match_basis AS match_basis
        """,
        {"pid": person_id},
    )

    rejected = client.execute_read(
        """
        MATCH (p:Person {id: $pid})-[r:SUGGESTED_IDENTIFIER {status: 'rejected'}]->(f:IdentityFacet)
        RETURN f.facet_type AS type, f.value AS value,
               r.rejected_by AS rejected_by, r.rejected_reason AS reason
        """,
        {"pid": person_id},
    )

    # Group confirmed by type
    confirmed_grouped = {}
    for f in confirmed:
        confirmed_grouped.setdefault(f["type"], []).append(f["value"])

    return {
        "person_id": person_id,
        "confirmed_identifiers": confirmed_grouped,
        "pending_suggestions": pending,
        "rejected_candidates": rejected,
    }
