"""Identity Ontology — IdentityFacet resolution and person merging.

Handles normalization of identity values (phone, email, etc.),
deduplication on lookup, and person merge operations.
"""

import logging
import re
import uuid
from datetime import datetime, timezone

from app.graph.driver import get_neo4j_client
from app.graph import crud

logger = logging.getLogger(__name__)


# ── Normalization Rules ──────────────────────────────────────────────────

def normalize_phone_number(value: str) -> str:
    """Strip non-digit characters, keep leading + for international."""
    stripped = re.sub(r"[^\d+]", "", value)
    # Ensure it starts with + if it had one
    if value.strip().startswith("+") and not stripped.startswith("+"):
        stripped = "+" + stripped
    if not stripped.startswith("+") and stripped:
        stripped = "+" + stripped
    return stripped


def normalize_email(value: str) -> str:
    """Lowercase and strip whitespace."""
    return value.strip().lower()


def normalize_value(facet_type: str, value: str) -> str:
    """Normalize a facet value according to its type."""
    normalizers = {
        "phone_number": normalize_phone_number,
        "email": normalize_email,
        "upi_id": lambda v: v.strip().lower(),
        "social_handle": lambda v: v.strip().lower().lstrip("@"),
        "device_imei": lambda v: re.sub(r"\D", "", v),
        "crypto_wallet_address": lambda v: v.strip(),
    }
    normalizer = normalizers.get(facet_type, lambda v: v.strip())
    return normalizer(value)


# ── Identity Facet Resolution ────────────────────────────────────────────

def resolve_identity_facet(
    case_id: str,
    facet_type: str,
    value: str,
    person_id: str = None,
    classification_tag: str = "case_sensitive",
) -> dict:
    """
    Get-or-create an IdentityFacet:
    1. Normalize the value
    2. Check if this facet already exists for this case
    3. If yes, return existing facet + linked persons
    4. If no, create facet. If person_id provided, link to that person;
       otherwise create a new Person with role='unknown' and link it.
    """
    client = get_neo4j_client()
    normalized = normalize_value(facet_type, value)

    # Check for existing facet
    existing = client.execute_read(
        """
        MATCH (f:IdentityFacet {case_id: $case_id, facet_type: $facet_type, value: $value})
        OPTIONAL MATCH (p:Person)-[:HAS_IDENTIFIER]->(f)
        RETURN f {.*} AS facet, collect(p {.*}) AS persons
        """,
        {"case_id": case_id, "facet_type": facet_type, "value": normalized},
    )

    if existing and existing[0]["facet"]:
        result = existing[0]
        persons = result["persons"]
        for p in persons:
            crud.deserialize_person(p)
        return {
            **result["facet"],
            "linked_persons": persons,
            "is_existing": True,
        }

    # Create new facet
    facet_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Determine person to link to
    if person_id is None:
        # Create a new unknown person
        person_id = str(uuid.uuid4())
        client.execute_write(
            """
            CREATE (p:Person {
                id: $person_id,
                case_id: $case_id,
                display_name: $display_name,
                role: 'unknown',
                classification_tag: $tag,
                created_at: $now,
                merge_log: []
            })
            """,
            {
                "person_id": person_id,
                "case_id": case_id,
                "display_name": f"Unknown ({facet_type}: {normalized})",
                "tag": classification_tag,
                "now": now,
            },
        )
        crud.ensure_case_anchor(case_id)

    # Create facet and link to person
    result = client.execute_write(
        """
        CREATE (f:IdentityFacet {
            id: $facet_id,
            case_id: $case_id,
            facet_type: $facet_type,
            value: $value,
            classification_tag: $tag,
            created_at: $now
        })
        WITH f
        MATCH (p:Person {id: $person_id})
        CREATE (p)-[:HAS_IDENTIFIER {confidence: 1.0, created_at: $now}]->(f)
        RETURN f {.*} AS facet, collect(p {.*}) AS persons
        """,
        {
            "facet_id": facet_id,
            "case_id": case_id,
            "facet_type": facet_type,
            "value": normalized,
            "tag": classification_tag,
            "now": now,
            "person_id": person_id,
        },
    )

    if result:
        persons = result[0]["persons"]
        for p in persons:
            crud.deserialize_person(p)
        return {
            **result[0]["facet"],
            "linked_persons": persons,
            "is_existing": False,
        }
    return {"id": facet_id, "is_existing": False, "linked_persons": []}


def get_person_identifiers(case_id: str, person_id: str) -> dict:
    """
    Return all IdentityFacets linked to a person, grouped by facet_type.
    """
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (p:Person {id: $person_id, case_id: $case_id})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
        RETURN f.facet_type AS facet_type, collect(f {.*}) AS facets
        """,
        {"person_id": person_id, "case_id": case_id},
    )
    grouped = {}
    for row in result:
        grouped[row["facet_type"]] = row["facets"]
    return grouped


def merge_persons(case_id: str, keep_id: str, merge_id: str, reason: str = "manual_merge") -> dict:
    """
    Merge two persons: re-point all relationships and IdentityFacets from
    merge_id to keep_id, then delete merge_id. Records the merge in the
    surviving node's merge_log.
    """
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Transfer all outgoing relationships
    out_transferred = 0
    in_transferred = 0
    use_manual = True

    try:
        out_result = client.execute_write(
            """
            MATCH (old:Person {id: $merge_id, case_id: $case_id})-[r]->(target)
            MATCH (keep:Person {id: $keep_id, case_id: $case_id})
            WITH keep, type(r) AS rtype, properties(r) AS rprops, target, r
            DELETE r
            WITH keep, rtype, rprops, target
            CALL apoc.create.relationship(keep, rtype, rprops, target) YIELD rel
            RETURN count(rel) AS transferred
            """,
            {"merge_id": merge_id, "keep_id": keep_id, "case_id": case_id},
        )
        if out_result:
            out_transferred = out_result[0].get("transferred", 0)
            use_manual = False
    except Exception as e:
        logger.info("APOC transfer failed, falling back to manual: %s", e)

    if use_manual:
        try:
            # Transfer outgoing relationships (without APOC)
            for rel_type in ["HAS_IDENTIFIER", "OWNS", "CONTROLS", "COMMUNICATED_WITH",
                             "PARTICIPATED_IN", "AT", "CO_LOCATED_WITH", "TRANSFERRED_TO"]:
                r = client.execute_write(
                    f"""
                    MATCH (old:Person {{id: $merge_id, case_id: $case_id}})-[r:{rel_type}]->(target)
                    MATCH (keep:Person {{id: $keep_id, case_id: $case_id}})
                    CREATE (keep)-[nr:{rel_type}]->(target)
                    SET nr = properties(r)
                    DELETE r
                    RETURN count(nr) AS cnt
                    """,
                    {"merge_id": merge_id, "keep_id": keep_id, "case_id": case_id},
                )
                if r:
                    out_transferred += r[0].get("cnt", 0)

            # Transfer incoming relationships
            for rel_type in ["HAS_IDENTIFIER", "OWNS", "CONTROLS", "COMMUNICATED_WITH",
                             "PARTICIPATED_IN", "AT", "CO_LOCATED_WITH", "TRANSFERRED_TO",
                             "PREDICTED_BY", "SUPPORTED_BY"]:
                r = client.execute_write(
                    f"""
                    MATCH (source)-[r:{rel_type}]->(old:Person {{id: $merge_id, case_id: $case_id}})
                    MATCH (keep:Person {{id: $keep_id, case_id: $case_id}})
                    CREATE (source)-[nr:{rel_type}]->(keep)
                    SET nr = properties(r)
                    DELETE r
                    RETURN count(nr) AS cnt
                    """,
                    {"merge_id": merge_id, "keep_id": keep_id, "case_id": case_id},
                )
                if r:
                    in_transferred += r[0].get("cnt", 0)
        except Exception as e:
            logger.warning("Relationship transfer issue: %s", e)

    total_transferred = out_transferred + in_transferred

    # Record merge in surviving node's merge_log (serialize entry to JSON string for Neo4j)
    import json
    merge_entry = json.dumps({
        "merged_id": merge_id,
        "timestamp": now,
        "reason": reason
    })
    client.execute_write(
        """
        MATCH (p:Person {id: $keep_id, case_id: $case_id})
        SET p.merge_log = coalesce(p.merge_log, []) + [$merge_entry]
        """,
        {"keep_id": keep_id, "case_id": case_id, "merge_entry": merge_entry},
    )

    # Count facets transferred (HAS_IDENTIFIER relationships now on keep)
    facet_result = client.execute_read(
        """
        MATCH (p:Person {id: $keep_id, case_id: $case_id})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
        RETURN count(f) AS count
        """,
        {"keep_id": keep_id, "case_id": case_id},
    )
    facets_count = facet_result[0]["count"] if facet_result else 0

    # Delete the merged person node
    client.execute_write(
        "MATCH (p:Person {id: $merge_id, case_id: $case_id}) DETACH DELETE p",
        {"merge_id": merge_id, "case_id": case_id},
    )

    return {
        "surviving_person_id": keep_id,
        "merged_person_id": merge_id,
        "relationships_transferred": total_transferred,
        "facets_transferred": facets_count,
    }
