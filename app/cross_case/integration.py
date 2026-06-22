"""Cross-case AIRE integration — wires Phase 8 into AIRE Step 0,
Theory Engine priors, and Action Queue decisive evidence types.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.cross_case.methodology_library import find_similar_cases, get_methodology_baseline
from app.cross_case.playbook_engine import get_recommended_playbook
from app.cross_case.fingerprint import check_recidivism, detect_modus_operandi
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def aire_step_0_cross_case(case_id: str, db: Optional[Session] = None) -> dict:
    """AIRE Step 0: cross-case intelligence on case creation."""
    results = {}

    # 1. Find similar cases
    try:
        similar = find_similar_cases(case_id)
        results["similar_cases"] = similar
    except Exception as e:
        logger.warning("Similar cases lookup failed: %s", e)
        results["similar_cases"] = {"error": str(e)}

    # 2. Methodology baseline
    try:
        baseline = get_methodology_baseline(case_id)
        results["methodology_baseline"] = baseline
    except Exception as e:
        logger.warning("Methodology baseline failed: %s", e)
        results["methodology_baseline"] = {"error": str(e)}

    # 3. Recommended playbook
    try:
        playbook = get_recommended_playbook(case_id)
        results["recommended_playbook"] = playbook
    except Exception as e:
        logger.warning("Playbook recommendation failed: %s", e)
        results["recommended_playbook"] = {"error": str(e)}

    # 4. Recidivism check for suspects
    client = get_neo4j_client()
    suspects = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})
        WHERE p.role = 'suspect' OR p.role IS NULL
        RETURN p.id AS pid
        LIMIT 10
        """,
        {"cid": case_id},
    )
    recidivism_results = []
    for s in suspects:
        try:
            r = check_recidivism(case_id, s["pid"])
            recidivism_results.append(r)
        except Exception as e:
            logger.warning("Recidivism check failed for %s: %s", s["pid"], e)
    results["recidivism_checks"] = recidivism_results

    # 5. MO detection
    try:
        mo = detect_modus_operandi(case_id)
        results["modus_operandi"] = mo
    except Exception as e:
        results["modus_operandi"] = {"error": str(e)}

    # Write memory record
    if db:
        insights_count = len(results.get("similar_cases", {}).get("similar_cases", []))
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Cross-case intelligence: {insights_count} similar cases found",
            actor="system:cross_case",
            reasoning=f"AIRE Step 0 completed. Similar={insights_count}, "
                      f"recidivism_matches={sum(r.get('matches_found', 0) for r in recidivism_results)}",
        )
        db.commit()

    return results


def get_cross_case_prior(case_id: str) -> dict:
    """Check if similar cases suggest a stronger prior for hypothesis spawning."""
    similar = find_similar_cases(case_id, top_k=10)
    cases = similar.get("similar_cases", [])

    if len(cases) < 3:
        return {"use_historical_prior": False, "reason": "Insufficient similar cases"}

    # Check if 80%+ have a dominant outcome
    outcomes = {}
    for c in cases:
        o = c.get("outcome", "unknown")
        outcomes[o] = outcomes.get(o, 0) + 1

    total = sum(outcomes.values())
    for outcome, count in outcomes.items():
        if count / total >= 0.8:
            return {
                "use_historical_prior": True,
                "dominant_outcome": outcome,
                "confidence": count / total,
                "sample_size": total,
                "reason": f"{count}/{total} similar cases had outcome '{outcome}'",
            }

    return {"use_historical_prior": False, "reason": "No dominant outcome (80%+)"}


def create_decisive_evidence_actions(case_id: str, db: Optional[Session] = None) -> list:
    """Create high-priority actions for decisive evidence types from similar cases."""
    similar = find_similar_cases(case_id, top_k=5)
    client = get_neo4j_client()

    # Collect decisive evidence types from similar cases
    decisive_types = set()
    for c in similar.get("similar_cases", []):
        for dt in c.get("decisive_evidence_types", []):
            decisive_types.add(dt)

    if not decisive_types:
        return []

    # Check which types are already present in the case
    present = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN DISTINCT n.source_tool AS tool
        """,
        {"cid": case_id},
    )
    present_types = {p["tool"] for p in present}
    missing_decisive = decisive_types - present_types

    actions = []
    for etype in missing_decisive:
        action_id = __import__("uuid").uuid4()
        # Check if action already exists
        existing = client.execute_read(
            """
            MATCH (a:InvestigationAction {case_id: $cid})
            WHERE a.description CONTAINS $etype AND a.status <> 'done'
            RETURN count(a) AS cnt
            """,
            {"cid": case_id, "etype": etype},
        )
        if existing and existing[0]["cnt"] > 0:
            continue

        now = datetime.now(timezone.utc).isoformat()
        client.execute_write(
            """
            CREATE (a:InvestigationAction {
                id: $aid, case_id: $cid,
                action_type: 'pursue_evidence_gap',
                target_ref: $etype,
                priority_score: 0.9,
                status: 'pending',
                description: $desc,
                classification_tag: 'case_sensitive',
                created_at: $now
            })
            """,
            {
                "aid": str(action_id), "cid": case_id, "etype": etype,
                "desc": f"Historical pattern: '{etype}' was decisive in similar cases "
                        f"but is not yet present. Priority elevated based on cross-case analysis.",
                "now": now,
            },
        )
        actions.append({"action_id": str(action_id), "evidence_type": etype, "priority": 0.9})

    return actions


def get_full_cross_case_intelligence(case_id: str) -> dict:
    """Consolidated cross-case intelligence for a single endpoint."""
    client = get_neo4j_client()

    similar = find_similar_cases(case_id)
    baseline = get_methodology_baseline(case_id)
    playbook = get_recommended_playbook(case_id)
    mo = detect_modus_operandi(case_id)

    # Recidivism for all suspects
    suspects = client.execute_read(
        "MATCH (p:Person {case_id: $cid}) RETURN p.id AS pid LIMIT 20",
        {"cid": case_id},
    )
    recidivism = []
    for s in suspects:
        try:
            recidivism.append(check_recidivism(case_id, s["pid"]))
        except Exception:
            pass

    # Action recommendations from cross-case
    decisive_actions = create_decisive_evidence_actions(case_id)

    return {
        "case_id": case_id,
        "similar_cases": similar,
        "methodology_baseline": baseline,
        "playbook_progress": playbook,
        "recidivism_matches": recidivism,
        "modus_operandi": mo,
        "decisive_evidence_actions": decisive_actions,
    }
