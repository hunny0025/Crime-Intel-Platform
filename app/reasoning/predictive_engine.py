"""Predictive Intelligence & Decision Support Engine.

Addresses Gaps 7 & 16:
  - What will the suspect probably do next?
  - Which evidence is at risk of disappearing?
  - Which witness should be contacted first?
  - What should be seized immediately?
  - "What-if" simulations: If we seize Laptop A → probability of finding evidence = ?

Uses graph topology + temporal patterns + Bayesian reasoning to generate
forward-looking predictions and action-value estimates.
"""

import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


# ── Suspect Next-Move Prediction ─────────────────────────────────────────

def predict_suspect_actions(case_id: str, suspect_id: str) -> dict:
    """
    Predict likely next actions for a suspect based on behavioral patterns
    and graph topology.
    """
    client = get_neo4j_client()

    # Get suspect's event history
    events = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[:PARTICIPATED_IN]->(e:Event)
        WHERE e.valid_from IS NOT NULL
        RETURN e.event_type AS event_type, e.valid_from AS ts,
               e.valid_to AS end_ts
        ORDER BY e.valid_from DESC
        LIMIT 50
        """,
        {"pid": suspect_id, "cid": case_id},
    )

    # Get suspect's connections
    connections = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[r]-(n)
        RETURN type(r) AS rel_type, labels(n)[0] AS neighbor_type,
               n.id AS neighbor_id, n.display_name AS neighbor_name
        """,
        {"pid": suspect_id, "cid": case_id},
    )

    # Build event type frequency
    event_freq = defaultdict(int)
    for e in events:
        event_freq[e["event_type"]] += 1

    # Temporal pattern analysis
    recent_events = events[:5]
    escalation_types = {
        "communication": 1, "sms_phishing": 2, "credential_compromise": 3,
        "data_exfiltration": 4, "cash_withdrawal": 5, "ransomware_deployment": 6,
    }

    escalation_trajectory = []
    for e in recent_events:
        level = escalation_types.get(e["event_type"], 0)
        escalation_trajectory.append(level)

    is_escalating = (
        len(escalation_trajectory) >= 2 and
        escalation_trajectory[0] > escalation_trajectory[-1]
    )

    # Predict next actions
    predictions = []

    # 1. Evidence destruction risk
    has_digital_accounts = any(
        c["neighbor_type"] == "Account" for c in connections
    )
    if has_digital_accounts:
        predictions.append({
            "action": "evidence_destruction",
            "description": "Suspect may attempt to delete digital accounts or communications",
            "probability": 0.72 if is_escalating else 0.45,
            "urgency": "high",
            "recommended_response": "Immediately preserve digital evidence via legal hold",
            "basis": ["Digital account connections detected", "Escalation pattern observed" if is_escalating else "Standard risk"],
        })

    # 2. Flight risk
    has_location_data = any(
        c["neighbor_type"] == "Location" for c in connections
    )
    if is_escalating:
        predictions.append({
            "action": "flight_risk",
            "description": "Suspect may attempt to flee jurisdiction",
            "probability": 0.55 if is_escalating else 0.20,
            "urgency": "high" if is_escalating else "medium",
            "recommended_response": "Consider Look-Out Circular (LOC) if sufficient evidence",
            "basis": ["Escalating criminal activity pattern", f"{len(events)} known events"],
        })

    # 3. Communication with co-suspects
    co_suspect_links = [
        c for c in connections
        if c["rel_type"] == "COMMUNICATED_WITH" and c["neighbor_type"] == "Person"
    ]
    if co_suspect_links:
        predictions.append({
            "action": "coordination_with_accomplices",
            "description": f"Likely to coordinate with {len(co_suspect_links)} known associate(s)",
            "probability": 0.80,
            "urgency": "medium",
            "recommended_response": "Monitor communication channels of associated persons",
            "basis": [f"Active links to {len(co_suspect_links)} persons"],
        })

    # 4. Financial movement
    has_financial = any(
        c["neighbor_type"] == "Account" and "bank" in str(c.get("neighbor_name", "")).lower()
        or c["rel_type"] == "OWNS"
        for c in connections
    )
    if has_financial or "cash_withdrawal" in event_freq:
        predictions.append({
            "action": "financial_movement",
            "description": "Suspect may move funds to obscure financial trail",
            "probability": 0.65,
            "urgency": "high",
            "recommended_response": "Issue bank account freeze order under Section 102 CrPC / BNSS",
            "basis": ["Financial connections in graph", f"Past withdrawal events: {event_freq.get('cash_withdrawal', 0)}"],
        })

    # Sort by probability
    predictions.sort(key=lambda p: p["probability"], reverse=True)

    return {
        "suspect_id": suspect_id,
        "case_id": case_id,
        "total_known_events": len(events),
        "is_escalating": is_escalating,
        "predictions": predictions,
        "model": "predictive_intel_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Evidence Expiration Risk ─────────────────────────────────────────────

def assess_evidence_expiration_risk(case_id: str) -> dict:
    """
    Identify evidence at risk of disappearing or becoming unavailable.
    Returns prioritized list of at-risk evidence with time-to-expiry estimates.
    """
    client = get_neo4j_client()

    # All evidence-bearing nodes
    nodes = client.execute_read(
        """
        MATCH (n {case_id: $cid})
        WHERE n:Event OR n:Account OR n:Device
        RETURN n.id AS id, labels(n)[0] AS label, n.event_type AS event_type,
               n.valid_from AS created, n.classification_tag AS tag,
               n.display_name AS name
        """,
        {"cid": case_id},
    )

    at_risk = []
    now = datetime.now(timezone.utc)

    # Evidence type expiration rules (days until risk)
    expiration_rules = {
        "cctv_footage": {"retention_days": 30, "urgency": "critical",
                         "action": "Issue preservation notice to CCTV operator"},
        "cell_tower_cdr": {"retention_days": 180, "urgency": "high",
                           "action": "Request CDR from telecom provider via Section 91 CrPC"},
        "bank_statement": {"retention_days": 365, "urgency": "medium",
                           "action": "Request transaction records from bank"},
        "ip_log": {"retention_days": 90, "urgency": "high",
                   "action": "Request IP assignment logs from ISP"},
        "social_media_post": {"retention_days": 0, "urgency": "critical",
                              "action": "Screenshot and preserve immediately — can be deleted anytime"},
        "chat_message": {"retention_days": 0, "urgency": "critical",
                         "action": "Preserve via legal hold — suspect may delete"},
        "email": {"retention_days": 365, "urgency": "medium",
                  "action": "Request email data from provider"},
        "gps_log": {"retention_days": 60, "urgency": "high",
                    "action": "Extract GPS data from device before factory reset"},
        "atm_footage": {"retention_days": 45, "urgency": "critical",
                        "action": "Request ATM CCTV from bank immediately"},
        "browser_history": {"retention_days": 0, "urgency": "critical",
                            "action": "Extract before device sync or deletion"},
    }

    for node in nodes:
        event_type = node.get("event_type") or node.get("label", "").lower()

        for evidence_type, rule in expiration_rules.items():
            if evidence_type in str(event_type).lower() or evidence_type in str(node.get("name", "")).lower():
                days_remaining = rule["retention_days"]

                # Compute from node creation if available
                if node.get("created"):
                    try:
                        created = datetime.fromisoformat(
                            str(node["created"]).replace("Z", "+00:00")
                        )
                        elapsed = (now - created).days
                        days_remaining = max(rule["retention_days"] - elapsed, 0)
                    except (ValueError, TypeError):
                        pass

                at_risk.append({
                    "node_id": node["id"],
                    "node_label": node.get("label"),
                    "evidence_type": evidence_type,
                    "days_remaining": days_remaining,
                    "urgency": rule["urgency"],
                    "recommended_action": rule["action"],
                    "risk_score": round(1.0 - min(days_remaining / 30, 1.0), 2),
                })

    # Sort by urgency and days remaining
    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    at_risk.sort(key=lambda x: (urgency_order.get(x["urgency"], 9), x["days_remaining"]))

    return {
        "case_id": case_id,
        "total_nodes_scanned": len(nodes),
        "at_risk_count": len(at_risk),
        "at_risk_evidence": at_risk,
        "model": "evidence_expiration_v1",
        "generated_at": now.isoformat(),
    }


# ── Witness Prioritization ──────────────────────────────────────────────

def prioritize_witnesses(case_id: str) -> dict:
    """
    Rank witnesses by investigative value: connectivity, event proximity,
    hypothesis coverage, and cooperation likelihood.
    """
    client = get_neo4j_client()

    witnesses = client.execute_read(
        """
        MATCH (w:Person {case_id: $cid})
        WHERE w.role IN ['witness', 'victim', 'informant']
        OPTIONAL MATCH (w)-[:PARTICIPATED_IN]->(e:Event)
        OPTIONAL MATCH (w)-[r]-(n)
        RETURN w.id AS id, w.display_name AS name, w.role AS role,
               count(DISTINCT e) AS event_count,
               count(DISTINCT n) AS connection_count
        ORDER BY event_count DESC
        """,
        {"cid": case_id},
    )

    # Hypothesis coverage: how many active hypotheses reference this witness
    hypotheses = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'active'}) RETURN count(h) AS cnt",
        {"cid": case_id},
    )
    total_hypotheses = hypotheses[0]["cnt"] if hypotheses else 1

    ranked = []
    for w in witnesses:
        event_score = min(w["event_count"] / 5, 1.0)
        connection_score = min(w["connection_count"] / 10, 1.0)
        role_score = {"victim": 0.9, "witness": 0.7, "informant": 0.8}.get(w["role"], 0.5)

        priority_score = (event_score * 0.35 + connection_score * 0.25 + role_score * 0.4)

        ranked.append({
            "witness_id": w["id"],
            "name": w["name"],
            "role": w["role"],
            "event_involvement": w["event_count"],
            "connections": w["connection_count"],
            "priority_score": round(priority_score, 3),
            "recommended_timing": (
                "immediate" if priority_score > 0.7 else
                "within_48h" if priority_score > 0.4 else
                "scheduled"
            ),
        })

    ranked.sort(key=lambda x: x["priority_score"], reverse=True)

    return {
        "case_id": case_id,
        "witnesses_ranked": ranked,
        "total_witnesses": len(ranked),
        "model": "witness_prioritization_v1",
    }


# ── Seizure Priority Assessment ─────────────────────────────────────────

def assess_seizure_priority(case_id: str) -> dict:
    """
    Determine which devices/locations should be seized immediately
    based on evidence density and hypothesis impact.
    """
    client = get_neo4j_client()

    # Get all devices and locations
    targets = client.execute_read(
        """
        MATCH (n {case_id: $cid})
        WHERE n:Device OR n:Location
        OPTIONAL MATCH (n)-[r]-(connected)
        WITH n, labels(n)[0] AS label, count(DISTINCT connected) AS connections,
             collect(DISTINCT type(r)) AS rel_types
        OPTIONAL MATCH (n)<-[:INVOLVED_IN|AT|PARTICIPATED_IN]-(e:Event)
        WITH n, label, connections, rel_types, count(DISTINCT e) AS event_links
        RETURN n.id AS id, n.display_name AS name, label,
               connections, event_links, rel_types,
               n.device_type AS device_type, n.address AS address
        ORDER BY connections DESC
        """,
        {"cid": case_id},
    )

    prioritized = []
    for t in targets:
        evidence_density = min((t["connections"] + t["event_links"]) / 10, 1.0)

        # Device-type bonus
        device_bonus = {
            "mobile": 0.3, "laptop": 0.25, "desktop": 0.2,
            "server": 0.35, "atm": 0.15,
        }.get(t.get("device_type", ""), 0.1)

        score = evidence_density * 0.6 + device_bonus * 0.4

        prioritized.append({
            "target_id": t["id"],
            "name": t.get("name") or t.get("address") or t["id"],
            "type": t["label"],
            "device_type": t.get("device_type"),
            "connections": t["connections"],
            "event_links": t["event_links"],
            "seizure_score": round(score, 3),
            "urgency": (
                "immediate" if score > 0.6 else
                "within_24h" if score > 0.3 else
                "low_priority"
            ),
            "legal_basis": "Section 102 BNSS (seizure of property)" if t["label"] == "Device" else "Section 100 BNSS (search of place)",
        })

    prioritized.sort(key=lambda x: x["seizure_score"], reverse=True)

    return {
        "case_id": case_id,
        "seizure_targets": prioritized,
        "total_targets": len(prioritized),
        "model": "seizure_priority_v1",
    }


# ── Decision Support: "What-If" Simulator ────────────────────────────────

def simulate_action_outcome(
    case_id: str,
    action_type: str,
    target_id: str,
) -> dict:
    """
    Simulate the outcome of an investigative action.

    Supported actions:
      seize_device     — Probability of finding relevant evidence
      subpoena_records — Expected evidence yield from bank/telecom records
      interview_person — Expected information value from a witness
      arrest_suspect   — Case strength assessment for arrest
      forensic_extract — Expected findings from forensic analysis

    Returns probability estimates, expected findings, and risk assessment.
    """
    client = get_neo4j_client()

    # Get target node info
    target_info = client.execute_read(
        """
        MATCH (n {id: $tid, case_id: $cid})
        OPTIONAL MATCH (n)-[r]-(connected)
        RETURN n {.*} AS node, labels(n)[0] AS label,
               count(DISTINCT connected) AS connections,
               collect(DISTINCT {type: type(r), label: labels(connected)[0]}) AS conn_details
        """,
        {"tid": target_id, "cid": case_id},
    )

    if not target_info:
        return {"error": f"Target {target_id} not found in case {case_id}"}

    target = target_info[0]
    node = target["node"]
    connections = target["connections"]
    conn_details = target["conn_details"]

    # Get active hypotheses
    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.narrative AS narrative, h.probability AS prob
        ORDER BY h.probability DESC
        """,
        {"cid": case_id},
    )

    result = {
        "case_id": case_id,
        "action_type": action_type,
        "target_id": target_id,
        "target_label": target["label"],
        "target_name": node.get("display_name") or node.get("value") or target_id,
        "model": "decision_support_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if action_type == "seize_device":
        # Probability based on connectivity and event links
        base_prob = min(0.5 + connections * 0.05, 0.95)
        evidence_types_likely = []
        if "mobile" in str(node.get("device_type", "")):
            evidence_types_likely = ["SMS logs", "Call records", "GPS data", "Photos", "App data", "Browser history"]
            base_prob = min(base_prob + 0.1, 0.95)
        elif "laptop" in str(node.get("device_type", "")):
            evidence_types_likely = ["Documents", "Emails", "Browser history", "Chat logs", "Financial records"]
            base_prob = min(base_prob + 0.08, 0.95)
        elif "server" in str(node.get("device_type", "")):
            evidence_types_likely = ["Access logs", "Network traffic", "Database records", "Encryption keys"]
            base_prob = min(base_prob + 0.15, 0.95)

        result["outcome"] = {
            "probability_of_relevant_evidence": round(base_prob, 2),
            "expected_evidence_types": evidence_types_likely,
            "estimated_processing_time": "2-5 days for mobile, 5-14 days for laptop/server",
            "hypothesis_impact": _estimate_hypothesis_impact(hypotheses, connections),
            "risks": ["Data may be encrypted", "Device may have anti-forensic tools", "Remote wipe possible"],
            "legal_requirements": ["Search warrant under Section 94 BNSS", "Section 65B IT Act certificate", "Write-blocker mandatory"],
        }

    elif action_type == "subpoena_records":
        record_types = node.get("account_type", "unknown")
        prob = 0.85 if record_types in ("bank", "demat", "telecom") else 0.60
        result["outcome"] = {
            "probability_of_useful_records": round(prob, 2),
            "expected_response_time_days": 7 if "bank" in str(record_types) else 14,
            "record_types_expected": [record_types, "transaction_history", "account_statements", "KYC_data"],
            "hypothesis_impact": _estimate_hypothesis_impact(hypotheses, connections),
            "legal_requirements": ["Section 91 CrPC / BNSS order", "Court order for sealed records"],
        }

    elif action_type == "interview_person":
        role = node.get("role", "unknown")
        cooperation_prob = {"victim": 0.85, "witness": 0.65, "informant": 0.75, "suspect": 0.30}.get(role, 0.50)
        info_value = min(0.3 + connections * 0.07, 0.95)
        result["outcome"] = {
            "cooperation_probability": round(cooperation_prob, 2),
            "information_value": round(info_value, 2),
            "expected_new_leads": max(1, connections // 3),
            "hypothesis_impact": _estimate_hypothesis_impact(hypotheses, connections),
            "recommended_approach": "Cognitive interview" if role == "witness" else "Strategic disclosure" if role == "suspect" else "Standard",
            "risks": ["Witness may be hostile", "Information may be unreliable"] if role != "victim" else ["Re-traumatization risk"],
        }

    elif action_type == "arrest_suspect":
        # Need sufficient evidence strength
        event_links = sum(1 for c in conn_details if c.get("label") == "Event")
        evidence_strength = min(event_links * 0.15 + connections * 0.05, 0.95)
        result["outcome"] = {
            "case_strength_for_arrest": round(evidence_strength, 2),
            "sufficient_for_arrest": evidence_strength > 0.5,
            "evidence_count": event_links,
            "hypothesis_impact": _estimate_hypothesis_impact(hypotheses, connections),
            "risks": ["Premature arrest may compromise investigation", "Co-suspects may flee", "Evidence destruction risk"],
            "legal_requirements": ["Section 41 BNSS compliance", "Arrest memo mandatory", "Medical examination within 24h"],
        }

    elif action_type == "forensic_extract":
        prob = 0.80 if connections > 3 else 0.55
        result["outcome"] = {
            "probability_of_findings": round(prob, 2),
            "estimated_artifacts": max(5, connections * 3),
            "processing_pipeline": ["Hash verification", "File carving", "Timeline extraction", "Keyword search", "Entity extraction"],
            "hypothesis_impact": _estimate_hypothesis_impact(hypotheses, connections),
        }

    else:
        result["error"] = f"Unknown action_type: {action_type}"

    return result


def _estimate_hypothesis_impact(hypotheses: list, connections: int) -> dict:
    """Estimate how many hypotheses would be affected by this action."""
    total = len(hypotheses)
    if total == 0:
        return {"affected_hypotheses": 0, "impact": "unknown"}

    # Heuristic: actions on well-connected nodes affect more hypotheses
    affected = min(max(1, int(total * (connections / 20))), total)

    return {
        "total_active_hypotheses": total,
        "likely_affected": affected,
        "impact_level": (
            "high" if affected / total > 0.5 else
            "medium" if affected / total > 0.2 else
            "low"
        ),
    }
