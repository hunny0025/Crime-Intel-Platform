"""Autonomous Evidence Expiration Model + Preservation Alerting (Prompt 47).

Proactively identifies evidence at risk of expiring based on known
retention windows and initiates preservation actions.
"""

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

RETENTION_FILE = Path(__file__).parent.parent / "config" / "retention_windows.json"


def load_retention_windows() -> dict:
    """Load evidence type retention windows."""
    if RETENTION_FILE.exists():
        with open(RETENTION_FILE) as f:
            windows = json.load(f)
        return {w["evidence_type"]: w for w in windows}
    return {}


def compute_expiration_map(case_id: str, incident_date: str = None) -> dict:
    """Compute EvidenceExpirationMap for a case."""
    client = get_neo4j_client()
    windows = load_retention_windows()
    now = datetime.now(timezone.utc)

    # Get incident date from case
    if not incident_date:
        case_info = client.execute_read(
            "MATCH (ca:CaseAnchor {case_id: $cid}) RETURN ca.created_at AS created",
            {"cid": case_id},
        )
        if case_info and case_info[0].get("created"):
            try:
                incident_date = str(case_info[0]["created"])
            except Exception:
                incident_date = now.isoformat()
        else:
            incident_date = now.isoformat()

    try:
        inc_dt = datetime.fromisoformat(incident_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        inc_dt = now

    # Get implied evidence types from active hypotheses
    implied_types = set()
    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.implied_evidence AS implied
        """,
        {"cid": case_id},
    )
    for h in hypotheses:
        if h.get("implied"):
            try:
                items = json.loads(str(h["implied"]).replace("'", '"'))
                for item in items:
                    if isinstance(item, dict):
                        implied_types.add(item.get("evidence_type", ""))
                    elif isinstance(item, str):
                        implied_types.add(item)
            except (json.JSONDecodeError, ValueError):
                pass

    # Add common evidence types
    implied_types.update(["telecom_cdr", "cell_tower_ping", "cctv_footage"])

    # Check which types have NOT been obtained
    obtained = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN DISTINCT n.source_tool AS tool
        """,
        {"cid": case_id},
    )
    obtained_types = {o["tool"] for o in obtained}

    expiration_entries = []
    for etype in implied_types:
        if etype in obtained_types or not etype:
            continue

        window = windows.get(etype)
        if not window or window.get("retention_days") is None:
            expiration_entries.append({
                "evidence_type": etype,
                "retention_days": None,
                "earliest_possible_expiry": None,
                "days_until_expiry": None,
                "urgency": "unknown",
                "confidence": "low",
                "verify_with_legal_team": True,
            })
            continue

        retention_days = window["retention_days"]
        expiry = inc_dt + timedelta(days=retention_days)
        days_until = (expiry - now).days

        if days_until <= 7:
            urgency = "critical"
        elif days_until <= 30:
            urgency = "high"
        elif days_until <= 90:
            urgency = "medium"
        else:
            urgency = "low"

        expiration_entries.append({
            "evidence_type": etype,
            "retention_days": retention_days,
            "regulation": window.get("regulation", ""),
            "earliest_possible_expiry": expiry.isoformat(),
            "days_until_expiry": days_until,
            "urgency": urgency,
            "confidence": window.get("confidence", "medium"),
            "verify_with_legal_team": window.get("verify_with_legal_team", True),
        })

    return {
        "case_id": case_id,
        "incident_date": incident_date,
        "scanned_at": now.isoformat(),
        "entries": expiration_entries,
    }


def run_expiration_scan(case_id: str, incident_date: str = None,
                        db: Optional[Session] = None) -> dict:
    """Run expiration scan and create preservation actions."""
    exp_map = compute_expiration_map(case_id, incident_date)
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    actions_created = 0
    alerts = []

    for entry in exp_map["entries"]:
        urgency = entry.get("urgency", "low")
        if urgency not in ("critical", "high"):
            continue

        etype = entry["evidence_type"]
        days = entry.get("days_until_expiry", "unknown")
        priority = 1.0 if urgency == "critical" else 0.95

        # Check if action already exists
        existing = client.execute_read(
            """
            MATCH (a:InvestigationAction {case_id: $cid})
            WHERE a.target_ref = $etype AND a.status IN ['pending', 'in_progress']
            RETURN count(a) AS cnt
            """,
            {"cid": case_id, "etype": etype},
        )
        if existing and existing[0]["cnt"] > 0:
            continue

        action_id = str(uuid.uuid4())
        client.execute_write(
            """
            CREATE (a:InvestigationAction {
                id: $aid, case_id: $cid,
                action_type: 'pursue_evidence_gap',
                target_ref: $etype,
                priority_score: $priority,
                status: 'pending',
                description: $desc,
                urgency: $urgency,
                time_critical: true,
                classification_tag: 'case_sensitive',
                created_at: $now
            })
            """,
            {
                "aid": action_id, "cid": case_id, "etype": etype,
                "priority": priority, "urgency": urgency,
                "desc": f"TIME_CRITICAL: Evidence type '{etype}' expires in {days} days. "
                        f"Preservation request should be initiated immediately.",
                "now": now,
            },
        )
        actions_created += 1

        alert = {
            "alert_type": "TIME_CRITICAL",
            "evidence_type": etype,
            "days_until_expiry": days,
            "urgency": urgency,
            "message": f"Evidence type '{etype}' expires in {days} days — "
                       f"preservation request required immediately.",
        }
        alerts.append(alert)

        if db:
            write_memory_record(
                db=db, case_id=case_id,
                record_type=MemoryRecordType.gap_identified,
                description=f"Evidence type '{etype}' expires in {days} days",
                actor="system:aire_expiration_monitor",
                reasoning=f"Retention window analysis: {etype} has {days} days remaining. "
                          f"Urgency: {urgency}. Preservation request should be initiated.",
            )

    if db:
        db.commit()

    exp_map["actions_created"] = actions_created
    exp_map["time_critical_alerts"] = alerts
    return exp_map
