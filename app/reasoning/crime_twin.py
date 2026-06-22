"""Crime Twin — living probabilistic model of the crime scenario.

A read-only view (query-time construct) over the graph. The "twin" is NOT a
separate data store. It assembles Events with confidence annotations, hypothesis
alignment, and alternative interpretations.

Changes every time hypothesis probabilities update or new Events are added —
this is a live view, not a cached snapshot.
"""

import json
import logging
from datetime import datetime, timezone

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def get_crime_twin(case_id: str) -> dict:
    """
    Assemble the Crime Twin view: ordered event sequence with annotations.

    Optimized Cypher queries use case_id and valid_from indexes.
    """
    client = get_neo4j_client()

    # Step 1: Get all Events ordered by time
    # Query plan: uses index_event_case_id, sorts on valid_from
    events = client.execute_read(
        """
        MATCH (e:Event {case_id: $cid})
        OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(e)
        OPTIONAL MATCH (e)-[:AT]->(l:Location)
        WITH e, collect(DISTINCT {id: p.id, name: coalesce(p.display_name, p.id)}) AS participants,
             collect(DISTINCT {id: l.id, name: coalesce(l.display_name, l.address, l.id)}) AS locations
        RETURN e.id AS id, e.event_type AS event_type,
               e.valid_from AS valid_from, e.valid_to AS valid_to,
               coalesce(e.display_name, e.event_type) AS display,
               e.classification_tag AS tag,
               participants, locations
        ORDER BY e.valid_from
        """,
        {"cid": case_id},
    )

    # Step 2: Get all active hypotheses
    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.probability AS prob, h.narrative AS narrative,
               h.implied_evidence AS implied, h.forbidden_evidence AS forbidden
        """,
        {"cid": case_id},
    )

    # Step 3: Annotate each event with hypothesis alignment
    annotated_events = []
    for evt in events:
        alignments = []
        for h in hypotheses:
            alignment = _compute_alignment(evt, h, client, case_id)
            alignments.append({
                "hypothesis_id": h["id"],
                "alignment": alignment,
                "probability": h["prob"],
            })

        # Find alternative interpretations (same time window, same participants)
        alternatives = _find_alternatives(evt, events)

        annotated_events.append({
            "event_id": evt["id"],
            "event_type": evt["event_type"],
            "valid_from": str(evt["valid_from"]) if evt["valid_from"] else None,
            "valid_to": str(evt["valid_to"]) if evt["valid_to"] else None,
            "display": evt["display"],
            "participants": evt["participants"],
            "locations": evt["locations"],
            "hypothesis_alignment": alignments,
            "alternative_interpretations": alternatives,
        })

    # Step 4: Compute probabilistic scenarios
    scenarios = _compute_scenarios(annotated_events, hypotheses)

    # Get simulations_run count
    sim_res = client.execute_read(
        "MATCH (ca:CaseAnchor {case_id: $cid}) RETURN coalesce(ca.simulations_run, 0) AS sim_run",
        {"cid": case_id}
    )
    simulations_run = sim_res[0]["sim_run"] if sim_res else 0

    return {
        "case_id": case_id,
        "event_count": len(annotated_events),
        "events": annotated_events,
        "scenarios": scenarios,
        "simulations_run": simulations_run,
    }


def simulate_scenario(
    case_id: str,
    hypothesis_id: str,
    modifications: list[dict],
) -> dict:
    """
    Simulate a 'what if' scenario. NOT evidence — explicitly labeled.

    Modifications: [{"action": "remove"|"add", "event_id": "..."}]
    """
    client = get_neo4j_client()

    # Increment simulations_run count
    client.execute_write(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})
        SET ca.simulations_run = coalesce(ca.simulations_run, 0) + 1
        """,
        {"cid": case_id}
    )

    hyp = client.execute_read(
        "MATCH (h:Hypothesis {id: $hid}) "
        "RETURN h.narrative AS narrative, h.implied_evidence AS implied",
        {"hid": hypothesis_id},
    )
    if not hyp:
        return {"error": "Hypothesis not found"}

    implied = json.loads(
        hyp[0].get("implied", "[]").replace("'", '"')
    ) if hyp[0].get("implied") else []

    # Get current events
    events = client.execute_read(
        "MATCH (e:Event {case_id: $cid}) "
        "RETURN e.id AS id, e.event_type AS type, e.valid_from AS ts",
        {"cid": case_id},
    )
    current_ids = {e["id"] for e in events}

    # Apply modifications
    removed = set()
    added = []
    for mod in modifications:
        if mod.get("action") == "remove":
            removed.add(mod.get("event_id"))
        elif mod.get("action") == "add":
            added.append(mod)

    simulated_ids = (current_ids - removed) | {a.get("event_id", "") for a in added}

    # Check which IMPLIES are met/unmet in simulated scenario
    implies_status = []
    for item in implied:
        # Simplified check — would need full evidence matching in production
        implies_status.append({
            "evidence_type": item.get("evidence_type"),
            "status": "present" if item.get("evidence_type") in {e["type"] for e in events if e["id"] in simulated_ids} else "unmet",
        })

    return {
        "SIMULATION_NOT_EVIDENCE": True,
        "hypothesis_id": hypothesis_id,
        "hypothesis_narrative": hyp[0]["narrative"],
        "modifications_applied": modifications,
        "events_remaining": len(simulated_ids),
        "events_removed": list(removed),
        "implies_status": implies_status,
    }


def _compute_alignment(event: dict, hypothesis: dict, client, case_id: str) -> str:
    """Determine if an event confirms, contradicts, or is neutral to a hypothesis."""
    # Check if event is PREDICTED_BY or contradicts the hypothesis
    pred = client.execute_read(
        """
        MATCH (h:Hypothesis {id: $hid})-[:PREDICTED_BY]->(e:Event {id: $eid})
        RETURN count(*) AS cnt
        """,
        {"hid": hypothesis["id"], "eid": event["id"]},
    )
    if pred and pred[0]["cnt"] > 0:
        return "confirms"

    contra = client.execute_read(
        """
        MATCH (c:Contradiction)-[:INVOLVES]->(h:Hypothesis {id: $hid})
        MATCH (c)-[:INVOLVES]->(e:Event {id: $eid})
        RETURN count(*) AS cnt
        """,
        {"hid": hypothesis["id"], "eid": event["id"]},
    )
    if contra and contra[0]["cnt"] > 0:
        return "contradicts"

    return "neutral"


def _find_alternatives(event: dict, all_events: list) -> list:
    """Find events in same time window with overlapping participants."""
    if not event.get("valid_from"):
        return []

    alts = []
    evt_participants = {p.get("id") for p in event.get("participants", []) if p.get("id")}
    evt_time = str(event["valid_from"])

    for other in all_events:
        if other["id"] == event["id"]:
            continue
        if not other.get("valid_from"):
            continue

        other_participants = {p.get("id") for p in other.get("participants", []) if p.get("id")}
        overlap = evt_participants & other_participants

        if overlap and abs(hash(str(other["valid_from"])) - hash(evt_time)) < 3600:
            alts.append({
                "event_id": other["id"],
                "event_type": other["event_type"],
                "shared_participants": list(overlap),
            })

    return alts[:3]


def _compute_scenarios(events: list, hypotheses: list) -> dict:
    """Compute probabilistic scenario distributions."""
    if not hypotheses:
        return {"most_probable": None, "second": None, "residual": []}

    sorted_hyps = sorted(hypotheses, key=lambda h: h.get("prob", 0), reverse=True)

    most_probable = {
        "hypothesis_id": sorted_hyps[0]["id"],
        "probability": sorted_hyps[0]["prob"],
        "narrative": sorted_hyps[0]["narrative"],
        "consistent_events": [
            e["event_id"] for e in events
            if any(a["alignment"] == "confirms" and a["hypothesis_id"] == sorted_hyps[0]["id"]
                   for a in e.get("hypothesis_alignment", []))
        ],
    }

    second = None
    if len(sorted_hyps) > 1:
        second = {
            "hypothesis_id": sorted_hyps[1]["id"],
            "probability": sorted_hyps[1]["prob"],
            "narrative": sorted_hyps[1]["narrative"],
        }

    # Residual events: neutral to all hypotheses
    residual = [
        e["event_id"] for e in events
        if all(a["alignment"] == "neutral" for a in e.get("hypothesis_alignment", []))
    ]

    return {
        "most_probable": most_probable,
        "second": second,
        "residual_event_ids": residual,
    }
