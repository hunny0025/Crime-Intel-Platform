"""Investigation Playbook Engine — recommended investigation sequences.

Extracts playbook steps from historical case patterns and annotates
current case progress against the recommended sequence.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def get_playbook_template(crime_category_id: str) -> dict:
    """Get or generate PlaybookTemplate for a crime category."""
    client = get_neo4j_client()

    # Check for existing template
    existing = client.execute_read(
        """
        MATCH (pt:PlaybookTemplate {crime_category_id: $cat})
        RETURN pt.id AS id, pt.steps AS steps,
               pt.derived_from_case_count AS case_count,
               pt.outcome_stats AS stats
        ORDER BY pt.last_updated DESC LIMIT 1
        """,
        {"cat": crime_category_id},
    )

    if existing and existing[0].get("steps"):
        steps = json.loads(existing[0]["steps"].replace("'", '"')) \
            if isinstance(existing[0]["steps"], str) else existing[0]["steps"]
        stats = json.loads(existing[0].get("stats", "{}").replace("'", '"')) \
            if isinstance(existing[0].get("stats"), str) else existing[0].get("stats", {})
        return {
            "template_id": existing[0]["id"],
            "crime_category_id": crime_category_id,
            "steps": steps,
            "derived_from_case_count": existing[0].get("case_count", 0),
            "outcome_stats": stats,
        }

    # Generate default playbook from crime category patterns
    return _generate_default_playbook(client, crime_category_id)


def get_recommended_playbook(case_id: str) -> dict:
    """Annotate playbook with current case progress."""
    client = get_neo4j_client()

    # Get case crime category
    cats = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS cat_id
        """,
        {"cid": case_id},
    )

    if not cats:
        return {"error": "No crime category assigned to case"}

    template = get_playbook_template(cats[0]["cat_id"])
    steps = template.get("steps", [])

    # Check completion status for each step
    for step in steps:
        step["status"] = _check_step_completion(client, case_id, step)

    completed = sum(1 for s in steps if s["status"] == "completed")
    total = len(steps)

    # Next uncompleted high-priority step
    next_step = None
    for s in steps:
        if s["status"] == "pending":
            next_step = s
            break

    return {
        "case_id": case_id,
        "template_id": template.get("template_id"),
        "steps": steps,
        "progress": f"{completed}/{total}",
        "progress_fraction": completed / total if total > 0 else 0,
        "next_priority_step": next_step,
    }


def complete_playbook_step(case_id: str, step_number: int,
                           db: Optional[Session] = None) -> dict:
    """Mark a playbook step as completed."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Store completion
    client.execute_write(
        """
        MERGE (ps:PlaybookStepCompletion {case_id: $cid, step_number: $sn})
        SET ps.completed_at = $now, ps.status = 'completed'
        """,
        {"cid": case_id, "sn": step_number, "now": now},
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.lead_pursued,
            description=f"Playbook step {step_number} completed",
            actor="system:playbook_engine",
        )
        db.commit()

    return {"step_number": step_number, "status": "completed"}


def _check_step_completion(client, case_id: str, step: dict) -> str:
    """Check if a playbook step is completed for this case."""
    completion = client.execute_read(
        """
        MATCH (ps:PlaybookStepCompletion {case_id: $cid, step_number: $sn})
        RETURN ps.status AS status
        """,
        {"cid": case_id, "sn": step.get("step_number", 0)},
    )
    if completion and completion[0].get("status") == "completed":
        return "completed"

    # Auto-detect completion based on evidence presence
    evidence_type = step.get("evidence_type_target", "")
    if evidence_type:
        has_evidence = client.execute_read(
            """
            MATCH (n)
            WHERE n.case_id = $cid
            AND (n.source_tool = $etype OR n.content_type = $etype
                 OR n.event_type = $etype)
            RETURN count(n) AS cnt
            """,
            {"cid": case_id, "etype": evidence_type},
        )
        if has_evidence and has_evidence[0]["cnt"] > 0:
            return "completed"

    return "pending"


def _generate_default_playbook(client, crime_category_id: str) -> dict:
    """Generate a default playbook from crime category."""
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Default investigation sequence
    default_steps = [
        {
            "step_number": 1,
            "action_type": "collect_digital_evidence",
            "evidence_type_target": "device_artifact",
            "rationale": "Secure and preserve digital devices before evidence is destroyed",
            "success_rate_in_similar_cases": 0.9,
            "common_failure_modes": ["device encrypted", "remote wipe triggered"],
        },
        {
            "step_number": 2,
            "action_type": "obtain_communication_records",
            "evidence_type_target": "communication_record",
            "rationale": "CDR/IP logs establish communication patterns and timelines",
            "success_rate_in_similar_cases": 0.85,
            "common_failure_modes": ["data retention period expired", "VPN usage"],
        },
        {
            "step_number": 3,
            "action_type": "obtain_financial_records",
            "evidence_type_target": "financial_record",
            "rationale": "Follow the money to establish motive and trace fund flows",
            "success_rate_in_similar_cases": 0.75,
            "common_failure_modes": ["cryptocurrency mixing", "offshore accounts"],
        },
        {
            "step_number": 4,
            "action_type": "location_verification",
            "evidence_type_target": "gps_record",
            "rationale": "Corroborate physical presence claims with location data",
            "success_rate_in_similar_cases": 0.7,
            "common_failure_modes": ["location services disabled", "device not carried"],
        },
        {
            "step_number": 5,
            "action_type": "witness_documentation",
            "evidence_type_target": "witness_statement",
            "rationale": "Corroborate digital evidence with witness testimony",
            "success_rate_in_similar_cases": 0.65,
            "common_failure_modes": ["witness unavailable", "conflicting statements"],
        },
    ]

    # Store template
    client.execute_write(
        """
        CREATE (pt:PlaybookTemplate {
            id: $tid, crime_category_id: $cat,
            derived_from_case_count: 0,
            steps: $steps,
            outcome_stats: $stats,
            created_at: $now, last_updated: $now
        })
        """,
        {
            "tid": template_id, "cat": crime_category_id,
            "steps": json.dumps(default_steps),
            "stats": json.dumps({"note": "default template"}),
            "now": now,
        },
    )

    return {
        "template_id": template_id,
        "crime_category_id": crime_category_id,
        "steps": default_steps,
        "derived_from_case_count": 0,
        "outcome_stats": {"note": "default template"},
    }
