"""ORACLE — Case Intelligence Report coordinator.

Synthesizes all reasoning layer outputs into the investigation's primary
decision surface. ORACLE does not perform its own reasoning — it reads from
Theory Engine, Competing Theory Engine, Evidence Gap Engine, Attention Engine,
Causal Layer, and Contradiction Engine.

Includes Meta-Cognition Agent alerts for investigation health monitoring.
"""

import math
import json
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from app.graph.driver import get_neo4j_client
from app.reasoning.theory_engine import explain_hypothesis
from app.reasoning.competing_theory_engine import get_ranked_hypotheses
from app.reasoning.probabilistic_engine import generate_confidence_report
from app.memory.writer import write_memory_record
from app.memory.reader import get_investigation_state
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def generate_report(case_id: str, db: Session = None) -> dict:
    """
    Generate a fresh CaseIntelligenceReport.
    Assembly operation — no new computation, just reading existing engine outputs.
    """
    now = datetime.now(timezone.utc).isoformat()

    state = get_investigation_state(case_id, db=db)
    if "error" in state:
        return state

    # Filter active hypotheses
    hypotheses = [
        {"id": h["hypothesis_id"], "prob": h["probability"], "narrative": h["narrative"]}
        for h in state["hypotheses"] if h["status"] == "active"
    ]
    hypotheses.sort(key=lambda x: x["prob"] or 0.0, reverse=True)

    probs = [h["prob"] for h in hypotheses if h["prob"] and h["prob"] > 0]
    entropy = -sum(p * math.log2(p) for p in probs) if probs else 0.0

    # Leading hypotheses
    leading = explain_hypothesis(case_id, hypotheses[0]["id"]) if hypotheses else None
    second = explain_hypothesis(case_id, hypotheses[1]["id"]) if len(hypotheses) > 1 else None

    # Key contradictions
    contradictions = [
        {"id": c["id"], "description": c["description"], "severity": c["severity"]}
        for c in state["contradictions"] if c["status"] == "open"
    ][:3]

    # Critical evidence gaps
    gaps = [
        {"id": g["id"], "description": g["description"], "urgency": g["urgency"]}
        for g in state["gaps"] if g["status"] == "open"
    ][:3]

    # Critical assumptions
    assumptions = [
        {"id": a["id"], "statement": a["statement"], "hypothesis": a["hypothesis"]}
        for a in state["assumptions"]
        if a["verification_status"] == "unverified" and a["criticality"] == "high"
    ]

    # Top attention entities
    attention = [
        {"id": att["id"], "label": att["label"], "display": att["display"], "score": att["score"]}
        for att in state["attention_entities"]
    ][:5]

    # Investigation health metrics
    client = get_neo4j_client()
    health = _compute_investigation_health(client, case_id, hypotheses, db)

    # Meta-cognition alerts
    alerts = _check_meta_cognition(hypotheses, entropy, health, case_id, db)

    # Narrative summary
    leading_name = hypotheses[0]["narrative"][:50] if hypotheses else "none"
    leading_prob = hypotheses[0]["prob"] if hypotheses else 0
    contra_text = contradictions[0]["description"][:60] if contradictions else "none"
    action_text = "review evidence gaps" if gaps else "continue monitoring"

    narrative = (
        f"Investigation currently has entropy {entropy:.2f} with "
        f"{len(hypotheses)} active hypothesis(es). "
        f"The leading theory is '{leading_name}' (probability {leading_prob:.2f}), "
        f"challenged by: {contra_text}. "
        f"Highest priority action: {action_text}."
    )
    if hypotheses:
        leading_id = hypotheses[0]["id"]
        narrative += f"\n\n[Trace leading theory proof chain](/cases/{case_id}/explain/hypothesis/{leading_id})"

    # Get cross-case intelligence additions
    cross_case = {}
    try:
        from app.cross_case.integration import get_full_cross_case_intelligence
        cross_case = get_full_cross_case_intelligence(case_id)
    except Exception as e:
        logger.warning("Failed to get cross-case intelligence for ORACLE report: %s", e)

    # Get chargesheet summary for ORACLE report
    chargesheet_summary = _get_chargesheet_summary(client, case_id)

    report = {
        "generated_at": now,
        "case_id": case_id,
        "entropy_score": round(entropy, 4),
        "leading_hypothesis": leading,
        "second_hypothesis": second,
        "key_contradictions": contradictions,
        "critical_gaps": gaps,
        "critical_assumptions": assumptions,
        "top_attention_entities": attention,
        "investigation_health": health,
        "alerts": alerts,
        "narrative_summary": narrative,
        "cross_case_intelligence": cross_case,
        "chargesheet_summary": chargesheet_summary,
    }

    # Store report in postgres
    if db:
        try:
            db.execute(sql_text("""
                CREATE TABLE IF NOT EXISTS oracle_reports (
                    report_id UUID PRIMARY KEY,
                    case_id UUID NOT NULL,
                    generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    entropy_score FLOAT,
                    report_data JSONB,
                    narrative_summary TEXT
                )
            """))
            db.execute(sql_text("""
                INSERT INTO oracle_reports (report_id, case_id, generated_at,
                                          entropy_score, report_data, narrative_summary)
                VALUES (:rid, :cid, :at, :ent, :data::jsonb, :narr)
            """), {
                "rid": uuid.uuid4(), "cid": uuid.UUID(case_id),
                "at": now, "ent": entropy,
                "data": json.dumps(report, default=str),
                "narr": narrative,
            })
            db.commit()
        except Exception as e:
            logger.warning("Failed to store ORACLE report: %s", e)
            db.rollback()

    return report


def get_report_history(case_id: str, db: Session) -> list[dict]:
    """List all ORACLE reports for a case (entropy time series)."""
    try:
        rows = db.execute(sql_text("""
            SELECT report_id, generated_at, entropy_score, narrative_summary
            FROM oracle_reports
            WHERE case_id = :cid
            ORDER BY generated_at DESC
        """), {"cid": uuid.UUID(case_id)}).fetchall()

        return [
            {
                "report_id": str(r[0]),
                "generated_at": r[1].isoformat() if r[1] else None,
                "entropy_score": r[2],
                "narrative_summary": r[3],
            }
            for r in rows
        ]
    except Exception:
        return []


def _compute_investigation_health(client, case_id, hypotheses, db) -> dict:
    """Structured assessment of investigation quality."""
    # Days since last elimination
    eliminated = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'eliminated'})
        RETURN h.eliminated_at AS ts
        ORDER BY h.eliminated_at DESC
        LIMIT 1
        """,
        {"cid": case_id},
    )
    days_since_elimination = None
    if eliminated and eliminated[0]["ts"]:
        try:
            elim_dt = datetime.fromisoformat(str(eliminated[0]["ts"]).replace("Z", "+00:00"))
            days_since_elimination = (datetime.now(timezone.utc) - elim_dt).days
        except (ValueError, TypeError):
            pass

    # Memory completeness: fraction of graph nodes with memory references
    total_nodes = client.execute_read(
        "MATCH (n) WHERE n.case_id = $cid RETURN count(n) AS cnt",
        {"cid": case_id},
    )
    total = total_nodes[0]["cnt"] if total_nodes else 0

    return {
        "hypothesis_count": len(hypotheses),
        "days_since_last_elimination": days_since_elimination,
        "total_graph_nodes": total,
    }


def _check_meta_cognition(hypotheses, entropy, health, case_id, db) -> list[dict]:
    """Meta-Cognition Agent: detect investigation health issues."""
    alerts = []

    hyp_count = health.get("hypothesis_count", 0)
    days = health.get("days_since_last_elimination")

    # Over-specification
    if hyp_count > 5 and entropy < 1.0:
        alerts.append({
            "alert_type": "over_specification",
            "message": f"Hypothesis space may be over-specified — {hyp_count} hypotheses "
                       f"but entropy only {entropy:.2f}. Consider merging equivalent hypotheses.",
            "recommendation": "Review hypotheses for equivalence using GET /hypotheses/ranked",
        })

    # Cognitive anchoring
    if days is not None and days > 14 and hyp_count > 1:
        alerts.append({
            "alert_type": "cognitive_anchoring",
            "message": f"No hypotheses eliminated in {days} days — investigation may be anchored.",
            "recommendation": "Review CHALLENGE output for each active hypothesis",
        })

    # Low-confidence support
    for h in hypotheses:
        # This would check chain confidence from the probabilistic engine
        # Simplified check here
        if h.get("prob", 0) > 0.5:
            alerts.append({
                "alert_type": "check_evidence_quality",
                "message": f"High-probability hypothesis '{h['narrative'][:40]}' — "
                           f"verify its supporting evidence chain confidence.",
                "recommendation": "Run GET /reasoning/confidence-report",
            })
            break

    # Write alerts as memory records
    if alerts and db:
        for alert in alerts:
            write_memory_record(
                db=db, case_id=case_id,
                record_type=MemoryRecordType.decision_made,
                description=f"ORACLE alert: {alert['alert_type']}",
                actor="system:oracle",
                reasoning=alert["message"],
            )
        db.commit()

    return alerts


def _get_chargesheet_summary(client, case_id: str) -> dict:
    """Summarize chargesheet status for the ORACLE report."""
    try:
        result = client.execute_read(
            """
            MATCH (cs:ChargesheetPackage {case_id: $cid})
            RETURN cs.id AS id, cs.overall_readiness_score AS score,
                   cs.readiness_tier AS tier, cs.trial_strength AS strength,
                   cs.filing_ready AS filing_ready,
                   cs.file_count AS fc, cs.hold_count AS hc, cs.drop_count AS dc,
                   cs.is_stale AS is_stale, cs.generated_at AS generated_at,
                   cs.evidence_count_at_generation AS ecnt
            ORDER BY cs.generated_at DESC LIMIT 1
            """,
            {"cid": case_id},
        )
        if not result:
            return {
                "exists": False,
                "filing_ready": False,
                "regenerate_recommended": True,
            }

        cs = result[0]
        return {
            "exists": True,
            "chargesheet_id": cs["id"],
            "filing_ready": cs.get("filing_ready", False),
            "overall_readiness_score": cs.get("score", 0.0),
            "readiness_tier": cs.get("tier", "not_ready"),
            "trial_strength": cs.get("strength", "weak"),
            "is_stale": cs.get("is_stale", False),
            "file_count": cs.get("fc", 0),
            "hold_count": cs.get("hc", 0),
            "drop_count": cs.get("dc", 0),
            "generated_at": cs.get("generated_at"),
            "regenerate_recommended": cs.get("is_stale", False),
        }
    except Exception as e:
        logger.warning("Failed to get chargesheet summary: %s", e)
        return {"exists": False, "error": str(e)}

