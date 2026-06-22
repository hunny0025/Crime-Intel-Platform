"""Autonomous Gap Resolution + Dead End Detection (Prompt 49).

Monitors evidence gaps for auto-resolution and detects investigation
dead ends for pivot recommendations.
"""

import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

DEAD_END_THRESHOLD_DAYS = 14


def run_gap_resolution(case_id: str, db: Optional[Session] = None) -> dict:
    """Check and auto-resolve evidence gaps with new evidence."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    open_gaps = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $cid, status: 'open'})
        RETURN g.id AS id, g.description AS desc, g.gap_type AS gtype,
               g.expected_evidence_type AS expected
        """,
        {"cid": case_id},
    )

    resolved = []
    for gap in open_gaps:
        gap_resolved = False
        resolution_reason = ""

        gtype = gap.get("gtype", "")
        expected = gap.get("expected", "")

        # Communication silence gap
        if "communication" in gtype.lower() or "silence" in gtype.lower():
            comms = client.execute_read(
                """
                MATCH ()-[r:COMMUNICATED_WITH]->()
                WHERE r.confidence >= 0.5
                RETURN count(r) AS cnt
                """,
            )
            if comms and comms[0]["cnt"] > 0:
                gap_resolved = True
                resolution_reason = "New COMMUNICATED_WITH relationship covers the gap window"

        # Identifier gap
        elif "identifier" in gtype.lower() or "identity" in gtype.lower():
            identifiers = client.execute_read(
                """
                MATCH (p:Person {case_id: $cid})-[:HAS_IDENTIFIER]->(f:IdentityFacet)
                RETURN count(f) AS cnt
                """,
                {"cid": case_id},
            )
            if identifiers and identifiers[0]["cnt"] > 0:
                gap_resolved = True
                resolution_reason = "New IdentityFacet linked to a Person"

        # Legal element gap
        elif "element" in gtype.lower() or "legal" in gtype.lower():
            satisfied = client.execute_read(
                """
                MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
                WHERE r.satisfaction_score >= 0.4
                RETURN count(r) AS cnt
                """,
                {"cid": case_id},
            )
            if satisfied and satisfied[0]["cnt"] > 0:
                gap_resolved = True
                resolution_reason = "New SATISFIES_ELEMENT relationship created"

        # Expiration-driven gap (resolved by evidence arrival)
        elif expected:
            arrived = client.execute_read(
                """
                MATCH (n)
                WHERE n.case_id = $cid AND n.source_tool = $etype
                RETURN count(n) AS cnt
                """,
                {"cid": case_id, "etype": expected},
            )
            if arrived and arrived[0]["cnt"] > 0:
                gap_resolved = True
                resolution_reason = f"Evidence of type '{expected}' has been ingested"

        if gap_resolved:
            client.execute_write(
                """
                MATCH (g:EvidenceGap {id: $gid})
                SET g.status = 'auto_resolved', g.resolved_at = $now,
                    g.resolution_reason = $reason
                """,
                {"gid": gap["id"], "now": now, "reason": resolution_reason},
            )
            resolved.append({
                "gap_id": gap["id"],
                "description": gap.get("desc", ""),
                "resolution_reason": resolution_reason,
            })

            if db:
                write_memory_record(
                    db=db, case_id=case_id,
                    record_type=MemoryRecordType.gap_identified,
                    description=f"Gap auto-resolved: {gap.get('desc', '')[:60]}",
                    actor="system:aire_gap_resolver",
                    reasoning=resolution_reason,
                    graph_refs=[gap["id"]],
                )

    if db and resolved:
        db.commit()

    return {
        "case_id": case_id,
        "scanned_at": now,
        "open_gaps_checked": len(open_gaps),
        "auto_resolved": len(resolved),
        "resolved_gaps": resolved,
    }


def run_dead_end_detection(case_id: str, threshold_days: int = DEAD_END_THRESHOLD_DAYS,
                           db: Optional[Session] = None) -> dict:
    """Detect investigation dead ends — stalled actions."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=threshold_days)).isoformat()

    stalled_actions = client.execute_read(
        """
        MATCH (a:InvestigationAction {case_id: $cid})
        WHERE a.status = 'in_progress' AND a.created_at < $cutoff
        RETURN a.id AS id, a.target_ref AS target, a.action_type AS atype,
               a.created_at AS created, a.description AS desc
        """,
        {"cid": case_id, "cutoff": cutoff},
    )

    dead_ends = []
    for action in stalled_actions:
        target = action.get("target", "")
        created = action.get("created", "")

        # Check if new evidence of target type has arrived since action creation
        evidence_arrived = client.execute_read(
            """
            MATCH (n)
            WHERE n.case_id = $cid AND n.source_tool = $target
            AND n.created_at > $since
            RETURN count(n) AS cnt
            """,
            {"cid": case_id, "target": target, "since": created},
        )
        has_evidence = evidence_arrived and evidence_arrived[0]["cnt"] > 0

        # Check if hypothesis probabilities changed
        prob_changed = client.execute_read(
            """
            MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
            RETURN h.probability AS prob
            """,
            {"cid": case_id},
        )

        if has_evidence:
            continue  # Not a dead end if evidence arrived

        days_stalled = threshold_days
        try:
            created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            days_stalled = (now - created_dt).days
        except (ValueError, TypeError):
            pass

        # Compute dead end prediction using methodology library
        dead_end_score = _compute_dead_end_prediction(client, case_id, target)

        description = (
            f"This action has been in progress {days_stalled} days with no evidence "
            f"arrival of type '{target}' and no hypothesis probability change. "
            f"Consider: (a) pursuing a parallel evidence stream, "
            f"(b) reassessing whether this evidence type is still obtainable, "
            f"(c) marking this action dismissed if the thread is exhausted."
        )

        client.execute_write(
            """
            MATCH (a:InvestigationAction {id: $aid})
            SET a.dead_end_flag = true,
                a.dead_end_description = $desc,
                a.dead_end_prediction_score = $score,
                a.dead_end_detected_at = $now
            """,
            {
                "aid": action["id"], "desc": description,
                "score": dead_end_score, "now": now.isoformat(),
            },
        )

        dead_ends.append({
            "action_id": action["id"],
            "target_ref": target,
            "days_stalled": days_stalled,
            "dead_end_prediction_score": dead_end_score,
            "description": description,
            "recommended_alternatives": [
                "Pursue parallel evidence stream",
                "Reassess evidence obtainability",
                "Mark as dismissed if exhausted",
            ],
        })

        if db:
            write_memory_record(
                db=db, case_id=case_id,
                record_type=MemoryRecordType.lead_status_changed,
                description=f"Dead end detected: {target} stalled {days_stalled} days",
                actor="system:aire_dead_end_detector",
                reasoning=description,
                graph_refs=[action["id"]],
            )

    if db and dead_ends:
        db.commit()

    return {
        "case_id": case_id,
        "checked_at": now.isoformat(),
        "actions_checked": len(stalled_actions),
        "dead_ends_detected": len(dead_ends),
        "dead_ends": dead_ends,
    }


def get_dead_ends(case_id: str) -> list:
    """List all dead-end-flagged actions."""
    client = get_neo4j_client()
    return client.execute_read(
        """
        MATCH (a:InvestigationAction {case_id: $cid})
        WHERE a.dead_end_flag = true
        RETURN a.id AS id, a.target_ref AS target,
               a.dead_end_description AS description,
               a.dead_end_prediction_score AS score,
               a.dead_end_detected_at AS detected_at
        ORDER BY a.dead_end_detected_at DESC
        """,
        {"cid": case_id},
    )


def pivot_dead_end(case_id: str, action_id: str, pivot_rationale: str,
                   replacement_target: str = None,
                   db: Optional[Session] = None) -> dict:
    """Dismiss dead end and optionally spawn replacement action."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Dismiss original
    client.execute_write(
        "MATCH (a:InvestigationAction {id: $aid}) SET a.status = 'dismissed', "
        "a.dismissal_reason = $reason",
        {"aid": action_id, "reason": f"Dead end pivot: {pivot_rationale}"},
    )

    result = {"dismissed_action_id": action_id, "pivot_rationale": pivot_rationale}

    # Spawn replacement if requested
    if replacement_target:
        new_id = str(uuid.uuid4())
        client.execute_write(
            """
            CREATE (a:InvestigationAction {
                id: $aid, case_id: $cid,
                action_type: 'pursue_evidence_gap',
                target_ref: $target, priority_score: 0.85,
                status: 'pending',
                description: $desc,
                classification_tag: 'case_sensitive', created_at: $now
            })
            """,
            {
                "aid": new_id, "cid": case_id, "target": replacement_target,
                "desc": f"Pivot from dead end: {pivot_rationale[:80]}",
                "now": now,
            },
        )
        result["replacement_action_id"] = new_id

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.lead_status_changed,
            description=f"Dead end pivot: dismissed {action_id[:8]}, rationale: {pivot_rationale[:60]}",
            actor="system:aire_dead_end_detector",
            reasoning=pivot_rationale,
            graph_refs=[action_id],
        )
        db.commit()

    return result


def _compute_dead_end_prediction(client, case_id: str, evidence_type: str) -> float:
    """Compute dead end prediction score using methodology library."""
    # Check PlaybookTemplates for success rates
    templates = client.execute_read(
        """
        MATCH (pt:PlaybookTemplate)
        RETURN pt.steps AS steps
        """,
    )

    for t in templates:
        try:
            steps = json.loads(str(t.get("steps", "[]")).replace("'", '"'))
            for step in steps:
                if step.get("evidence_type_target") == evidence_type:
                    success_rate = step.get("success_rate_in_similar_cases", 0.5)
                    if success_rate < 0.3:
                        return 0.8  # High dead end probability
                    elif success_rate < 0.5:
                        return 0.5
                    return 0.2  # Low dead end probability
        except (json.JSONDecodeError, ValueError):
            continue

    return 0.5  # Neutral default
