"""AIRE — Autonomous Investigation Reasoning Engine.

Master orchestrator that subscribes to all evidence events and maintains the
Theory Plane via a 7-step pipeline, without requiring investigator initiation.

Subscribes to:
    - evidence.normalized (Phase 1)
    - graph.updated (Phase 2)
    - osint.graph.updated (Phase 4)

Pipeline (per event):
    1. HPL predicate check → Bayesian update
    2. Contradiction scan
    3. Gap rescan
    4. Behavioral anomaly check
    5. Attention recompute
    6. Action queue update
    7. ORACLE report invalidation
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.reasoning.hpl.grammar import check_implied_evidence_status
from app.reasoning.competing_theory_engine import bayesian_update
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


class AIREState:
    """Per-case AIRE state tracking."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.last_event_processed: Optional[str] = None
        self.events_processed: int = 0
        self.step_timestamps: dict = {
            "cross_case": None,
            "hpl_check": None,
            "legal_remapping": None,
            "qualification_rescore": None,
            "procedural_compliance": None,
            "contradiction_scan": None,
            "gap_rescan": None,
            "behavioral_check": None,
            "attention_recompute": None,
            "action_queue_update": None,
            "oracle_invalidation": None,
        }
        self.step_errors: dict = {}
        self.stale_report: bool = False
        self.consecutive_low_entropy_changes: int = 0
        self.last_entropy: float = 0.0


# Global state registry
_aire_states: dict[str, AIREState] = {}


def get_aire_state(case_id: str) -> AIREState:
    """Get or create AIRE state for a case."""
    if case_id not in _aire_states:
        _aire_states[case_id] = AIREState(case_id)
    return _aire_states[case_id]


def _step_cross_case_step_0(
    client,
    case_id: str,
    event_type: str,
    event_data: dict,
    db: Optional[Session] = None,
) -> dict:
    """
    Step 0: Cross-case intelligence on case creation, and recidivism check
    for all Person nodes added in the first 24 hours.
    """
    results = {}
    from app.cross_case.integration import aire_step_0_cross_case
    
    # 1. Run cross-case intelligence on case creation (or if manually triggered)
    if event_type == "case.created" or event_data.get("event_type") == "case.created":
        results = aire_step_0_cross_case(case_id, db)
        
    # 2. Recidivism check for all Person nodes added to the case in the first 24 hours
    is_within_24h = False
    if db:
        from app.db.models import Case
        import uuid as pyuuid
        try:
            case_obj = db.query(Case).filter(Case.case_id == pyuuid.UUID(case_id)).first()
            if case_obj:
                age = datetime.now(timezone.utc) - case_obj.created_at.replace(tzinfo=timezone.utc)
                if age.total_seconds() < 86400:
                    is_within_24h = True
        except Exception as e:
            logger.warning("Failed to check case age in SQL: %s", e)

    if not is_within_24h:
        try:
            anchor = client.execute_read(
                "MATCH (ca:CaseAnchor {case_id: $cid}) RETURN ca.created_at AS created",
                {"cid": case_id}
            )
            if anchor and anchor[0]["created"]:
                created_str = str(anchor[0]["created"])
                created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - created_dt).total_seconds() < 86400:
                    is_within_24h = True
        except Exception as e:
            logger.warning("Failed to check case age in Neo4j: %s", e)

    if is_within_24h:
        new_node_ids = event_data.get("new_node_ids", [])
        if not new_node_ids:
            new_node_ids = event_data.get("touched_entities", [])
            
        new_persons = []
        for nid in new_node_ids:
            if nid:
                try:
                    node_label = client.execute_read(
                        "MATCH (n {id: $nid}) RETURN labels(n) AS labels",
                        {"nid": nid}
                    )
                    if node_label and "Person" in node_label[0]["labels"]:
                        new_persons.append(nid)
                except Exception:
                    pass
                    
        if new_persons:
            from app.cross_case.fingerprint import check_recidivism
            recidivism_results = []
            for pid in new_persons:
                try:
                    r = check_recidivism(case_id, pid)
                    recidivism_results.append(r)
                except Exception as e:
                    logger.warning("Recidivism check failed for Person %s: %s", pid, e)
            results["recidivism_checks_first_24h"] = recidivism_results
            
            if db and recidivism_results:
                write_memory_record(
                    db=db, case_id=case_id,
                    record_type=MemoryRecordType.decision_made,
                    description=f"Recidivism check executed for {len(new_persons)} new Person nodes in first 24h",
                    actor="system:cross_case",
                    reasoning=f"Identified {sum(r.get('matches_found', 0) for r in recidivism_results)} historical recidivism matches.",
                )
                db.commit()
                
    return results


def run_pipeline(
    case_id: str,
    event_type: str,
    event_data: dict,
    db: Optional[Session] = None,
) -> dict:
    """
    Run the full 7-step AIRE pipeline for an incoming event.
    Returns pipeline execution summary.
    """
    state = get_aire_state(case_id)
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    results = {}

    # Extract entity IDs touched by this event
    node_id = event_data.get("node_id", "")
    node_type = event_data.get("node_type", "")
    relationship_type = event_data.get("relationship_type", "")
    touched_entities = event_data.get("touched_entities", [node_id])

    # ── Step 0: Cross-Case Intelligence ──────────────────────────────────
    try:
        step0 = _step_cross_case_step_0(client, case_id, event_type, event_data, db)
        results["cross_case"] = step0
        state.step_timestamps["cross_case"] = now
    except Exception as e:
        state.step_errors["cross_case"] = str(e)
        results["cross_case"] = {"error": str(e)}
        logger.error("AIRE Step 0 (Cross-Case) error: %s", e)

    # ── Step 1: HPL Predicate Check ──────────────────────────────────────
    try:
        step1 = _step_hpl_check(client, case_id, node_type, node_id, db)
        results["hpl_check"] = step1
        state.step_timestamps["hpl_check"] = now
    except Exception as e:
        state.step_errors["hpl_check"] = str(e)
        results["hpl_check"] = {"error": str(e)}
        logger.error("AIRE Step 1 (HPL) error: %s", e)

    # ── Step 1d: Legal Element Re-Mapping ──────────────────────────────
    try:
        step1d = _step_legal_remapping(case_id, db)
        results["legal_remapping"] = step1d
        state.step_timestamps["legal_remapping"] = now
    except Exception as e:
        state.step_errors["legal_remapping"] = str(e)
        results["legal_remapping"] = {"error": str(e)}
        logger.error("AIRE Step 1d (Legal Re-Mapping) error: %s", e)

    # ── Step 1e: Qualification Re-Score ───────────────────────────────
    try:
        step1e = _step_qualification_rescore(case_id, db)
        results["qualification_rescore"] = step1e
        state.step_timestamps["qualification_rescore"] = now
    except Exception as e:
        state.step_errors["qualification_rescore"] = str(e)
        results["qualification_rescore"] = {"error": str(e)}
        logger.error("AIRE Step 1e (Qualification Re-Score) error: %s", e)

    # ── Step 1f: Procedural Compliance Check ──────────────────────────
    try:
        step1f = _step_procedural_compliance_check(client, case_id, db)
        results["procedural_compliance"] = step1f
        state.step_timestamps["procedural_compliance"] = now
    except Exception as e:
        state.step_errors["procedural_compliance"] = str(e)
        results["procedural_compliance"] = {"error": str(e)}
        logger.error("AIRE Step 1f (Procedural Compliance Check) error: %s", e)

    # ── Step 1g: Chargesheet Staleness Check ─────────────────────────────
    try:
        step1g = _step_chargesheet_staleness(case_id, event_type)
        results["chargesheet_staleness"] = step1g
    except Exception as e:
        state.step_errors["chargesheet_staleness"] = str(e)
        results["chargesheet_staleness"] = {"error": str(e)}
        logger.error("AIRE Step 1g (Chargesheet Staleness) error: %s", e)

    # ── Step 2: Contradiction Scan ───────────────────────────────────────
    try:
        step2 = _step_contradiction_scan(client, case_id, touched_entities)
        results["contradiction_scan"] = step2
        state.step_timestamps["contradiction_scan"] = now
    except Exception as e:
        state.step_errors["contradiction_scan"] = str(e)
        results["contradiction_scan"] = {"error": str(e)}
        logger.error("AIRE Step 2 (Contradiction) error: %s", e)

    # ── Step 3: Gap Rescan ───────────────────────────────────────────────
    try:
        step3 = _step_gap_rescan(client, case_id, touched_entities)
        results["gap_rescan"] = step3
        state.step_timestamps["gap_rescan"] = now
    except Exception as e:
        state.step_errors["gap_rescan"] = str(e)
        results["gap_rescan"] = {"error": str(e)}
        logger.error("AIRE Step 3 (Gap) error: %s", e)

    # ── Step 4: Behavioral Anomaly Check ─────────────────────────────────
    try:
        step4 = _step_behavioral_check(client, case_id, touched_entities)
        results["behavioral_check"] = step4
        state.step_timestamps["behavioral_check"] = now
    except Exception as e:
        state.step_errors["behavioral_check"] = str(e)
        results["behavioral_check"] = {"error": str(e)}
        logger.error("AIRE Step 4 (Behavioral) error: %s", e)

    # ── Step 5: Attention Recompute ──────────────────────────────────────
    try:
        step5 = _step_attention_recompute(case_id, touched_entities)
        results["attention_recompute"] = step5
        state.step_timestamps["attention_recompute"] = now
    except Exception as e:
        state.step_errors["attention_recompute"] = str(e)
        results["attention_recompute"] = {"error": str(e)}
        logger.error("AIRE Step 5 (Attention) error: %s", e)

    # ── Step 6: Action Queue Update ──────────────────────────────────────
    try:
        step6 = _step_action_queue_update(client, case_id)
        results["action_queue_update"] = step6
        state.step_timestamps["action_queue_update"] = now
    except Exception as e:
        state.step_errors["action_queue_update"] = str(e)
        results["action_queue_update"] = {"error": str(e)}
        logger.error("AIRE Step 6 (Actions) error: %s", e)

    # ── Step 7: ORACLE Report Invalidation ───────────────────────────────
    try:
        state.stale_report = True
        results["oracle_invalidation"] = {"stale": True}
        state.step_timestamps["oracle_invalidation"] = now
    except Exception as e:
        state.step_errors["oracle_invalidation"] = str(e)
        results["oracle_invalidation"] = {"error": str(e)}

    # Update state
    state.last_event_processed = node_id
    state.events_processed += 1

    # Check for GENERATE trigger (stalled investigation)
    _check_generate_trigger(client, case_id, state, db)

    return {
        "case_id": case_id,
        "event_processed": node_id,
        "pipeline_steps": results,
        "events_total": state.events_processed,
        "timestamp": now,
    }


def dead_end_predict(case_id: str, action_type: str, target_ref: str) -> dict:
    """
    DEAD_END_PREDICT — estimate probability an action produces no hypothesis update.

    If >0.8 of hypotheses are unaffected → label as low_discriminating_value.
    """
    client = get_neo4j_client()

    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.implied_evidence AS implied, h.forbidden_evidence AS forbidden
        """,
        {"cid": case_id},
    )

    if not hypotheses:
        return {"low_discriminating_value": True, "irrelevance_ratio": 1.0,
                "explanation": "No active hypotheses"}

    irrelevant_count = 0
    for h in hypotheses:
        implied = json.loads(h.get("implied", "[]").replace("'", '"')) if h.get("implied") else []
        forbidden = json.loads(h.get("forbidden", "[]").replace("'", '"')) if h.get("forbidden") else []

        # Check if action_type appears in any IMPLIES or FORBIDS
        all_types = [item.get("evidence_type", "") for item in implied + forbidden]
        if action_type not in all_types:
            irrelevant_count += 1

    ratio = irrelevant_count / len(hypotheses)
    low_value = ratio > 0.8

    return {
        "action_type": action_type,
        "target_ref": target_ref,
        "irrelevance_ratio": round(ratio, 4),
        "low_discriminating_value": low_value,
        "explanation": (
            f"Action irrelevant to {irrelevant_count}/{len(hypotheses)} active hypotheses"
            + (" — low discriminating value" if low_value else " — may be discriminating")
        ),
    }


def get_status(case_id: str) -> dict:
    """Return AIRE's current state for monitoring."""
    state = get_aire_state(case_id)
    from app.reasoning.debouncer import debouncer
    return {
        "case_id": case_id,
        "last_event_processed": state.last_event_processed,
        "events_processed": state.events_processed,
        "step_timestamps": state.step_timestamps,
        "step_errors": state.step_errors,
        "stale_report": state.stale_report,
        "debounce_buffer_size": debouncer.get_buffer_size(case_id),
    }


# ── Pipeline Steps ──────────────────────────────────────────────────────

def _step_hpl_check(client, case_id, evidence_type, evidence_id, db):
    """Step 1: Check HPL predicates and trigger Bayesian updates."""
    hypotheses = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) "
        "RETURN h.id AS id, h.implied_evidence AS implied, h.forbidden_evidence AS forbidden",
        {"cid": case_id},
    )

    updates = []
    for h in hypotheses:
        implied = json.loads(h.get("implied", "[]").replace("'", '"')) if h.get("implied") else []
        forbidden = json.loads(h.get("forbidden", "[]").replace("'", '"')) if h.get("forbidden") else []

        # Check for newly-satisfied IMPLIES/FORBIDS
        for item in implied:
            if item.get("evidence_type", "").lower() == evidence_type.lower():
                updates.append({"hypothesis": h["id"], "match": "implies"})
                break
        for item in forbidden:
            if item.get("evidence_type", "").lower() == evidence_type.lower():
                updates.append({"hypothesis": h["id"], "match": "forbids"})
                break

    # Run Bayesian update if there are matches
    if updates:
        evidence_ids = evidence_id if isinstance(evidence_id, list) else [evidence_id]
        for eid in evidence_ids:
            if eid:
                bayesian_update(case_id, eid, evidence_type, db)

    return {"predicates_checked": len(hypotheses), "updates_triggered": len(updates)}


def _step_contradiction_scan(client, case_id, touched_entities):
    """Step 2: Incremental contradiction check for touched entities."""
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    contradictions_found = 0

    for entity_id in touched_entities:
        if not entity_id:
            continue
        # Check for temporal co-location conflicts
        conflicts = client.execute_read(
            """
            MATCH (p {id: $eid})-[r1:AT]->(l1:Location),
                  (p)-[r2:AT]->(l2:Location)
            WHERE l1.id <> l2.id
            AND r1.valid_from IS NOT NULL AND r2.valid_from IS NOT NULL
            AND abs(duration.between(datetime(r1.valid_from), datetime(r2.valid_from)).seconds) < 1800
            AND NOT EXISTS {
                MATCH (c:Contradiction)-[:INVOLVES]->(p)
                WHERE c.description CONTAINS l1.id AND c.description CONTAINS l2.id
            }
            RETURN l1.id AS loc1, l2.id AS loc2, r1.valid_from AS t1, r2.valid_from AS t2
            LIMIT 1
            """,
            {"eid": entity_id},
        )
        if conflicts:
            c = conflicts[0]
            contra_id = str(uuid.uuid4())
            client.execute_write(
                """
                CREATE (c:Contradiction {
                    id: $cid, case_id: $case_id,
                    contradiction_type: 'temporal',
                    description: $desc, severity: 'high', status: 'open',
                    classification_tag: 'case_sensitive', created_at: $now
                })
                """,
                {
                    "cid": contra_id, "case_id": case_id,
                    "desc": f"Entity {entity_id} at {c['loc1']} and {c['loc2']} "
                            f"within 30 min ({c['t1']} vs {c['t2']})",
                    "now": now,
                },
            )
            contradictions_found += 1

    return {"entities_scanned": len(touched_entities), "contradictions_found": contradictions_found}


def _step_gap_rescan(client, case_id, touched_entities):
    """Step 3: Re-evaluate open EvidenceGaps for resolution."""
    resolved = 0
    gaps = client.execute_read(
        "MATCH (g:EvidenceGap {case_id: $cid, status: 'open'}) "
        "RETURN g.id AS id, g.gap_type AS type",
        {"cid": case_id},
    )

    for gap in gaps:
        # Check if gap's implied evidence now exists
        statuses = check_implied_evidence_status(case_id, [{
            "evidence_type": gap["type"], "params": {},
        }])
        if statuses and statuses[0]["status"] == "found":
            client.execute_write(
                "MATCH (g:EvidenceGap {id: $gid}) "
                "SET g.status = 'resolved', g.resolution_note = 'evidence arrived'",
                {"gid": gap["id"]},
            )
            resolved += 1

    return {"gaps_checked": len(gaps), "gaps_resolved": resolved}


def _step_behavioral_check(client, case_id, touched_entities):
    """Step 4: Check for behavioral anomalies on persons with baselines."""
    checks = 0
    for entity_id in touched_entities:
        if not entity_id:
            continue
        # Check if entity is a Person with a baseline
        has_baseline = client.execute_read(
            """
            MATCH (p:Person {id: $eid})-[:HAS_BASELINE]->(b:BehavioralBaseline)
            RETURN b.id AS bid
            """,
            {"eid": entity_id},
        )
        if has_baseline:
            checks += 1
            # Anomaly detection would be triggered here
            # (delegated to behavioral engine in production)

    return {"persons_with_baselines_checked": checks}


def _step_attention_recompute(case_id, touched_entities):
    """Step 5: Recompute attention_value for touched entities."""
    from app.intelligence.attention_engine import compute_attention_value
    recomputed = 0
    for entity_id in touched_entities:
        if entity_id:
            compute_attention_value(case_id, entity_id)
            recomputed += 1
    return {"entities_recomputed": recomputed}


def _step_action_queue_update(client, case_id):
    """Step 6: Generate InvestigationActions for new contradictions/gaps."""
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    actions_created = 0

    # New contradictions without actions
    new_contras = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $cid, status: 'open'})
        WHERE NOT EXISTS { MATCH (a:InvestigationAction)-[:ADDRESSES]->(c) }
        RETURN c.id AS id, c.description AS desc
        """,
        {"cid": case_id},
    )
    for c in new_contras:
        action_id = str(uuid.uuid4())
        client.execute_write(
            """
            CREATE (a:InvestigationAction {
                id: $aid, case_id: $cid,
                action_type: 'resolve_contradiction',
                target_ref: $tid, description: $desc,
                status: 'pending', priority: 0.8,
                created_at: $now
            })
            """,
            {"aid": action_id, "cid": case_id, "tid": c["id"],
             "desc": f"Resolve: {c['desc'][:80]}", "now": now},
        )
        actions_created += 1

    return {"actions_created": actions_created}


def _check_generate_trigger(client, case_id, state, db):
    """
    GENERATE operation: detect stalled investigations and unaccounted entities.
    Triggers when entropy hasn't changed by >0.05 across 3 events.
    """
    # Check for high-attention entities not referenced by any hypothesis
    unaccounted = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.attention_value > 0.5
        AND NOT EXISTS {
            MATCH (h:Hypothesis {case_id: $cid, status: 'active'})-[:PREDICTED_BY]->(n)
        }
        AND NOT EXISTS {
            MATCH (c:Contradiction)-[:INVOLVES]->(n)
        }
        RETURN n.id AS id, labels(n)[0] AS label, n.attention_value AS attention
        LIMIT 3
        """,
        {"cid": case_id},
    )

    if unaccounted and db:
        for entity in unaccounted:
            write_memory_record(
                db=db, case_id=case_id,
                record_type=MemoryRecordType.theory_revised,
                description=f"Unaccounted high-attention entity: {entity['label']}[{entity['id']}] "
                            f"(attention={entity['attention']:.2f})",
                actor="system:aire",
                reasoning=f"Entity {entity['id']} has high attention value but is not referenced "
                          f"by any active hypothesis — consider whether a new hypothesis is needed.",
                graph_refs=[entity["id"]],
            )
        db.commit()


def _step_legal_remapping(case_id: str, db: Optional[Session] = None) -> dict:
    """Step 1d: Legal Element Re-Mapping."""
    from app.legal.element_mapper import map_elements_for_case
    results = map_elements_for_case(case_id, threshold=0.4, db=db)
    return {"mappings_processed": results.get("mappings_above_threshold", 0)}


def _step_qualification_rescore(case_id: str, db: Optional[Session] = None) -> dict:
    """Step 1e: Qualification Re-Score."""
    from app.legal.qualification_engine import qualify_sections
    results = qualify_sections(case_id, db=db)
    return {"qualifications_calculated": len(results.get("qualifications", []))}


def _step_procedural_compliance_check(client, case_id: str, db: Optional[Session] = None) -> dict:
    """Step 1f: Procedural Compliance Check."""
    from app.legal.procedural_engine import scan_compliance, generate_compliance_alerts
    # Run scan
    scan_compliance(case_id, db=db)
    # Generate alerts
    alerts_data = generate_compliance_alerts(case_id, db=db)

    # Create InvestigationAction nodes for overdue/upcoming deadlines
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    actions_created = 0

    all_alerts = alerts_data.get("blocking", []) + alerts_data.get("urgent", []) + alerts_data.get("upcoming", [])
    for alert in all_alerts:
        req_id = alert["requirement_id"]
        # Check if pending InvestigationAction already exists for this requirement
        existing = client.execute_read(
            """
            MATCH (a:InvestigationAction {case_id: $cid, target_ref: $req_id, status: 'pending'})
            RETURN count(a) AS cnt
            """,
            {"cid": case_id, "req_id": req_id}
        )
        if existing and existing[0]["cnt"] == 0:
            action_id = str(uuid.uuid4())
            priority = 0.9 if alert["alert_level"] == "blocking" else 0.7 if alert["alert_level"] == "urgent" else 0.5
            client.execute_write(
                """
                CREATE (a:InvestigationAction {
                    id: $aid, case_id: $cid,
                    action_type: 'procedural_compliance',
                    target_ref: $tid, description: $desc,
                    status: 'pending', priority: $priority,
                    created_at: $now
                })
                """,
                {
                    "aid": action_id, "cid": case_id, "tid": req_id,
                    "desc": alert["message"], "priority": priority, "now": now
                }
            )
            actions_created += 1

    return {
        "total_active_alerts": alerts_data.get("total_alerts", 0),
        "actions_created": actions_created
    }


def _step_chargesheet_staleness(case_id: str, event_type: str) -> dict:
    """Step 1g: Mark existing chargesheet as stale when new evidence arrives.

    Triggered by evidence.normalized and graph.updated events, signaling
    that the chargesheet needs regeneration to incorporate new data.
    """
    stale_events = {"evidence.normalized", "graph.updated", "osint.graph.updated"}
    if event_type not in stale_events:
        return {"skipped": True, "reason": f"Event type {event_type} does not trigger staleness"}

    try:
        from app.legal.chargesheet_engine import mark_chargesheet_stale
        result = mark_chargesheet_stale(
            case_id,
            reason=f"New {event_type} event received — chargesheet needs regeneration",
        )
        return result
    except Exception as e:
        logger.warning("Failed to mark chargesheet stale: %s", e)
        return {"error": str(e)}


class AIREWorker:
    """
    Background worker that consumes 'graph.updated' events,
    debounces them, and triggers the AIRE pipeline.
    """

    def __init__(self) -> None:
        self._thread = None
        self._running = False
        self._consumer = None
        self._loop = None

    def start(self, db_session_factory) -> None:
        """Start the worker in a background thread."""
        import threading
        if self._thread and self._thread.is_alive():
            self.stop()
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(db_session_factory,),
            daemon=True,
            name="aire-worker",
        )
        self._thread.start()
        logger.info("AIRE worker started")

    def _run_loop(self, db_session_factory) -> None:
        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run(db_session_factory))

    async def _run(self, db_session_factory) -> None:
        import asyncio
        from app.events.consumer import KafkaConsumer
        from app.reasoning.debouncer import debouncer

        self._consumer = KafkaConsumer(
            topics=["graph.updated"],
            group_id="aire-workers",
        )

        def process_batch(case_id: str, batch_payload: dict):
            db = db_session_factory()
            try:
                run_pipeline(case_id, "graph.batch_updated", batch_payload, db)
            except Exception as e:
                logger.error("Error running AIRE pipeline for case %s: %s", case_id, e, exc_info=True)
            finally:
                db.close()

        debouncer.set_callback(process_batch)

        while self._running:
            try:
                envelope = await self._loop.run_in_executor(
                    None, self._consumer.poll_once, 1.0
                )
                if envelope is None:
                    await asyncio.sleep(0.1)
                    continue

                logger.info(
                    "AIRE worker: received graph.updated event %s for case %s",
                    envelope.event_id, envelope.case_id,
                )
                debouncer.add(str(envelope.case_id), envelope.payload)

            except Exception as e:
                logger.error("Error in AIRE worker loop: %s", e, exc_info=True)
                await asyncio.sleep(1.0)

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False
        if self._consumer:
            try:
                self._consumer.close()
            except Exception:
                pass
            self._consumer = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("AIRE worker stopped")


_worker = None


def get_aire_worker() -> AIREWorker:
    global _worker
    if _worker is None:
        _worker = AIREWorker()
    return _worker
