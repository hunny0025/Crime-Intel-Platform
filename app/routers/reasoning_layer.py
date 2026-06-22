"""Phase 5 — Reasoning Layer API endpoints.

All endpoints are read-from-Evidence-Plane, write-to-Theory-Plane.
Every output carries confidence, evidence_basis, and explanation.
"""

import json
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case

from app.reasoning.hpl.grammar import (
    parse_hpl, serialize_hpl, validate_hpl_entities,
    extract_evidence_lists, check_implied_evidence_status,
)
from app.reasoning.theory_engine import spawn_hypothesis, eliminate_hypothesis, explain_hypothesis
from app.reasoning.explainability import build_explanation_chain
from app.reasoning.competing_theory_engine import (
    get_ranked_hypotheses, compute_sensitivity, challenge_hypothesis,
)
from app.reasoning.causal_layer import (
    create_causal_link, build_causal_chain, counterfactual_simulation,
)
from app.reasoning.probabilistic_engine import (
    get_chain_confidence, compute_alr, compute_timestamp_integrity,
    generate_confidence_report, ensure_absence_base_rates_table,
)
from app.reasoning.crime_twin import get_crime_twin, simulate_scenario
from app.reasoning.oracle import generate_report, get_report_history
from app.reasoning.aire import run_pipeline, dead_end_predict, get_status as aire_status

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reasoning-layer"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


# ── Prompt 23: HPL Endpoints ────────────────────────────────────────────

class PredicateUpdate(BaseModel):
    predicates: list[str]


@router.put("/cases/{case_id}/hypotheses/{hypothesis_id}/predicates")
def update_predicates(
    case_id: str,
    hypothesis_id: str,
    body: PredicateUpdate,
    db: Session = Depends(get_db),
):
    """Replace predicate set for a hypothesis. Re-parse, re-validate, re-populate."""
    _validate_case(case_id, db)
    from app.graph.driver import get_neo4j_client
    from app.memory.writer import write_memory_record
    from app.db.models import MemoryRecordType

    # Validate all predicates
    errors = []
    for hpl_str in body.predicates:
        try:
            pred = parse_hpl(hpl_str)
            entity_errors = validate_hpl_entities(pred, case_id)
            errors.extend(entity_errors)
        except Exception as e:
            errors.append(f"Parse error: {str(e)[:100]}")

    if errors:
        raise HTTPException(status_code=400, detail={"validation_errors": errors})

    implied, forbidden = extract_evidence_lists(body.predicates)

    client = get_neo4j_client()
    client.execute_write(
        """
        MATCH (h:Hypothesis {id: $hid, case_id: $cid})
        SET h.predicates = $preds,
            h.implied_evidence = $implied,
            h.forbidden_evidence = $forbidden
        """,
        {
            "hid": hypothesis_id, "cid": case_id,
            "preds": json.dumps(body.predicates),
            "implied": json.dumps(implied),
            "forbidden": json.dumps(forbidden),
        },
    )

    write_memory_record(
        db=db, case_id=case_id,
        record_type=MemoryRecordType.theory_revised,
        description=f"Predicates updated for hypothesis {hypothesis_id}",
        actor="system:hpl",
        graph_refs=[hypothesis_id],
    )
    db.commit()

    return {
        "hypothesis_id": hypothesis_id,
        "predicates_count": len(body.predicates),
        "implied_evidence_count": len(implied),
        "forbidden_evidence_count": len(forbidden),
    }


@router.get("/cases/{case_id}/hypotheses/{hypothesis_id}/implied-evidence-status")
def get_implied_evidence_status(
    case_id: str, hypothesis_id: str, db: Session = Depends(get_db),
):
    """Check status of each implied evidence item: found | absent | not_checked."""
    _validate_case(case_id, db)
    from app.graph.driver import get_neo4j_client
    client = get_neo4j_client()

    hyp = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid}) RETURN h.implied_evidence AS implied",
        {"hid": hypothesis_id},
    )
    if not hyp:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    implied = json.loads(
        hyp[0].get("implied", "[]").replace("'", '"')
    ) if hyp[0].get("implied") else []

    statuses = check_implied_evidence_status(case_id, implied)
    return {"hypothesis_id": hypothesis_id, "items": statuses}


# ── Prompt 24: Theory Engine Endpoints ──────────────────────────────────

class SpawnRequest(BaseModel):
    narrative: str
    predicates: list[str] = []
    scenario_type: Optional[str] = None


class EliminateRequest(BaseModel):
    evidence_id: str
    reasoning: str


@router.post("/cases/{case_id}/hypotheses/spawn")
def spawn(case_id: str, body: SpawnRequest, db: Session = Depends(get_db)):
    """SPAWN — create a hypothesis with probability initialization."""
    _validate_case(case_id, db)
    return spawn_hypothesis(
        case_id, body.narrative, body.predicates, body.scenario_type, db,
    )


@router.post("/cases/{case_id}/hypotheses/{hypothesis_id}/eliminate")
def eliminate(
    case_id: str, hypothesis_id: str,
    body: EliminateRequest, db: Session = Depends(get_db),
):
    """ELIMINATE — remove a hypothesis and redistribute probability."""
    _validate_case(case_id, db)
    return eliminate_hypothesis(case_id, hypothesis_id, body.evidence_id, body.reasoning, db)


@router.get("/cases/{case_id}/hypotheses/{hypothesis_id}/explain")
def explain(case_id: str, hypothesis_id: str, db: Session = Depends(get_db)):
    """EXPLAIN — structured explanation of a hypothesis."""
    _validate_case(case_id, db)
    return explain_hypothesis(case_id, hypothesis_id)


# ── Prompt 25: Competing Theory Engine Endpoints ────────────────────────

@router.get("/cases/{case_id}/hypotheses/ranked")
def ranked(case_id: str, db: Session = Depends(get_db)):
    """All active hypotheses sorted by probability descending."""
    _validate_case(case_id, db)
    return get_ranked_hypotheses(case_id)


@router.get("/cases/{case_id}/hypotheses/{hypothesis_id}/sensitivity")
def sensitivity(case_id: str, hypothesis_id: str, db: Session = Depends(get_db)):
    """SENSITIVITY — top 5 weight-bearing evidence items."""
    _validate_case(case_id, db)
    return compute_sensitivity(case_id, hypothesis_id)


@router.get("/cases/{case_id}/hypotheses/{hypothesis_id}/challenge")
def challenge(case_id: str, hypothesis_id: str, db: Session = Depends(get_db)):
    """CHALLENGE — assumption vulnerability analysis."""
    _validate_case(case_id, db)
    return challenge_hypothesis(case_id, hypothesis_id)


# ── Prompt 26: Causal Layer Endpoints ───────────────────────────────────

class CausalLinkRequest(BaseModel):
    cause_event_id: str
    effect_event_id: str
    mechanism: str
    confidence: float = 0.8
    evidence_basis: list[str] = []


class CounterfactualRequest(BaseModel):
    focal_event_id: str
    removed_event_id: str
    actor: str = "system"


@router.post("/cases/{case_id}/graph/causal-link")
def create_causal(case_id: str, body: CausalLinkRequest, db: Session = Depends(get_db)):
    """Create a CAUSED relationship between Events."""
    _validate_case(case_id, db)
    return create_causal_link(
        case_id, body.cause_event_id, body.effect_event_id,
        body.mechanism, body.confidence, body.evidence_basis,
    )


@router.post("/cases/{case_id}/reasoning/counterfactual")
def counterfactual(case_id: str, body: CounterfactualRequest, db: Session = Depends(get_db)):
    """Counterfactual simulation: what if this event didn't happen?"""
    _validate_case(case_id, db)
    return counterfactual_simulation(
        case_id, body.focal_event_id, body.removed_event_id, body.actor, db,
    )


@router.get("/cases/{case_id}/reasoning/causal-chain/{focal_event_id}")
def causal_chain(case_id: str, focal_event_id: str, db: Session = Depends(get_db)):
    """Construct the causal chain leading to a focal event."""
    _validate_case(case_id, db)
    return build_causal_chain(case_id, focal_event_id)


# ── Prompt 27: Probabilistic Engine Endpoints ───────────────────────────

class AbsenceRateUpdate(BaseModel):
    evidence_type: str
    p_gen_innocent: float
    p_gen_guilty: float


@router.get("/cases/{case_id}/reasoning/confidence-report")
def confidence_report(case_id: str, db: Session = Depends(get_db)):
    """Per-hypothesis confidence report with chain values and ALR."""
    _validate_case(case_id, db)
    return generate_confidence_report(case_id, db)


@router.put("/config/absence-base-rates")
def update_absence_rates(body: AbsenceRateUpdate, db: Session = Depends(get_db)):
    """Update base rates for absence likelihood computation."""
    from sqlalchemy import text as sql_text
    ensure_absence_base_rates_table(db)
    db.execute(sql_text("""
        INSERT INTO absence_base_rates (evidence_type, p_gen_innocent, p_gen_guilty, updated_at)
        VALUES (:et, :pi, :pg, CURRENT_TIMESTAMP)
        ON CONFLICT (evidence_type) DO UPDATE
        SET p_gen_innocent = :pi, p_gen_guilty = :pg, updated_at = CURRENT_TIMESTAMP
    """), {"et": body.evidence_type, "pi": body.p_gen_innocent, "pg": body.p_gen_guilty})
    db.commit()
    return compute_alr(body.evidence_type, db)


# ── Prompt 28: Crime Twin Endpoints ─────────────────────────────────────

class SimulationRequest(BaseModel):
    hypothesis_id: str
    modifications: list[dict] = []


@router.get("/cases/{case_id}/crime-twin")
def crime_twin(case_id: str, db: Session = Depends(get_db)):
    """Full Crime Twin view: ordered events with hypothesis alignment + scenarios."""
    _validate_case(case_id, db)
    return get_crime_twin(case_id)


@router.post("/cases/{case_id}/crime-twin/simulate")
def simulate(case_id: str, body: SimulationRequest, db: Session = Depends(get_db)):
    """Simulate a what-if scenario. EXPLICITLY NOT EVIDENCE."""
    _validate_case(case_id, db)
    return simulate_scenario(case_id, body.hypothesis_id, body.modifications)


# ── Prompt 29: ORACLE Endpoints ─────────────────────────────────────────

@router.get("/cases/{case_id}/oracle/report")
def oracle_report(case_id: str, db: Session = Depends(get_db)):
    """Generate fresh Case Intelligence Report."""
    _validate_case(case_id, db)
    return generate_report(case_id, db)


@router.get("/cases/{case_id}/oracle/history")
def oracle_history(case_id: str, db: Session = Depends(get_db)):
    """List all ORACLE reports (entropy time series)."""
    _validate_case(case_id, db)
    return get_report_history(case_id, db)


# ── Prompt 30: AIRE Endpoints ───────────────────────────────────────────

class AIREEventRequest(BaseModel):
    event_type: str = "graph.updated"
    node_id: str = ""
    node_type: str = ""
    relationship_type: str = ""
    touched_entities: list[str] = []


@router.post("/cases/{case_id}/aire/process")
def aire_process(case_id: str, body: AIREEventRequest, db: Session = Depends(get_db)):
    """Manually trigger AIRE pipeline for testing/debugging."""
    _validate_case(case_id, db)
    return run_pipeline(case_id, body.event_type, body.model_dump(), db)


@router.get("/cases/{case_id}/aire/status")
def aire_status_endpoint(case_id: str, db: Session = Depends(get_db)):
    """AIRE monitoring/health endpoint."""
    _validate_case(case_id, db)
    return aire_status(case_id)


@router.get("/cases/{case_id}/aire/dead-end-predict")
def dead_end(
    case_id: str,
    action_type: str,
    target_ref: str = "",
    db: Session = Depends(get_db),
):
    """DEAD_END_PREDICT — estimate if an action will produce useful results."""
    _validate_case(case_id, db)
    return dead_end_predict(case_id, action_type, target_ref)


@router.get("/cases/{case_id}/explain/{metric_type}/{metric_id}")
def explain_metric_chain(
    case_id: str,
    metric_type: str,
    metric_id: str,
    max_depth: int = Query(3, description="Maximum depth to trace dependencies"),
    db: Session = Depends(get_db),
):
    """Traces the full proof dependency chain for a given metric/hypothesis."""
    _validate_case(case_id, db)
    return build_explanation_chain(metric_type, metric_id, max_depth)
