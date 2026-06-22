"""Multi-tenancy + Agency Isolation (Prompt 51).

Agency registry, JWT-based isolation, and Postgres RLS scaffolding.
"""

import uuid
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


# ── Agency Registry ─────────────────────────────────────────────────────

class AgencyType:
    STATE_POLICE = "state_police"
    CENTRAL_AGENCY = "central_agency"
    I4C = "i4c"
    CERT_IN = "cert_in"
    CUSTOMS = "customs"
    ALL = {STATE_POLICE, CENTRAL_AGENCY, I4C, CERT_IN, CUSTOMS}


def create_agency(agency_name: str, agency_type: str, jurisdiction: str,
                  contact_officer: str) -> dict:
    """Register a new agency."""
    client = get_neo4j_client()
    agency_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        CREATE (a:Agency {
            id: $aid, name: $name, agency_type: $atype,
            jurisdiction: $jurisdiction, contact_officer: $contact,
            onboarded_at: $now, status: 'active', created_at: $now
        })
        """,
        {
            "aid": agency_id, "name": agency_name, "atype": agency_type,
            "jurisdiction": jurisdiction, "contact": contact_officer,
            "now": now,
        },
    )

    return {
        "agency_id": agency_id,
        "agency_name": agency_name,
        "agency_type": agency_type,
        "jurisdiction": jurisdiction,
        "status": "active",
        "onboarded_at": now,
    }


def list_agencies() -> list:
    """List all registered agencies."""
    client = get_neo4j_client()
    return client.execute_read(
        """
        MATCH (a:Agency)
        RETURN a.id AS id, a.name AS name, a.agency_type AS type,
               a.jurisdiction AS jurisdiction,
               a.contact_officer AS contact, a.status AS status,
               a.onboarded_at AS onboarded_at
        ORDER BY a.name
        """,
    )


def provision_investigator(agency_id: str, investigator_name: str,
                           role: str = "investigator") -> dict:
    """Provision an investigator for an agency."""
    client = get_neo4j_client()
    inv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (a:Agency {id: $agid})
        CREATE (i:Investigator {
            id: $iid, name: $name, role: $role,
            agency_id: $agid, provisioned_at: $now,
            status: 'active', created_at: $now
        })
        CREATE (i)-[:BELONGS_TO]->(a)
        """,
        {"agid": agency_id, "iid": inv_id, "name": investigator_name,
         "role": role, "now": now},
    )

    return {
        "investigator_id": inv_id,
        "agency_id": agency_id,
        "name": investigator_name,
        "role": role,
    }


def get_rls_policy_sql() -> list[str]:
    """Generate PostgreSQL RLS policy SQL for all tables."""
    tables = [
        "cases", "evidence_artifacts", "case_entities",
        "ingestion_audit_log", "memory_records",
        "investigation_actions", "osint_records",
    ]
    policies = []
    for table in tables:
        policies.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        policies.append(
            f"CREATE POLICY agency_isolation ON {table} "
            f"USING (agency_id = current_setting('app.current_agency_id')::uuid);"
        )
    return policies


def validate_agency_access(agency_id: str, case_id: str) -> dict:
    """Validate that an agency has access to a case."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})
        RETURN ca.agency_id AS agency_id
        """,
        {"cid": case_id},
    )
    if not result:
        return {"authorized": False, "reason": "Case not found"}

    case_agency = result[0].get("agency_id", "")
    if case_agency != agency_id:
        return {"authorized": False, "reason": "Access denied — case belongs to another agency"}

    return {"authorized": True}
