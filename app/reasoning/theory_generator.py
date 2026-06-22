"""Autonomous Theory Generator (Prompt 48).

Generates HypothesisCandidates from: pattern matching, unaccounted entity
analysis, and contradiction resolution. NOT auto-spawned — requires
investigator accept/reject.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

STRATEGY_STATS_FILE = Path(__file__).parent.parent / "config" / "generation_strategy_stats.json"


def check_generation_triggers(case_id: str) -> dict:
    """Check if any generation trigger condition is met."""
    client = get_neo4j_client()
    triggers = {"stalled_entropy": False, "unaccounted_entity": False,
                "open_contradiction": False}

    # Trigger 1: Stalled entropy (5+ events with <0.05 change)
    # Simplified: check if entropy hasn't changed recently
    reports = client.execute_read(
        """
        MATCH (r:ChargesheetReadinessReport {case_id: $cid})
        RETURN r.overall_readiness_score AS score
        ORDER BY r.generated_at DESC LIMIT 5
        """,
        {"cid": case_id},
    )
    if len(reports) >= 3:
        scores = [r["score"] for r in reports if r.get("score") is not None]
        if scores and max(scores) - min(scores) < 0.05:
            triggers["stalled_entropy"] = True

    # Trigger 2: High-attention entity not in any hypothesis
    high_attn = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.attention_value > 0.7
        AND NOT EXISTS {
            MATCH (h:Hypothesis {case_id: $cid, status: 'active'})-[:INVOLVES]->(n)
        }
        RETURN n.id AS id, labels(n)[0] AS label, n.attention_value AS attn
        LIMIT 5
        """,
        {"cid": case_id},
    )
    if high_attn:
        triggers["unaccounted_entity"] = True
        triggers["unaccounted_entities"] = high_attn

    # Trigger 3: Open contradiction > 24h
    open_contradictions = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $cid, status: 'open'})
        WHERE c.created_at < $cutoff
        RETURN c.id AS id, c.description AS desc
        LIMIT 5
        """,
        {"cid": case_id,
         "cutoff": (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=24)).isoformat()},
    )
    if open_contradictions:
        triggers["open_contradiction"] = True
        triggers["contradictions"] = open_contradictions

    triggers["any_triggered"] = any(
        triggers[k] for k in ("stalled_entropy", "unaccounted_entity", "open_contradiction")
    )
    return triggers


def generate_theory_candidates(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate HypothesisCandidate records from triggered strategies."""
    client = get_neo4j_client()
    triggers = check_generation_triggers(case_id)
    now = datetime.now(timezone.utc).isoformat()
    candidates = []

    # Strategy 1 — Pattern matching (from methodology library)
    if triggers.get("stalled_entropy") or triggers.get("any_triggered"):
        try:
            from app.cross_case.methodology_library import find_similar_cases
            similar = find_similar_cases(case_id, top_k=3)
            for sim_case in similar.get("similar_cases", []):
                for etype in sim_case.get("decisive_evidence_types", []):
                    cand_id = str(uuid.uuid4())
                    narrative = (
                        f"Based on {sim_case.get('similarity_score', 0):.0%} similar cases, "
                        f"an alternative explanation involving '{etype}' evidence pattern "
                        f"should be considered."
                    )
                    candidates.append({
                        "id": cand_id,
                        "case_id": case_id,
                        "generation_strategy": "pattern_match",
                        "narrative": narrative,
                        "generated_predicates": [],
                        "generation_rationale": f"Methodology library: similar case pattern "
                                                f"(score={sim_case.get('similarity_score', 0):.2f})",
                        "status": "pending_review",
                        "generated_at": now,
                    })
        except Exception as e:
            logger.warning("Pattern matching strategy failed: %s", e)

    # Strategy 2 — Unaccounted entity analysis
    for entity in triggers.get("unaccounted_entities", []):
        cand_id = str(uuid.uuid4())
        label = entity.get("label", "Entity")
        eid = entity.get("id", "unknown")
        narrative = (
            f"The involvement of {label} (attention={entity.get('attn', 0):.2f}) "
            f"is not explained by any current hypothesis. Its high attention suggests "
            f"a potential alternative involvement pattern."
        )
        candidates.append({
            "id": cand_id,
            "case_id": case_id,
            "generation_strategy": "unaccounted_entity",
            "narrative": narrative,
            "generated_predicates": [
                f"PREDICATE: {label}[{eid}] PARTICIPATED_IN Event[unknown] "
                f"IMPLIES [CommunicationRecord(window: recent)]"
            ],
            "generation_rationale": f"High-attention {label} not referenced by any hypothesis",
            "status": "pending_review",
            "generated_at": now,
        })

    # Strategy 3 — Contradiction resolution
    for contra in triggers.get("contradictions", []):
        cand_id = str(uuid.uuid4())
        narrative = (
            f"The open contradiction '{contra.get('desc', '')[:80]}' could be resolved "
            f"by considering an alternative sequence of events or involvement pattern."
        )
        candidates.append({
            "id": cand_id,
            "case_id": case_id,
            "generation_strategy": "contradiction_resolution",
            "narrative": narrative,
            "generated_predicates": [],
            "generation_rationale": f"Unresolved contradiction: {contra.get('id', '')}",
            "status": "pending_review",
            "generated_at": now,
        })

    # Store candidates in Neo4j
    for cand in candidates:
        client.execute_write(
            """
            CREATE (c:HypothesisCandidate {
                id: $cid, case_id: $caseid,
                generation_strategy: $strat, narrative: $narr,
                generated_predicates: $preds,
                generation_rationale: $rationale,
                status: 'pending_review',
                generated_at: $now,
                classification_tag: 'case_sensitive', created_at: $now
            })
            """,
            {
                "cid": cand["id"], "caseid": case_id,
                "strat": cand["generation_strategy"],
                "narr": cand["narrative"],
                "preds": json.dumps(cand["generated_predicates"]),
                "rationale": cand["generation_rationale"],
                "now": now,
            },
        )

    if db and candidates:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.hypothesis_created,
            description=f"AIRE generated {len(candidates)} theory candidate(s)",
            actor="system:theory_generator",
            reasoning=f"Triggers: stalled={triggers.get('stalled_entropy')}, "
                      f"unaccounted={triggers.get('unaccounted_entity')}, "
                      f"contradiction={triggers.get('open_contradiction')}",
        )
        db.commit()

    return {
        "case_id": case_id,
        "triggers": {k: v for k, v in triggers.items()
                     if k in ("stalled_entropy", "unaccounted_entity", "open_contradiction", "any_triggered")},
        "candidates_generated": len(candidates),
        "candidates": candidates,
    }


def get_theory_candidates(case_id: str) -> list:
    """List all pending HypothesisCandidates."""
    client = get_neo4j_client()
    return client.execute_read(
        """
        MATCH (c:HypothesisCandidate {case_id: $cid})
        WHERE c.status = 'pending_review'
        RETURN c.id AS id, c.narrative AS narrative,
               c.generation_strategy AS strategy,
               c.generation_rationale AS rationale,
               c.generated_predicates AS predicates,
               c.generated_at AS at
        ORDER BY c.generated_at DESC
        """,
        {"cid": case_id},
    )


def accept_candidate(case_id: str, candidate_id: str,
                     db: Optional[Session] = None) -> dict:
    """Investigator accepts a theory candidate — calls SPAWN."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    cand = client.execute_read(
        "MATCH (c:HypothesisCandidate {id: $cid}) RETURN c.narrative AS narr, "
        "c.generation_strategy AS strat",
        {"cid": candidate_id},
    )
    if not cand:
        return {"error": "Candidate not found"}

    client.execute_write(
        "MATCH (c:HypothesisCandidate {id: $cid}) SET c.status = 'accepted', c.accepted_at = $now",
        {"cid": candidate_id, "now": now},
    )

    # Create hypothesis from candidate
    hyp_id = str(uuid.uuid4())
    client.execute_write(
        """
        CREATE (h:Hypothesis {
            id: $hid, case_id: $caseid,
            narrative: $narr, status: 'active', probability: 0.1,
            spawned_from: 'theory_generator',
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {"hid": hyp_id, "caseid": case_id, "narr": cand[0]["narr"], "now": now},
    )

    # Update strategy stats
    _update_strategy_stats(cand[0].get("strat", ""), "accepted")

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.hypothesis_created,
            description=f"Theory candidate {candidate_id[:8]} accepted → Hypothesis {hyp_id[:8]}",
            actor="system:theory_generator",
        )
        db.commit()

    return {"candidate_id": candidate_id, "hypothesis_id": hyp_id, "status": "accepted"}


def reject_candidate(case_id: str, candidate_id: str, rejection_reason: str,
                     db: Optional[Session] = None) -> dict:
    """Investigator rejects a theory candidate."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    cand = client.execute_read(
        "MATCH (c:HypothesisCandidate {id: $cid}) RETURN c.generation_strategy AS strat",
        {"cid": candidate_id},
    )

    client.execute_write(
        """
        MATCH (c:HypothesisCandidate {id: $cid})
        SET c.status = 'rejected', c.rejection_reason = $reason, c.rejected_at = $now
        """,
        {"cid": candidate_id, "reason": rejection_reason, "now": now},
    )

    if cand:
        _update_strategy_stats(cand[0].get("strat", ""), "rejected")

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Theory candidate {candidate_id[:8]} rejected: {rejection_reason[:60]}",
            actor="system:theory_generator",
            reasoning=rejection_reason,
        )
        db.commit()

    return {"candidate_id": candidate_id, "status": "rejected"}


def _update_strategy_stats(strategy: str, outcome: str):
    """Update generation strategy accept/reject stats."""
    try:
        with open(STRATEGY_STATS_FILE) as f:
            stats = json.load(f)
        if strategy in stats:
            stats[strategy][outcome] = stats[strategy].get(outcome, 0) + 1
            with open(STRATEGY_STATS_FILE, "w") as f:
                json.dump(stats, f)
    except Exception:
        pass
