"""Missing Legal Elements Engine — checks elements coverage and suggests next steps.

For each applicable legal charge, assesses element satisfaction status,
categorizes required evidence types, identifies applicable exceptions,
and generates prioritized investigative recommendations.
"""

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.legal.element_mapper import get_element_map
from app.legal.explainable_reasoning import create_reasoning_trace
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Evidence type categorization
EVIDENCE_CATEGORIES = {
    "witness": ["witness_statements", "victim_statement", "informant_statement"],
    "expert_report": ["expert_opinion", "laboratory_report", "damage_assessment",
                      "malware_analysis", "expert_credentials", "appointment_document"],
    "digital_evidence": ["device_seizure", "digital_forensics", "network_logs",
                         "access_logs", "system_logs", "account_activity_logs",
                         "data_exfiltration_evidence", "hash_verification"],
    "forensic": ["integrity_certificate", "document_analysis", "seizure_memo",
                 "recovery_memo"],
    "documentary": ["documentary_evidence", "contractual_agreements", "legal_notices",
                    "fir_document", "complaint_document", "ownership_records",
                    "employment_records", "search_authorization", "warrant_document",
                    "delivery_receipt", "fir_receipt", "acknowledgment"],
    "financial": ["financial_records", "transaction_logs", "bank_statements",
                  "audit_reports", "fiduciary_evidence"],
    "communication": ["communication_records", "threat_evidence"],
}


def _categorize_evidence(evidence_type: str) -> str:
    """Categorize an evidence type into a high-level category."""
    for category, types in EVIDENCE_CATEGORIES.items():
        if evidence_type in types:
            return category
    return "other"


def analyze_missing_elements(case_id: str, db: Optional[Session] = None) -> dict:
    """
    Analyze element satisfaction for all applicable charges in a case.
    Identify missing elements, categorize required evidence, identify applicable
    exceptions, and generate prioritized investigative recommendations.
    """
    client = get_neo4j_client()

    # Get the element mapping status for the case
    mapped_data = get_element_map(case_id)
    sections_report = []

    for sec in mapped_data.get("sections", []):
        section_id = sec["section_id"]
        sec_ref = sec["section_reference"]
        title = sec["title"]

        # Fetch statute info
        sec_info = client.execute_read(
            "MATCH (ls:LegalSection {id: $sid}) RETURN ls.statute AS statute",
            {"sid": section_id},
        )
        statute = sec_info[0]["statute"] if sec_info else "BNS_2023"

        elements_report = []
        recommendations = []
        satisfied_count = 0
        partial_count = 0

        # Query all elements for this section
        db_elements = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[:HAS_ELEMENT]->(le:LegalElement)
            RETURN le.id AS id, le.element_text AS text,
                   le.evidence_types_typically_required AS required_types
            """,
            {"sid": section_id},
        )

        elements_map = {e["id"]: e for e in db_elements}

        # Fetch applicable exceptions for this section
        exceptions = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[:HAS_EXCEPTION]->(exc:Exception)
            RETURN exc.id AS id, exc.title AS title, exc.text AS text
            """,
            {"sid": section_id},
        )

        # Fetch burden of proof
        burdens = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[:HAS_BURDEN]->(bop:BurdenOfProof)
            RETURN bop.standard AS standard, bop.party AS party,
                   bop.description AS description
            """,
            {"sid": section_id},
        )

        for elem in sec.get("elements", []):
            eid = elem["element_id"]
            text = elem["element_text"]
            status = elem["status"]

            db_elem = elements_map.get(eid, {})
            req_types = db_elem.get("required_types", [])
            if isinstance(req_types, str):
                try:
                    req_types = json.loads(req_types.replace("'", '"'))
                except Exception:
                    req_types = [r.strip() for r in req_types.split(",") if r.strip()]

            # Categorize required evidence types
            categorized = {}
            for rt in req_types:
                cat = _categorize_evidence(rt)
                if cat not in categorized:
                    categorized[cat] = []
                categorized[cat].append(rt)

            # Compute priority score
            priority_score = _compute_priority(status, text, req_types)

            # Generate suggested investigation action
            suggested_action = _suggest_investigation_action(text, req_types, status)

            rec = None
            if status == "satisfied":
                satisfied_count += 1
            elif status == "partially_satisfied":
                partial_count += 1
                rec = suggested_action
                recommendations.append({"priority": priority_score, "text": rec})
            else:
                rec = suggested_action
                recommendations.append({"priority": priority_score, "text": rec})

            elements_report.append({
                "element_id": eid,
                "element_text": text,
                "status": status,
                "required_types": req_types,
                "evidence_categories": categorized,
                "priority_score": priority_score,
                "suggested_investigation_action": suggested_action,
                "recommendation": rec,
            })

        # Sort recommendations by priority (highest first)
        recommendations.sort(key=lambda r: r["priority"], reverse=True)

        # Section overall status
        total_elements = len(sec.get("elements", []))
        if total_elements == 0:
            sec_status = "unknown"
        elif satisfied_count == total_elements:
            sec_status = "fully_satisfied"
        elif satisfied_count > 0 or partial_count > 0:
            sec_status = "partially_satisfied"
        else:
            sec_status = "unsatisfied"

        section_entry = {
            "section_id": section_id,
            "section_reference": sec_ref,
            "statute": statute,
            "title": title,
            "status": sec_status,
            "satisfied_elements_count": satisfied_count,
            "total_elements_count": total_elements,
            "elements": elements_report,
            "recommendations": [r["text"] for r in recommendations],
            "applicable_exceptions": [
                {"id": exc["id"], "title": exc["title"], "text": exc.get("text", "")}
                for exc in exceptions
            ],
            "burden_of_proof": [
                {"standard": b["standard"], "party": b["party"],
                 "description": b.get("description", "")}
                for b in burdens
            ],
        }
        sections_report.append(section_entry)

        # Create reasoning trace for missing elements
        missing_elems = [e for e in elements_report if e["status"] != "satisfied"]
        if missing_elems:
            create_reasoning_trace(
                case_id=case_id,
                engine_source="missing_elements_engine",
                recommendation_text=f"Section {sec_ref}: {len(missing_elems)} element(s) need evidence",
                why=f"{sec_status}: {satisfied_count}/{total_elements} elements satisfied",
                unsatisfied_elements=[
                    {"id": e["element_id"], "text": e["element_text"]}
                    for e in missing_elems
                ],
                improvement_suggestions=[
                    e["suggested_investigation_action"] for e in missing_elems
                    if e.get("suggested_investigation_action")
                ],
                confidence_level="high" if sec_status == "partially_satisfied" else "low",
                legal_basis=f"{statute} {sec_ref}",
            )

    # Log memory record
    if db and sections_report:
        unsatisfied_charges = [
            s["section_reference"] for s in sections_report
            if s["status"] != "fully_satisfied"
        ]
        desc = "Missing legal elements analysis run. "
        if unsatisfied_charges:
            desc += f"Unsatisfied/partially satisfied charges: {', '.join(unsatisfied_charges)}"
        else:
            desc += "All charges fully satisfied."

        write_memory_record(
            db=db,
            case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=desc,
            actor="system:missing_elements_engine",
            reasoning=f"Analyzed {len(sections_report)} applicable charges.",
        )
        db.commit()

    return {
        "case_id": case_id,
        "applicable_sections": sections_report,
        "disclaimer": "Advisory only. Final charging decisions require independent prosecutorial assessment."
    }


def _compute_priority(status: str, element_text: str, req_types: list) -> float:
    """Compute priority score for a missing element (0.0 to 1.0)."""
    base = 0.0
    if status == "unsatisfied":
        base = 0.8
    elif status == "partially_satisfied":
        base = 0.5
    else:
        return 0.1

    # Boost for critical legal elements (mens rea)
    text_lower = element_text.lower()
    if any(kw in text_lower for kw in ["intent", "dishonest", "fraudulent", "knowledge"]):
        base += 0.15
    if any(kw in text_lower for kw in ["consent", "authorization", "without permission"]):
        base += 0.1

    # Boost for time-sensitive evidence types
    time_sensitive = {"communication_records", "network_logs", "cctv", "access_logs"}
    if time_sensitive.intersection(set(req_types)):
        base += 0.05

    return min(round(base, 2), 1.0)


def _suggest_investigation_action(element_text: str, req_types: list,
                                  status: str) -> str:
    """Generate a specific investigation action suggestion."""
    text_lower = element_text.lower()
    prefix = "STRENGTHEN: " if status == "partially_satisfied" else "CRITICAL: "

    if "intent" in text_lower or "dishonest" in text_lower or "fraudulent" in text_lower:
        return (f"{prefix}Obtain communication records pre-dating the offence to "
                "establish pre-existing fraudulent intent. Focus on messages, "
                "emails, or social media communications showing planning or deception.")
    if "consent" in text_lower or "without" in text_lower:
        return (f"{prefix}Record victim statement under BNSS Section 183 confirming "
                "absence of consent. Seek corroborating witness testimony.")
    if "delivery" in text_lower or "property" in text_lower or "retention" in text_lower:
        return (f"{prefix}Obtain complete financial trail: bank statements, "
                "transaction logs, UPI/NEFT records showing property transfer.")
    if "document" in text_lower or "electronic record" in text_lower or "false" in text_lower:
        return (f"{prefix}Seize device and submit for forensic examination. "
                "Obtain BSA Section 63 certificate. Compare with authentic documents.")
    if "threat" in text_lower or "fear" in text_lower or "alarm" in text_lower:
        return (f"{prefix}Preserve all threatening communications with metadata. "
                "Record victim statement describing fear and its impact.")
    if "access" in text_lower or "unauthorized" in text_lower:
        return (f"{prefix}Obtain server/system access logs, IP records, and "
                "authentication logs. Verify authorization scope of the accused.")
    if "personation" in text_lower or "pretending" in text_lower:
        return (f"{prefix}Collect evidence of the false identity used — fake profiles, "
                "forged credentials, or spoofed communications.")
    if "entrust" in text_lower or "dominion" in text_lower:
        return (f"{prefix}Obtain employment records, contractual agreements, or "
                "power-of-attorney documents establishing the trust relationship.")

    # Default
    cats = [_categorize_evidence(rt) for rt in req_types]
    unique_cats = list(set(cats))
    if unique_cats:
        return (f"{prefix}Collect {', '.join(unique_cats)} evidence "
                f"({', '.join(req_types[:3])}) to establish this element.")
    return f"{prefix}Investigate further to establish this element with corroborating evidence."
