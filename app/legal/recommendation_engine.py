"""Investigation Recommendation Engine — aggregates case gaps and generates prioritized remediation actions.

Analyzes missing legal elements, integrity audit grades, procedural timelines, and defense simulation attack vectors.
Restructures recommendations into highest-value categories with expected investigative value scoring.
"""

import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.legal.missing_elements_engine import analyze_missing_elements
from app.legal.procedural_engine import get_procedural_timeline, generate_compliance_alerts
from app.court.integrity_engine import run_integrity_audit
from app.court.defense_simulator import run_defense_simulation
from app.legal.explainable_reasoning import create_reasoning_trace

logger = logging.getLogger(__name__)


def generate_investigation_recommendations(case_id: str, db: Optional[Session] = None) -> dict:
    """
    Analyze the case and generate structured, prioritized recommendations
    organized into highest-value categories with expected investigative value.
    """
    client = get_neo4j_client()
    all_recommendations = []

    # 1. Gather Missing Legal Elements
    try:
        elements_report = analyze_missing_elements(case_id, db)
        for sec in elements_report.get("applicable_sections", []):
            for elem in sec.get("elements", []):
                if elem["status"] != "satisfied":
                    priority = "high" if elem["status"] == "unsatisfied" else "medium"
                    rec_id = str(uuid.uuid4())
                    req_types = elem.get("required_types", [])
                    req_types_str = ", ".join(req_types) or "any relevant tool"

                    # Determine recommendation sub-category
                    sub_category = _classify_recommendation(req_types)

                    # Compute expected investigative value
                    eiv = _compute_expected_investigative_value(
                        elem, sec, elements_report
                    )

                    action = elem.get("suggested_investigation_action") or \
                        f"Collect evidence of type [{req_types_str}] to cover element '{elem['element_text']}'."

                    all_recommendations.append({
                        "recommendation_id": rec_id,
                        "category": "evidence_gap",
                        "sub_category": sub_category,
                        "priority": priority,
                        "priority_score": elem.get("priority_score", 0.5),
                        "expected_investigative_value": eiv,
                        "action_required": action,
                        "rationale": f"The charge '{sec['section_reference']} {sec['title']}' "
                                     f"requires proof of this element, which is currently {elem['status']}.",
                        "evidence_ref": elem["element_id"],
                    })
    except Exception as e:
        logger.warning("Failed to analyze legal elements in recommendation engine: %s", e)

    # 2. Gather Evidence Integrity Gaps (D & F grades)
    try:
        audit_report = run_integrity_audit(case_id, None)
        for art in audit_report.get("details", []):
            grade = art.get("grade", "A")
            if grade in ("D", "F"):
                priority = "critical" if grade == "F" else "high"
                rec_id = str(uuid.uuid4())
                eiv = 0.9 if grade == "F" else 0.7
                all_recommendations.append({
                    "recommendation_id": rec_id,
                    "category": "evidence_integrity",
                    "sub_category": "forensic_examination",
                    "priority": priority,
                    "priority_score": 0.95 if grade == "F" else 0.8,
                    "expected_investigative_value": eiv,
                    "action_required": f"Establish cryptographic chain of custody and verify hash for evidence "
                                       f"'{art.get('filename', art['artifact_id'])}'.",
                    "rationale": f"Artifact has an integrity grade of '{grade}' due to missing verification, "
                                 f"making it vulnerable to admissibility exclusion.",
                    "evidence_ref": art["artifact_id"],
                })
    except Exception as e:
        logger.warning("Failed to run integrity audit in recommendation engine: %s", e)

    # 3. Gather Procedural Compliance Issues
    try:
        timeline_report = get_procedural_timeline(case_id, None)
        if "error" not in timeline_report:
            for milestone in timeline_report.get("timeline", []):
                if milestone["status"] == "non_compliant" or milestone.get("is_overdue", False):
                    priority = "critical" if milestone["severity"] == "critical" else "high"
                    rec_id = str(uuid.uuid4())
                    eiv = 0.95 if milestone["severity"] == "critical" else 0.7
                    all_recommendations.append({
                        "recommendation_id": rec_id,
                        "category": "procedural_compliance",
                        "sub_category": "legal_action",
                        "priority": priority,
                        "priority_score": 0.95 if priority == "critical" else 0.75,
                        "expected_investigative_value": eiv,
                        "action_required": milestone["remediation_guidance"] or
                                           f"Address procedural requirement: {milestone['title']}.",
                        "rationale": f"Milestone '{milestone['title']}' (required by {milestone['required_by']}) "
                                     f"is currently {milestone['status']}.",
                        "evidence_ref": milestone["requirement_id"],
                    })
    except Exception as e:
        logger.warning("Failed to analyze procedural compliance in recommendation engine: %s", e)

    # 4. Gather Critical Defense Attack Vectors
    try:
        defense_report = run_defense_simulation(case_id, None)
        for vector in defense_report.get("attack_vectors", []):
            if vector.get("severity") in ("critical", "major"):
                priority = "critical" if vector["severity"] == "critical" else "high"
                rec_id = str(uuid.uuid4())
                eiv = 0.85 if vector["severity"] == "critical" else 0.65
                all_recommendations.append({
                    "recommendation_id": rec_id,
                    "category": "defense_vulnerability",
                    "sub_category": _classify_defense_action(vector),
                    "priority": priority,
                    "priority_score": 0.9 if priority == "critical" else 0.7,
                    "expected_investigative_value": eiv,
                    "action_required": vector.get("recommended_counter") or "Strengthen defense posture.",
                    "rationale": f"Defense simulation identified a vulnerability: {vector['description']}",
                    "evidence_ref": ", ".join(vector.get("evidence_refs", [])) or None,
                })
    except Exception as e:
        logger.warning("Failed to run defense simulation in recommendation engine: %s", e)

    # Sort by expected investigative value (highest first)
    all_recommendations.sort(key=lambda r: r.get("expected_investigative_value", 0), reverse=True)

    # Build highest-value category picks
    highest_value = _build_highest_value_picks(all_recommendations)

    # Create reasoning trace for the top recommendation
    if all_recommendations:
        top = all_recommendations[0]
        create_reasoning_trace(
            case_id=case_id,
            engine_source="recommendation_engine",
            recommendation_text=top["action_required"][:200],
            why=top["rationale"],
            improvement_suggestions=[r["action_required"][:100] for r in all_recommendations[:5]],
            confidence_level="high" if top.get("expected_investigative_value", 0) >= 0.8 else "medium",
            legal_basis=top.get("evidence_ref", ""),
        )

    return {
        "case_id": case_id,
        "highest_value_picks": highest_value,
        "recommendations": all_recommendations,
        "total_recommendations": len(all_recommendations),
        "disclaimer": "Advisory only. Recommendations are generated based on automated graph and "
                       "forensic patterns. Human legal counsel must evaluate final evidence strategy.",
    }


def _classify_recommendation(req_types: list) -> str:
    """Classify a recommendation into a sub-category based on required evidence types."""
    witness_types = {"witness_statements", "victim_statement", "informant_statement"}
    forensic_types = {"digital_forensics", "malware_analysis", "document_analysis",
                      "expert_opinion", "laboratory_report"}
    search_types = {"device_seizure", "seizure_memo", "recovery_memo"}
    digital_types = {"network_logs", "access_logs", "account_activity_logs",
                     "system_logs", "data_exfiltration_evidence"}
    financial_types = {"financial_records", "transaction_logs", "bank_statements"}

    req_set = set(req_types)
    if req_set & witness_types:
        return "witness_testimony"
    if req_set & forensic_types:
        return "forensic_examination"
    if req_set & search_types:
        return "search_and_seizure"
    if req_set & digital_types:
        return "digital_acquisition"
    if req_set & financial_types:
        return "financial_investigation"
    return "general_investigation"


def _classify_defense_action(vector: dict) -> str:
    """Classify defense counter-action into sub-category."""
    category = vector.get("category", "").lower()
    if "chain_of_custody" in category or "integrity" in category:
        return "forensic_examination"
    if "witness" in category or "credibility" in category:
        return "witness_testimony"
    if "procedural" in category or "process" in category:
        return "legal_action"
    return "general_investigation"


def _compute_expected_investigative_value(elem: dict, section: dict,
                                          full_report: dict) -> float:
    """Compute expected investigative value for a recommendation.

    Based on:
      - How many legal elements this evidence would satisfy
      - How critical the section is
      - Priority score of the element
    """
    priority_score = elem.get("priority_score", 0.5)
    total_sections = len(full_report.get("applicable_sections", []))
    total_elements = section.get("total_elements_count", 1)
    satisfied = section.get("satisfied_elements_count", 0)

    # Higher value when section is close to being fully satisfied
    completion_bonus = (satisfied / total_elements) * 0.2 if total_elements > 0 else 0

    # Higher value when fewer sections are fully covered
    coverage_bonus = 0.1 if total_sections > 0 else 0

    eiv = min(priority_score + completion_bonus + coverage_bonus, 1.0)
    return round(eiv, 4)


def _build_highest_value_picks(recommendations: list) -> dict:
    """Extract the single highest-value recommendation per sub-category."""
    picks = {}
    category_labels = {
        "witness_testimony": "highest_value_witness",
        "forensic_examination": "highest_value_forensic_examination",
        "search_and_seizure": "highest_value_search",
        "digital_acquisition": "highest_value_digital_acquisition",
        "financial_investigation": "highest_value_financial_investigation",
        "legal_action": "highest_value_legal_action",
        "general_investigation": "highest_priority_investigation_step",
    }

    seen_categories = set()
    for rec in recommendations:
        sub = rec.get("sub_category", "general_investigation")
        label = category_labels.get(sub, "highest_priority_investigation_step")
        if label not in seen_categories:
            picks[label] = {
                "action": rec["action_required"],
                "expected_value": rec.get("expected_investigative_value", 0),
                "category": rec["category"],
                "priority": rec["priority"],
                "evidence_ref": rec.get("evidence_ref"),
            }
            seen_categories.add(label)

    # Ensure "highest_priority_investigation_step" always exists
    if "highest_priority_investigation_step" not in picks and recommendations:
        top = recommendations[0]
        picks["highest_priority_investigation_step"] = {
            "action": top["action_required"],
            "expected_value": top.get("expected_investigative_value", 0),
            "category": top["category"],
            "priority": top["priority"],
            "evidence_ref": top.get("evidence_ref"),
        }

    return picks
