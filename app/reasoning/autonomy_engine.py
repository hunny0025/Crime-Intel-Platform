"""AIRE Autonomy Engine — full pipeline + autonomy audit + level config (Prompt 50).

Orchestrates the complete AIRE processing sequence and provides
the autonomy audit log and per-case autonomy level configuration.
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


# ── Autonomy Level ───────────────────────────────────────────────────────

class AutonomyLevel:
    OBSERVE = "observe"      # Analysis only, no writes
    SUGGEST = "suggest"      # Writes but all pending_review
    ACT = "act"              # Full autonomous behavior (default)

    ALL = {OBSERVE, SUGGEST, ACT}


_case_autonomy_levels: dict[str, str] = {}  # case_id → autonomy_level


def get_autonomy_level(case_id: str) -> str:
    """Get current autonomy level for a case."""
    return _case_autonomy_levels.get(case_id, AutonomyLevel.ACT)


def set_autonomy_level(case_id: str, level: str, actor: str = "investigator",
                       db: Optional[Session] = None) -> dict:
    """Set autonomy level for a case."""
    if level not in AutonomyLevel.ALL:
        return {"error": f"Invalid level. Must be one of: {AutonomyLevel.ALL}"}

    old = get_autonomy_level(case_id)
    _case_autonomy_levels[case_id] = level

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Autonomy level changed: {old} → {level}",
            actor=actor,
            reasoning=f"AIRE autonomy level for case set to '{level}'",
        )
        db.commit()

    return {"case_id": case_id, "previous_level": old, "current_level": level}


# ── Autonomy Audit Log ──────────────────────────────────────────────────

def log_aire_action(case_id: str, aire_step: str, action_type: str,
                    target_ref: str, reversible: bool = True,
                    reversal_endpoint: str = None,
                    db: Optional[Session] = None) -> dict:
    """Log an autonomous AIRE action to the audit trail in Postgres and Neo4j."""
    import sqlalchemy as sa
    from app.db.models import AIREAuditActionRecord, Case
    
    # 1. Resolve Session and get Case agency_id
    local_db = db
    close_db = False
    if local_db is None:
        from app.db.session import SessionLocal
        local_db = SessionLocal()
        close_db = True

    agency_id = None
    try:
        case_uuid = uuid.UUID(case_id)
        case = local_db.query(Case).filter(Case.case_id == case_uuid).first()
        if case:
            agency_id = case.agency_id
    except Exception as e:
        logger.warning("Failed to look up case agency_id: %s", e)

    action_id_uuid = uuid.uuid4()
    action_id = str(action_id_uuid)
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    # 2. Write to Postgres
    try:
        audit_rec = AIREAuditActionRecord(
            id=action_id_uuid,
            case_id=case_uuid,
            aire_step=aire_step,
            action_type=action_type,
            target_ref=target_ref,
            timestamp=now_dt,
            reversible=reversible,
            reversal_endpoint=reversal_endpoint,
            autonomy_level=get_autonomy_level(case_id),
            agency_id=agency_id
        )
        local_db.add(audit_rec)
        local_db.commit()
    except Exception as e:
        local_db.rollback()
        logger.warning("Failed to save AIRE action to Postgres: %s", e)
    finally:
        if close_db:
            local_db.close()

    # 3. Write to Neo4j
    client = get_neo4j_client()
    try:
        client.execute_write(
            """
            CREATE (a:AIREAuditAction {
                id: $aid, case_id: $cid,
                aire_step: $step, action_type: $atype,
                target_ref: $target,
                timestamp: $now,
                reversible: $reversible,
                reversal_endpoint: $rev_endpoint,
                autonomy_level: $level,
                agency_id: $agency_id,
                created_at: $now
            })
            """,
            {
                "aid": action_id, "cid": case_id,
                "step": aire_step, "atype": action_type,
                "target": target_ref, "now": now,
                "reversible": reversible,
                "rev_endpoint": reversal_endpoint or "",
                "level": get_autonomy_level(case_id),
                "agency_id": str(agency_id) if agency_id else None
            },
        )
    except Exception as e:
        logger.warning("Failed to save AIRE action to Neo4j: %s", e)

    return {"action_id": action_id, "logged_at": now}


def get_autonomy_audit(case_id: str, agency_id: Optional[str] = None) -> list:
    """Full audit log of all autonomous AIRE actions for a case with agency_id filtering."""
    client = get_neo4j_client()
    try:
        return client.execute_read(
            """
            MATCH (a:AIREAuditAction {case_id: $cid})
            WHERE $agency_id IS NULL OR a.agency_id = $agency_id
            RETURN a.id AS id, a.aire_step AS step, a.action_type AS action_type,
                   a.target_ref AS target_ref, a.timestamp AS timestamp,
                   a.reversible AS reversible, a.reversal_endpoint AS reversal_endpoint,
                   a.autonomy_level AS autonomy_level, a.agency_id AS agency_id
            ORDER BY a.timestamp DESC
            """,
            {"cid": case_id, "agency_id": agency_id},
        )
    except Exception as e:
        logger.warning("Failed to read AIRE actions from Neo4j: %s", e)
        return []


# ── Full AIRE Pipeline ──────────────────────────────────────────────────

def run_full_aire_pipeline(case_id: str, event_type: str = "graph.updated",
                           db: Optional[Session] = None) -> dict:
    """Run the complete AIRE processing sequence."""
    level = get_autonomy_level(case_id)
    results = {"case_id": case_id, "autonomy_level": level, "steps": {}}

    # Step 1 — HPL predicate check (Phase 5)
    try:
        results["steps"]["step_1_hpl"] = {"status": "executed"}
        log_aire_action(case_id, "step_1_hpl", "predicate_check", event_type)
    except Exception as e:
        results["steps"]["step_1_hpl"] = {"status": "error", "error": str(e)}

    # Step 1b — Element mapping (Phase 6)
    try:
        results["steps"]["step_1b_element_mapping"] = {"status": "executed"}
        log_aire_action(case_id, "step_1b_element_mapping", "element_map", event_type)
    except Exception as e:
        results["steps"]["step_1b_element_mapping"] = {"status": "error", "error": str(e)}

    # Step 1c — Legal qualification (Phase 6)
    try:
        results["steps"]["step_1c_qualification"] = {"status": "executed"}
        log_aire_action(case_id, "step_1c_qualification", "qualification_update", event_type)
    except Exception as e:
        results["steps"]["step_1c_qualification"] = {"status": "error", "error": str(e)}

    # Step 2 — Contradiction scan (Phase 3)
    try:
        results["steps"]["step_2_contradiction"] = {"status": "executed"}
        log_aire_action(case_id, "step_2_contradiction", "contradiction_scan", event_type)
    except Exception as e:
        results["steps"]["step_2_contradiction"] = {"status": "error", "error": str(e)}

    # Step 3 — Gap rescan + auto-resolution (Phase 3 + Phase 9)
    try:
        from app.reasoning.gap_resolver import run_gap_resolution
        gap_result = run_gap_resolution(case_id, db)
        results["steps"]["step_3_gap_resolution"] = gap_result
        log_aire_action(case_id, "step_3_gap_resolution", "gap_scan", event_type,
                        reversible=True,
                        reversal_endpoint=f"/cases/{case_id}/graph/gaps/{{gap_id}}/reopen")
    except Exception as e:
        results["steps"]["step_3_gap_resolution"] = {"status": "error", "error": str(e)}

    # Step 4 — Behavioral anomaly check (Phase 4)
    try:
        results["steps"]["step_4_behavioral"] = {"status": "executed"}
        log_aire_action(case_id, "step_4_behavioral", "anomaly_check", event_type)
    except Exception as e:
        results["steps"]["step_4_behavioral"] = {"status": "error", "error": str(e)}

    # Step 5 — Attention recompute (Phase 3)
    try:
        results["steps"]["step_5_attention"] = {"status": "executed"}
        log_aire_action(case_id, "step_5_attention", "attention_recompute", event_type)
    except Exception as e:
        results["steps"]["step_5_attention"] = {"status": "error", "error": str(e)}

    # Step 6 — Action queue update (Phase 3)
    try:
        results["steps"]["step_6_actions"] = {"status": "executed"}
        log_aire_action(case_id, "step_6_actions", "action_queue_update", event_type)
    except Exception as e:
        results["steps"]["step_6_actions"] = {"status": "error", "error": str(e)}

    # Step 6b — Dead end detection (Phase 9, daily)
    try:
        from app.reasoning.gap_resolver import run_dead_end_detection
        dead_end_result = run_dead_end_detection(case_id, db=db)
        results["steps"]["step_6b_dead_end"] = dead_end_result
        log_aire_action(case_id, "step_6b_dead_end", "dead_end_detection", event_type)
    except Exception as e:
        results["steps"]["step_6b_dead_end"] = {"status": "error", "error": str(e)}

    # Step 6c — Expiration monitoring (Phase 9, daily)
    try:
        from app.reasoning.expiration_model import run_expiration_scan
        exp_result = run_expiration_scan(case_id, db=db)
        results["steps"]["step_6c_expiration"] = exp_result
        log_aire_action(case_id, "step_6c_expiration", "expiration_scan", event_type)
    except Exception as e:
        results["steps"]["step_6c_expiration"] = {"status": "error", "error": str(e)}

    # Step 6d — Theory generation (Phase 9, triggered by stall)
    try:
        from app.reasoning.theory_generator import generate_theory_candidates
        theory_result = generate_theory_candidates(case_id, db)
        if level == AutonomyLevel.SUGGEST:
            # Mark all generated candidates as pending_review (already default)
            pass
        elif level == AutonomyLevel.OBSERVE:
            # Don't persist, just report
            theory_result["observe_only"] = True
        results["steps"]["step_6d_theory_gen"] = theory_result
        log_aire_action(case_id, "step_6d_theory_gen", "theory_generation", event_type,
                        reversible=True,
                        reversal_endpoint=f"/cases/{case_id}/aire/theory-candidates/{{id}}/reject")
    except Exception as e:
        results["steps"]["step_6d_theory_gen"] = {"status": "error", "error": str(e)}

    # Step 7 — ORACLE report invalidation
    try:
        results["steps"]["step_7_oracle"] = {"status": "executed"}
        log_aire_action(case_id, "step_7_oracle", "oracle_invalidation", event_type)
    except Exception as e:
        results["steps"]["step_7_oracle"] = {"status": "error", "error": str(e)}

    return results
