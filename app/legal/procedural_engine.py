"""Procedural Compliance Engine — verifies investigation procedural steps.

Checks BNSS 2023, BSA 2023, IT Act requirements. Section 65B BSA 2023
(electronic evidence certificate) is treated as a critical-level requirement.
"""

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

REQUIREMENTS_FILE = Path(__file__).parent / "procedural_requirements.json"


def load_requirements() -> list[dict]:
    """Load procedural requirements from seed file."""
    if REQUIREMENTS_FILE.exists():
        with open(REQUIREMENTS_FILE) as f:
            return json.load(f)
    return _default_requirements()


def scan_compliance(case_id: str, db: Optional[Session] = None) -> dict:
    """Run all applicable requirements for the case's crime category."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    requirements = load_requirements()

    # Get case crime categories
    categories = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS cat_id
        """,
        {"cid": case_id},
    )
    cat_ids = {c["cat_id"] for c in categories}

    results = []
    for req in requirements:
        applicable_cats = set(req.get("applicable_crime_categories", []))
        # Apply if categories match or requirement is universal (empty list)
        if applicable_cats and not applicable_cats.intersection(cat_ids) and cat_ids:
            continue

        status = _check_requirement(client, case_id, req)
        record_id = str(uuid.uuid4())

        # Create/update compliance record
        client.execute_write(
            """
            MERGE (r:ProceduralComplianceRecord {
                case_id: $cid, requirement_id: $rid
            })
            ON CREATE SET r.id = $nid, r.created_at = $now
            SET r.status = $status,
                r.verified_at = $now,
                r.verified_by = 'system:procedural_engine',
                r.non_compliance_severity = $severity,
                r.remediation_guidance = $guidance,
                r.classification_tag = 'case_sensitive'
            """,
            {
                "cid": case_id, "rid": req["requirement_id"],
                "nid": record_id, "now": now,
                "status": status,
                "severity": req.get("non_compliance_severity", "minor"),
                "guidance": req.get("remediation_guidance", ""),
            },
        )

        results.append({
            "requirement_id": req["requirement_id"],
            "title": req["title"],
            "required_by": req.get("required_by", ""),
            "status": status,
            "severity": req.get("non_compliance_severity", "minor"),
            "remediation_guidance": req.get("remediation_guidance", ""),
        })

    if db:
        non_compliant = sum(1 for r in results if r["status"] == "non_compliant")
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Procedural compliance scan: {non_compliant} non-compliant of {len(results)}",
            actor="system:procedural_engine",
        )
        db.commit()

    return {"case_id": case_id, "requirements_checked": len(results), "results": results}


def get_compliance_report(case_id: str) -> dict:
    """Return all requirements grouped by severity for non-compliant."""
    client = get_neo4j_client()

    records = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {case_id: $cid})
        RETURN r.requirement_id AS req_id, r.status AS status,
               r.non_compliance_severity AS severity,
               r.remediation_guidance AS guidance,
               r.verified_at AS verified_at
        """,
        {"cid": case_id},
    )

    requirements = {r["requirement_id"]: r for r in load_requirements()}

    compliant = []
    non_compliant_critical = []
    non_compliant_major = []
    non_compliant_minor = []
    pending = []

    for rec in records:
        req = requirements.get(rec["req_id"], {})
        entry = {
            "requirement_id": rec["req_id"],
            "title": req.get("title", ""),
            "required_by": req.get("required_by", ""),
            "status": rec["status"],
            "severity": rec.get("severity", "minor"),
            "remediation_guidance": rec.get("guidance", ""),
        }

        if rec["status"] == "compliant":
            compliant.append(entry)
        elif rec["status"] == "pending_manual_confirmation":
            pending.append(entry)
        elif rec.get("severity") == "critical":
            non_compliant_critical.append(entry)
        elif rec.get("severity") == "major":
            non_compliant_major.append(entry)
        else:
            non_compliant_minor.append(entry)

    return {
        "case_id": case_id,
        "compliant": compliant,
        "non_compliant_critical": non_compliant_critical,
        "non_compliant_major": non_compliant_major,
        "non_compliant_minor": non_compliant_minor,
        "pending_manual_confirmation": pending,
    }


def confirm_requirement(case_id: str, requirement_id: str,
                        confirmation_notes: str,
                        db: Optional[Session] = None) -> dict:
    """Investigator manually confirms a requirement."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MERGE (r:ProceduralComplianceRecord {case_id: $cid, requirement_id: $rid})
        ON CREATE SET r.id = $nid, r.created_at = $now, r.classification_tag = 'case_sensitive'
        SET r.status = 'compliant',
            r.verified_by = 'investigator',
            r.verified_at = $now,
            r.confirmation_notes = $notes
        """,
        {
            "cid": case_id,
            "rid": requirement_id,
            "nid": str(uuid.uuid4()),
            "now": now,
            "notes": confirmation_notes
        },
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Procedural requirement {requirement_id} confirmed: {confirmation_notes[:80]}",
            actor="system:procedural_engine",
        )
        db.commit()

    return {"requirement_id": requirement_id, "status": "compliant"}


def check_section_65b(case_id: str) -> dict:
    """
    Critical check: Section 65B BSA 2023 electronic evidence certificate.
    Returns alert dict if non-compliant, None if compliant.
    """
    client = get_neo4j_client()

    # Check for electronic evidence in the case
    electronic_evidence = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid
        AND (n.source_tool IS NOT NULL OR n.content_type IN
             ['communication_record', 'device_artifact', 'generic_file'])
        RETURN count(n) AS cnt
        """,
        {"cid": case_id},
    )

    has_electronic = electronic_evidence and electronic_evidence[0]["cnt"] > 0

    if not has_electronic:
        return {"status": "not_applicable", "alert": None}

    # Check if 65B certificate is confirmed
    cert = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {case_id: $cid, requirement_id: 'section_65b_bsa_2023'})
        RETURN r.status AS status
        """,
        {"cid": case_id},
    )

    if cert and cert[0]["status"] == "compliant":
        return {"status": "compliant", "alert": None}

    return {
        "status": "non_compliant",
        "alert": {
            "alert_type": "section_65b_non_compliance",
            "severity": "critical",
            "message": "Section 65B BSA 2023 certificate not confirmed — electronic "
                       "evidence may be inadmissible without it. This is a critical "
                       "procedural requirement that must be addressed before prosecution.",
        },
    }


def _check_requirement(client, case_id: str, req: dict) -> str:
    """Check a single requirement against the case."""
    method = req.get("verification_method", "manual_confirmation")

    if method == "manual_confirmation":
        # Check if already confirmed
        existing = client.execute_read(
            """
            MATCH (r:ProceduralComplianceRecord {case_id: $cid, requirement_id: $rid})
            WHERE r.status = 'compliant'
            RETURN count(r) AS cnt
            """,
            {"cid": case_id, "rid": req["requirement_id"]},
        )
        if existing and existing[0]["cnt"] > 0:
            return "compliant"
        return "pending_manual_confirmation"

    elif method == "artifact_presence":
        check = req.get("verification_check", "")
        result = client.execute_read(
            """
            MATCH (n)
            WHERE n.case_id = $cid
            AND (n.source_tool = $check OR n.content_type = $check
                 OR n.artifact_type = $check)
            RETURN count(n) AS cnt
            """,
            {"cid": case_id, "check": check},
        )
        if result and result[0]["cnt"] > 0:
            return "compliant"
        return "non_compliant"

    elif method == "graph_assertion":
        # Check for the described graph pattern
        check_desc = req.get("verification_check", "")
        # For chain_of_custody: check all artifacts have intact chains
        if "chain_of_custody" in check_desc:
            broken = client.execute_read(
                """
                MATCH (n)
                WHERE n.case_id = $cid AND n.hash_verified = false
                RETURN count(n) AS cnt
                """,
                {"cid": case_id},
            )
            if broken and broken[0]["cnt"] > 0:
                return "non_compliant"
            return "compliant"
        return "pending_manual_confirmation"

    return "pending_manual_confirmation"


def _default_requirements() -> list[dict]:
    """Default procedural requirements if JSON seed not found."""
    return [
        {
            "requirement_id": "section_65b_bsa_2023",
            "title": "Section 65B BSA 2023 Certificate for Electronic Evidence",
            "description": "Electronic evidence requires a certificate under Section 65B "
                           "of the Bharatiya Sakshya Adhiniyam 2023 for admissibility.",
            "applicable_crime_categories": [],
            "required_by": "BSA_2023_Section_65B",
            "verification_method": "manual_confirmation",
            "verification_check": "",
            "non_compliance_severity": "critical",
            "remediation_guidance": "Obtain Section 65B certificate from the person "
                                    "responsible for the computer/device producing the evidence.",
        },
        {
            "requirement_id": "bnss_94_seizure_documentation",
            "title": "Digital Evidence Seizure Documentation (BNSS Section 94)",
            "description": "Seizure of digital evidence must be documented per BNSS Section 94.",
            "applicable_crime_categories": [],
            "required_by": "BNSS_2023_Section_94",
            "verification_method": "artifact_presence",
            "verification_check": "seizure_memo",
            "non_compliance_severity": "major",
            "remediation_guidance": "Prepare and attach seizure memo documenting date, time, "
                                    "location, witnesses, and description of seized items.",
        },
        {
            "requirement_id": "chain_of_custody_completeness",
            "title": "Chain of Custody Completeness",
            "description": "All evidence must have an unbroken chain of custody.",
            "applicable_crime_categories": [],
            "required_by": "BSA_2023_General",
            "verification_method": "graph_assertion",
            "verification_check": "chain_of_custody",
            "non_compliance_severity": "critical",
            "remediation_guidance": "Review chain of custody log for all evidence artifacts. "
                                    "Any gap must be documented with witness statements.",
        },
        {
            "requirement_id": "preservation_order",
            "title": "Data Preservation Orders",
            "description": "Preservation orders must be issued to service providers "
                           "to prevent data destruction.",
            "applicable_crime_categories": [],
            "required_by": "IT_Act_2000_Section_67C",
            "verification_method": "manual_confirmation",
            "verification_check": "",
            "non_compliance_severity": "major",
            "remediation_guidance": "Issue preservation orders to all relevant service "
                                    "providers (ISPs, social media, email).",
        },
    ]


def get_procedural_timeline(case_id: str, db: Session) -> dict:
    """
    Generate a timeline of procedural milestones with deadlines and compliance status.
    Calculates dynamic deadlines based on case registration and arrest timestamps.
    """
    client = get_neo4j_client()

    # 1. Fetch case details from Postgres
    from app.db.models import Case
    import uuid as pyuuid
    case = db.query(Case).filter(Case.case_id == pyuuid.UUID(case_id)).first()
    if not case:
        return {"error": "Case not found"}

    case_created_at = case.created_at

    # 2. Fetch arrest timestamp from Neo4j (if any)
    # Search for an Event of type 'arrest' or Person with arrest_timestamp
    arrest_data = client.execute_read(
        """
        MATCH (e:Event {case_id: $cid})
        WHERE e.event_type = 'arrest' OR e.event_type = 'arrest_event'
        RETURN e.valid_from AS arrest_time
        LIMIT 1
        """,
        {"cid": case_id}
    )

    arrest_time_str = None
    if arrest_data and arrest_data[0]["arrest_time"]:
        arrest_time_str = arrest_data[0]["arrest_time"]
    else:
        # Fallback search on Person status
        person_arrest = client.execute_read(
            """
            MATCH (p:Person {case_id: $cid})
            WHERE p.status = 'arrested' AND p.arrest_timestamp IS NOT NULL
            RETURN p.arrest_timestamp AS arrest_time
            LIMIT 1
            """,
            {"cid": case_id}
        )
        if person_arrest and person_arrest[0]["arrest_time"]:
            arrest_time_str = person_arrest[0]["arrest_time"]

    arrest_time = None
    if arrest_time_str:
        try:
            arrest_time = datetime.fromisoformat(str(arrest_time_str).replace("Z", "+00:00"))
        except Exception:
            pass

    # 3. Load all requirements
    requirements = load_requirements()

    # 4. Load compliance records from Neo4j
    records = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {case_id: $cid})
        RETURN r.requirement_id AS req_id, r.status AS status,
               r.verified_at AS verified_at, r.verified_by AS verified_by,
               r.confirmation_notes AS notes
        """,
        {"cid": case_id}
    )
    compliance_map = {r["req_id"]: r for r in records}

    # 5. Build timeline entries
    timeline = []
    now = datetime.now(timezone.utc)

    for req in requirements:
        req_id = req["requirement_id"]
        comp_rec = compliance_map.get(req_id, {})
        status = comp_rec.get("status", "pending_manual_confirmation")

        # Calculate deadline
        deadline = None
        days_remaining = None
        hours_remaining = None
        is_overdue = False

        if "deadline_days" in req:
            # Case-relative or arrest-relative
            base_time = case_created_at
            if req_id == "chargesheet_filing_bnss_193" and arrest_time:
                base_time = arrest_time

            deadline = base_time + timedelta(days=req["deadline_days"])
            diff = deadline - now
            days_remaining = round(diff.total_seconds() / 86400.0, 1)
            is_overdue = diff.total_seconds() < 0 and status != "compliant"

        elif "deadline_hours" in req and arrest_time:
            deadline = arrest_time + timedelta(hours=req["deadline_hours"])
            diff = deadline - now
            hours_remaining = round(diff.total_seconds() / 3600.0, 1)
            is_overdue = diff.total_seconds() < 0 and status != "compliant"

        timeline.append({
            "requirement_id": req_id,
            "title": req["title"],
            "required_by": req.get("required_by", ""),
            "status": status,
            "severity": req.get("non_compliance_severity", "minor"),
            "remediation_guidance": req.get("remediation_guidance", ""),
            "deadline": deadline.isoformat() if deadline else None,
            "days_remaining": days_remaining,
            "hours_remaining": hours_remaining,
            "is_overdue": is_overdue,
            "verified_at": comp_rec.get("verified_at"),
            "verified_by": comp_rec.get("verified_by"),
            "notes": comp_rec.get("notes"),
        })

    return {
        "case_id": case_id,
        "case_created_at": case_created_at.isoformat(),
        "arrest_timestamp": arrest_time.isoformat() if arrest_time else None,
        "timeline": timeline,
        "disclaimer": "Advisory only. Procedural compliance monitoring is designed for investigator support and does not constitute formal legal opinion."
    }


def generate_compliance_alerts(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate deadline alerts for upcoming, urgent, and overdue procedural requirements.

    Returns alerts categorized as:
      - blocking: overdue critical requirements (could invalidate evidence or cause default bail)
      - urgent: overdue major/due within 1 day
      - upcoming: due within 7 days
    """
    timeline_data = get_procedural_timeline(case_id, db)
    timeline = timeline_data.get("timeline", [])

    blocking = []
    urgent = []
    upcoming = []

    for item in timeline:
        status = item.get("status", "")
        if status == "compliant":
            continue

        severity = item.get("severity", "minor")
        is_overdue = item.get("is_overdue", False)
        days_remaining = item.get("days_remaining")
        hours_remaining = item.get("hours_remaining")

        alert = {
            "requirement_id": item["requirement_id"],
            "title": item["title"],
            "required_by": item.get("required_by", ""),
            "severity": severity,
            "deadline": item.get("deadline"),
            "remediation_guidance": item.get("remediation_guidance", ""),
        }

        if is_overdue and severity == "critical":
            alert["alert_level"] = "blocking"
            alert["message"] = (
                f"BLOCKING: {item['title']} is OVERDUE. "
                f"This critical requirement may invalidate evidence or trigger default bail. "
                f"Immediate action required."
            )
            blocking.append(alert)
        elif is_overdue or (days_remaining is not None and 0 <= days_remaining <= 1) or \
             (hours_remaining is not None and 0 <= hours_remaining <= 24):
            alert["alert_level"] = "urgent"
            if is_overdue:
                alert["message"] = (
                    f"URGENT: {item['title']} is OVERDUE. "
                    f"Address immediately to maintain procedural compliance."
                )
            else:
                remaining = (f"{days_remaining:.0f} day(s)" if days_remaining is not None
                             else f"{hours_remaining:.0f} hour(s)")
                alert["message"] = (
                    f"URGENT: {item['title']} due in {remaining}. "
                    f"Complete this requirement to avoid non-compliance."
                )
            urgent.append(alert)
        elif (days_remaining is not None and days_remaining <= 7) or \
             (hours_remaining is not None and hours_remaining <= 168):
            remaining = (f"{days_remaining:.0f} day(s)" if days_remaining is not None
                         else f"{hours_remaining:.0f} hour(s)")
            alert["alert_level"] = "upcoming"
            alert["message"] = (
                f"UPCOMING: {item['title']} due in {remaining}. "
                f"Plan to address before deadline."
            )
            upcoming.append(alert)
        elif status == "non_compliant" and not item.get("deadline"):
            # No deadline but non-compliant — treat as upcoming
            alert["alert_level"] = "upcoming"
            alert["message"] = (
                f"PENDING: {item['title']} has not been completed. "
                f"Complete at earliest opportunity."
            )
            upcoming.append(alert)

    return {
        "case_id": case_id,
        "total_alerts": len(blocking) + len(urgent) + len(upcoming),
        "blocking": blocking,
        "urgent": urgent,
        "upcoming": upcoming,
        "disclaimer": "Advisory only. Deadline calculations are automated estimates and should be verified against official records.",
    }
