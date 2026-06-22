"""Evidence Gap Rule 2 — Single-Source Identifier Gap.

For every Person, checks if one identity category (phone vs email/social)
is disproportionately thin, suggesting undiscovered accounts.
"""

import logging

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.graph.hypothesis import create_evidence_gap, add_relates_to
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Thresholds
RICH_THRESHOLD = 3   # "rich" = 3+ identifiers of one category
THIN_THRESHOLD = 1   # "thin" = 1 or fewer of the other category


def check_single_source_identifier(case_id: str, db: Session) -> list[dict]:
    """
    Detect Persons with unbalanced identifier coverage across categories.

    Category A (phone-like): phone_number, device_imei
    Category B (digital-like): email, social_handle, upi_id, crypto_wallet_address

    If one category has 3+ and the other has ≤1, create an EvidenceGap.

    Returns list of created EvidenceGap dicts.
    """
    client = get_neo4j_client()
    gaps_created = []

    persons = client.execute_read(
        """
        MATCH (p:Person {case_id: $case_id})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
        RETURN p.id AS person_id, p.display_name AS name,
               collect({facet_type: f.facet_type, value: f.value}) AS facets
        """,
        {"case_id": case_id},
    )

    phone_types = {"phone_number", "device_imei"}
    digital_types = {"email", "social_handle", "upi_id", "crypto_wallet_address"}

    for person in persons:
        facets = person["facets"]
        phone_count = sum(1 for f in facets if f.get("facet_type") in phone_types)
        digital_count = sum(1 for f in facets if f.get("facet_type") in digital_types)

        gap_description = None

        if phone_count >= RICH_THRESHOLD and digital_count <= THIN_THRESHOLD:
            gap_description = (
                f"Person {person['name']} has {phone_count} phone-related identifiers "
                f"but only {digital_count} email/social identifiers — "
                f"additional digital accounts likely exist but haven't been identified."
            )
        elif digital_count >= RICH_THRESHOLD and phone_count <= THIN_THRESHOLD:
            gap_description = (
                f"Person {person['name']} has {digital_count} email/social identifiers "
                f"but only {phone_count} phone-related identifiers — "
                f"additional phone numbers/devices likely exist but haven't been identified."
            )

        if gap_description is None:
            continue

        gap = create_evidence_gap({
            "case_id": case_id,
            "description": gap_description,
            "expected_value": "medium",
            "urgency": "low",
            "status": "open",
            "classification_tag": "case_sensitive",
        })
        gap_id = gap.get("id", "")

        add_relates_to(gap_id, person["person_id"])

        write_memory_record(
            db=db,
            case_id=case_id,
            record_type=MemoryRecordType.gap_identified,
            description=gap_description,
            actor="system:gap_engine",
            graph_refs=[gap_id, person["person_id"]],
            reasoning=f"Identifier imbalance: phone={phone_count}, digital={digital_count}",
        )
        db.commit()
        gaps_created.append(gap)

    return gaps_created
