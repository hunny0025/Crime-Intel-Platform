"""Intelligence Layer endpoints — Contradiction scan, Evidence Gap scan/resolve,
Attention heatmap, and Action Queue management."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, ActionStatus, MemoryRecordType
from app.intelligence.contradiction_engine import (
    scan_case_contradictions,
    get_contradictions_detail,
)
from app.intelligence.gap_rules import (
    check_communication_silence,
    check_single_source_identifier,
)
from app.intelligence.attention_engine import (
    recompute_case_attention,
    get_attention_heatmap,
    get_attention_changes,
    compute_attention_value,
)
from app.intelligence.navigation_engine import (
    create_action_for_contradiction,
    create_action_for_gap,
    create_action_for_attention,
    transition_action_status,
    get_action_queue,
    get_action_stats,
)
from app.graph.driver import get_neo4j_client
from app.graph.hypothesis import create_evidence_gap, list_evidence_gaps
from app.memory.writer import write_memory_record

router = APIRouter(tags=["intelligence"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


# ── Contradiction Engine ─────────────────────────────────────────────────

@router.post("/cases/{case_id}/contradictions/scan")
def run_contradiction_scan(case_id: str, db: Session = Depends(get_db)):
    """Full sweep: check all Persons in the case for temporal/spatial contradictions."""
    _validate_case(case_id, db)
    contradictions = scan_case_contradictions(case_id, db)

    # Create actions for each new contradiction
    for c in contradictions:
        create_action_for_contradiction(
            db, case_id, c.get("id", ""), c.get("severity", "medium"),
        )
    db.commit()

    return {"contradictions_found": len(contradictions), "contradictions": contradictions}


@router.get("/cases/{case_id}/contradictions/detail")
def get_contradictions_with_detail(case_id: str, db: Session = Depends(get_db)):
    """Return all Contradictions with resolved involved entities."""
    _validate_case(case_id, db)
    return get_contradictions_detail(case_id)


# ── Evidence Gap Engine ──────────────────────────────────────────────────

@router.post("/cases/{case_id}/evidence-gaps/scan")
def run_gap_scan(case_id: str, db: Session = Depends(get_db)):
    """Full sweep: run all evidence gap detection rules."""
    _validate_case(case_id, db)

    gaps = []
    gaps.extend(check_communication_silence(case_id, db))
    gaps.extend(check_single_source_identifier(case_id, db))

    # Create actions for each new gap
    for g in gaps:
        create_action_for_gap(
            db, case_id, g.get("id", ""),
            g.get("expected_value", "medium"),
            g.get("urgency", "medium"),
        )
    db.commit()

    return {"gaps_found": len(gaps), "gaps": gaps}


class ResolveGapRequest(BaseModel):
    resolution_note: str


@router.post("/cases/{case_id}/evidence-gaps/{gap_id}/resolve")
def resolve_evidence_gap(
    case_id: str,
    gap_id: str,
    body: ResolveGapRequest,
    db: Session = Depends(get_db),
):
    """Mark an evidence gap as resolved."""
    _validate_case(case_id, db)

    client = get_neo4j_client()
    client.execute_write(
        """
        MATCH (g:EvidenceGap {id: $gap_id, case_id: $case_id})
        SET g.status = 'resolved', g.resolution_note = $note
        """,
        {"gap_id": gap_id, "case_id": case_id, "note": body.resolution_note},
    )

    write_memory_record(
        db=db,
        case_id=case_id,
        record_type=MemoryRecordType.lead_status_changed,
        description=f"Evidence gap {gap_id} resolved: {body.resolution_note}",
        actor="system:gap_engine",
        graph_refs=[gap_id],
        reasoning=body.resolution_note,
    )
    db.commit()

    return {"gap_id": gap_id, "status": "resolved", "resolution_note": body.resolution_note}


@router.get("/cases/{case_id}/evidence-gaps/detail")
def get_evidence_gaps_detail(case_id: str, db: Session = Depends(get_db)):
    """Return open EvidenceGaps with resolved RELATES_TO entities."""
    _validate_case(case_id, db)
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $case_id, status: 'open'})
        OPTIONAL MATCH (g)-[:RELATES_TO]->(related)
        RETURN g {.*} AS gap,
               collect({
                   node_id: related.id,
                   label: labels(related)[0],
                   display: coalesce(related.display_name, related.address, related.event_type, related.id)
               }) AS related_entities
        ORDER BY
            CASE g.expected_value WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            CASE g.urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
        """,
        {"case_id": case_id},
    )
    return [
        {
            **row["gap"],
            "related_entities": [e for e in row["related_entities"] if e.get("node_id")],
        }
        for row in result
    ]


# ── Attention Engine ─────────────────────────────────────────────────────

@router.get("/cases/{case_id}/attention-heatmap")
def attention_heatmap(case_id: str, db: Session = Depends(get_db)):
    """Return all scored nodes sorted by attention_value descending with breakdown."""
    _validate_case(case_id, db)
    # Recompute before returning
    recompute_case_attention(case_id)
    return get_attention_heatmap(case_id)


@router.get("/cases/{case_id}/attention-heatmap/changes")
def attention_changes(
    case_id: str,
    since: str = Query(..., description="ISO timestamp"),
    db: Session = Depends(get_db),
):
    """Return nodes whose attention_value increased since the given timestamp."""
    _validate_case(case_id, db)
    return get_attention_changes(case_id, since)


# ── Action Queue ─────────────────────────────────────────────────────────

@router.get("/cases/{case_id}/action-queue")
def list_action_queue(
    case_id: str,
    status: str = "pending",
    db: Session = Depends(get_db),
):
    """List investigation actions, sorted by priority_score descending."""
    _validate_case(case_id, db)
    actions = get_action_queue(db, case_id, status_filter=status)

    # Resolve target_ref to human-readable summary
    client = get_neo4j_client()
    for action in actions:
        ref = action["target_ref"]
        node = client.execute_read(
            """
            MATCH (n {id: $id})
            RETURN labels(n)[0] AS label,
                   coalesce(n.description, n.display_name, n.event_type, n.id) AS summary
            """,
            {"id": ref},
        )
        if node:
            action["target_summary"] = f"[{node[0]['label']}] {node[0]['summary']}"
        else:
            action["target_summary"] = ref

    return actions


class ActionStatusUpdate(BaseModel):
    new_status: str  # pending/in_progress/done/dismissed
    dismissal_reason: Optional[str] = None


@router.post("/cases/{case_id}/action-queue/{action_id}/status")
def update_action_status(
    case_id: str,
    action_id: str,
    body: ActionStatusUpdate,
    db: Session = Depends(get_db),
):
    """Transition an action's status. Requires dismissal_reason if dismissing."""
    _validate_case(case_id, db)

    try:
        new_status = ActionStatus(body.new_status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {body.new_status}. "
                   f"Valid: {[s.value for s in ActionStatus]}",
        )

    try:
        action = transition_action_status(
            db, case_id, action_id, new_status, body.dismissal_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    return {
        "action_id": str(action.action_id),
        "status": action.status.value,
        "dismissal_reason": action.dismissal_reason,
    }


@router.get("/cases/{case_id}/action-queue/stats")
def action_queue_stats(case_id: str, db: Session = Depends(get_db)):
    """Summary counts by action_type and status."""
    _validate_case(case_id, db)
    return get_action_stats(db, case_id)
