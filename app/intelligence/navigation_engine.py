"""Investigation Navigation Engine — synthesizes engine outputs into a ranked action queue.

Creates InvestigationAction records from Contradictions, EvidenceGaps,
and high-attention entities. Provides status transition + memory recording.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import (
    InvestigationAction, ActionType, ActionStatus, MemoryRecordType,
)
from app.memory.writer import write_memory_record

logger = logging.getLogger(__name__)

# Priority score mappings
SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
VALUE_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
URGENCY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}

# Attention threshold for creating review actions
ATTENTION_THRESHOLD = 0.5


def create_action_for_contradiction(
    db: Session,
    case_id: str,
    contradiction_id: str,
    severity: str,
) -> InvestigationAction:
    """Create an InvestigationAction for a detected contradiction."""
    priority = SEVERITY_WEIGHT.get(severity, 0.3)

    # Check for existing pending action targeting this contradiction
    existing = db.query(InvestigationAction).filter(
        InvestigationAction.case_id == uuid.UUID(case_id),
        InvestigationAction.target_ref == contradiction_id,
        InvestigationAction.status == ActionStatus.pending,
    ).first()
    if existing:
        return existing

    action = InvestigationAction(
        action_id=uuid.uuid4(),
        case_id=uuid.UUID(case_id),
        action_type=ActionType.review_contradiction,
        target_ref=contradiction_id,
        priority_score=priority,
        status=ActionStatus.pending,
    )
    db.add(action)
    db.flush()

    write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType.lead_pursued,
        description=f"Action created: review contradiction {contradiction_id} (priority={priority:.2f})",
        actor="system:navigation_engine",
        graph_refs=[contradiction_id],
    )

    logger.info("Action created: review_contradiction %s (priority=%.2f)", contradiction_id, priority)
    return action


def create_action_for_gap(
    db: Session,
    case_id: str,
    gap_id: str,
    expected_value: str,
    urgency: str,
) -> InvestigationAction:
    """Create an InvestigationAction for a detected evidence gap."""
    priority = VALUE_WEIGHT.get(expected_value, 0.3) * URGENCY_WEIGHT.get(urgency, 0.3)

    existing = db.query(InvestigationAction).filter(
        InvestigationAction.case_id == uuid.UUID(case_id),
        InvestigationAction.target_ref == gap_id,
        InvestigationAction.status == ActionStatus.pending,
    ).first()
    if existing:
        return existing

    action = InvestigationAction(
        action_id=uuid.uuid4(),
        case_id=uuid.UUID(case_id),
        action_type=ActionType.pursue_evidence_gap,
        target_ref=gap_id,
        priority_score=priority,
        status=ActionStatus.pending,
    )
    db.add(action)
    db.flush()

    write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType.lead_pursued,
        description=f"Action created: pursue evidence gap {gap_id} (priority={priority:.2f})",
        actor="system:navigation_engine",
        graph_refs=[gap_id],
    )

    logger.info("Action created: pursue_evidence_gap %s (priority=%.2f)", gap_id, priority)
    return action


def create_action_for_attention(
    db: Session,
    case_id: str,
    node_id: str,
    attention_value: float,
) -> Optional[InvestigationAction]:
    """Create an InvestigationAction for a high-attention entity (if above threshold)."""
    if attention_value <= ATTENTION_THRESHOLD:
        return None

    # Don't duplicate
    existing = db.query(InvestigationAction).filter(
        InvestigationAction.case_id == uuid.UUID(case_id),
        InvestigationAction.target_ref == node_id,
        InvestigationAction.action_type == ActionType.review_high_attention_entity,
        InvestigationAction.status == ActionStatus.pending,
    ).first()
    if existing:
        # Update priority if it changed significantly
        if abs(existing.priority_score - attention_value) > 0.1:
            existing.priority_score = attention_value
            db.flush()
        return existing

    action = InvestigationAction(
        action_id=uuid.uuid4(),
        case_id=uuid.UUID(case_id),
        action_type=ActionType.review_high_attention_entity,
        target_ref=node_id,
        priority_score=attention_value,
        status=ActionStatus.pending,
    )
    db.add(action)
    db.flush()
    return action


def transition_action_status(
    db: Session,
    case_id: str,
    action_id: str,
    new_status: ActionStatus,
    dismissal_reason: Optional[str] = None,
) -> InvestigationAction:
    """Transition an action's status. Writes a memory record for each transition."""
    action = db.query(InvestigationAction).filter(
        InvestigationAction.action_id == uuid.UUID(action_id),
        InvestigationAction.case_id == uuid.UUID(case_id),
    ).first()
    if not action:
        raise ValueError(f"Action {action_id} not found")

    old_status = action.status
    action.status = new_status
    action.status_updated_at = datetime.now(timezone.utc)

    if new_status == ActionStatus.dismissed:
        if not dismissal_reason:
            raise ValueError("dismissal_reason required when dismissing")
        action.dismissal_reason = dismissal_reason

    db.flush()

    write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType.lead_status_changed,
        description=f"Action {action_id} status: {old_status.value} → {new_status.value}",
        actor="system:navigation_engine",
        graph_refs=[action.target_ref],
        reasoning=dismissal_reason,
    )

    return action


def get_action_queue(
    db: Session,
    case_id: str,
    status_filter: str = "pending",
) -> list[dict]:
    """List actions sorted by priority_score descending."""
    query = db.query(InvestigationAction).filter(
        InvestigationAction.case_id == uuid.UUID(case_id),
    )
    if status_filter:
        query = query.filter(InvestigationAction.status == ActionStatus(status_filter))

    actions = query.order_by(InvestigationAction.priority_score.desc()).all()

    return [
        {
            "action_id": str(a.action_id),
            "case_id": str(a.case_id),
            "action_type": a.action_type.value,
            "target_ref": a.target_ref,
            "priority_score": a.priority_score,
            "status": a.status.value,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "status_updated_at": a.status_updated_at.isoformat() if a.status_updated_at else None,
            "dismissal_reason": a.dismissal_reason,
        }
        for a in actions
    ]


def get_action_stats(db: Session, case_id: str) -> dict:
    """Summary counts by action_type and status."""
    from sqlalchemy import func

    results = (
        db.query(
            InvestigationAction.action_type,
            InvestigationAction.status,
            func.count().label("count"),
        )
        .filter(InvestigationAction.case_id == uuid.UUID(case_id))
        .group_by(InvestigationAction.action_type, InvestigationAction.status)
        .all()
    )

    stats = {"by_type": {}, "by_status": {}, "total": 0}
    for action_type, status, count in results:
        t = action_type.value
        s = status.value
        stats["by_type"].setdefault(t, 0)
        stats["by_type"][t] += count
        stats["by_status"].setdefault(s, 0)
        stats["by_status"][s] += count
        stats["total"] += count

    return stats
