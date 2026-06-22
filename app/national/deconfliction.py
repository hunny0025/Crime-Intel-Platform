"""Cross-agency Deconfliction Protocol (Prompt 52).

Privacy-preserving deconfliction using HMAC-SHA256 blind hashing.
"""

import uuid
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Platform-level shared secret (in production: from secure vault)
PLATFORM_DECONFLICTION_KEY = b"crime-intel-platform-deconfliction-key-v1"


def compute_deconfliction_hash(facet_value: str) -> str:
    """Compute blind hash: HMAC-SHA256(normalized_value, platform_key)."""
    normalized = facet_value.strip().lower()
    return hmac.new(PLATFORM_DECONFLICTION_KEY, normalized.encode(), hashlib.sha256).hexdigest()


def index_identity_facet(agency_id: str, case_id: str, facet_id: str,
                         facet_value: str, facet_type: str) -> dict:
    """Index an IdentityFacet for cross-agency deconfliction."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    decon_hash = compute_deconfliction_hash(facet_value)
    hashed_case_id = hmac.new(
        PLATFORM_DECONFLICTION_KEY, case_id.encode(), hashlib.sha256
    ).hexdigest()

    # Check for existing matches from OTHER agencies
    matches = client.execute_read(
        """
        MATCH (di:DeconflictionIndex {deconfliction_hash: $hash})
        WHERE di.agency_id <> $agency
        RETURN di.agency_id AS other_agency, di.hashed_case_id AS other_case,
               di.facet_type AS facet_type, di.indexed_at AS at
        """,
        {"hash": decon_hash, "agency": agency_id},
    )

    # Store the index entry
    client.execute_write(
        """
        MERGE (di:DeconflictionIndex {deconfliction_hash: $hash, agency_id: $agency})
        ON CREATE SET di.id = $did, di.hashed_case_id = $hcid,
                      di.facet_type = $ftype, di.indexed_at = $now, di.created_at = $now
        ON MATCH SET di.indexed_at = $now
        """,
        {
            "did": str(uuid.uuid4()), "hash": decon_hash, "agency": agency_id,
            "hcid": hashed_case_id, "ftype": facet_type, "now": now,
        },
    )

    # Create alerts for matches
    alerts = []
    for match in matches:
        alert_id = str(uuid.uuid4())

        # Get other agency contact
        other_agency = client.execute_read(
            "MATCH (a:Agency {id: $aid}) RETURN a.name AS name, a.contact_officer AS contact",
            {"aid": match["other_agency"]},
        )
        contact = other_agency[0] if other_agency else {"name": "Unknown", "contact": ""}

        client.execute_write(
            """
            CREATE (da:DeconflictionAlert {
                id: $aid, our_agency_id: $our_agency,
                our_case_hashed_id: $our_case,
                other_agency_id: $other_agency,
                other_case_hashed_id: $other_case,
                facet_type: $ftype,
                detected_at: $now, status: 'pending',
                created_at: $now
            })
            """,
            {
                "aid": alert_id, "our_agency": agency_id,
                "our_case": hashed_case_id,
                "other_agency": match["other_agency"],
                "other_case": match["other_case"],
                "ftype": facet_type, "now": now,
            },
        )

        # Create reciprocal alert for the other agency
        reciprocal_id = str(uuid.uuid4())
        client.execute_write(
            """
            CREATE (da:DeconflictionAlert {
                id: $aid, our_agency_id: $other_agency,
                our_case_hashed_id: $other_case,
                other_agency_id: $our_agency,
                other_case_hashed_id: $our_case,
                facet_type: $ftype,
                detected_at: $now, status: 'pending',
                created_at: $now
            })
            """,
            {
                "aid": reciprocal_id,
                "other_agency": match["other_agency"],
                "other_case": match["other_case"],
                "our_agency": agency_id, "our_case": hashed_case_id,
                "ftype": facet_type, "now": now,
            },
        )

        alerts.append({
            "alert_id": alert_id,
            "other_agency_name": contact.get("name", ""),
            "other_agency_contact": contact.get("contact", ""),
            "facet_type": facet_type,
            "message": f"Deconfliction match detected. Your case and a case in "
                       f"{contact.get('name', 'another agency')} share an entity of type "
                       f"'{facet_type}'. Contact {contact.get('contact', '')} to coordinate.",
        })

    return {
        "facet_id": facet_id,
        "deconfliction_hash": decon_hash,
        "matches_found": len(matches),
        "alerts_created": alerts,
    }


def get_deconfliction_alerts(case_id: str, agency_id: str) -> list:
    """Return deconfliction alerts for a case."""
    client = get_neo4j_client()
    hashed_case = hmac.new(
        PLATFORM_DECONFLICTION_KEY, case_id.encode(), hashlib.sha256
    ).hexdigest()

    alerts = client.execute_read(
        """
        MATCH (da:DeconflictionAlert {our_agency_id: $agency, our_case_hashed_id: $hcid})
        OPTIONAL MATCH (a:Agency {id: da.other_agency_id})
        RETURN da.id AS id, da.other_agency_id AS other_agency_id,
               coalesce(a.name, 'Unknown') AS other_agency_name,
               coalesce(a.contact_officer, '') AS contact,
               da.facet_type AS facet_type,
               da.detected_at AS detected_at, da.status AS status
        ORDER BY da.detected_at DESC
        """,
        {"agency": agency_id, "hcid": hashed_case},
    )
    return alerts


def acknowledge_alert(alert_id: str, contacted_other: bool = False,
                      db: Optional[Session] = None) -> dict:
    """Acknowledge a deconfliction alert."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (da:DeconflictionAlert {id: $aid})
        SET da.status = 'acknowledged', da.acknowledged_at = $now,
            da.contacted_other_agency = $contacted
        """,
        {"aid": alert_id, "now": now, "contacted": contacted_other},
    )

    return {"alert_id": alert_id, "status": "acknowledged"}
