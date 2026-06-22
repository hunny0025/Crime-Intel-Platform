"""Chargesheet Intelligence Engine — synthesizes final chargesheet readiness.

Integrates element coverage, admissibility certificates, procedural compliance, prosecution theory, and accused persons list.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.legal.missing_elements_engine import analyze_missing_elements
from app.legal.procedural_engine import get_procedural_timeline
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)


def generate_intelligence_chargesheet(case_id: str, db: Optional[Session] = None) -> dict:
    """
    Generate an upgraded, fully synthesized Chargesheet Intelligence Report.
    """
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    report_id = str(uuid.uuid4())

    # 1. Get Accused Persons
    accused_nodes = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})
        WHERE p.status IN ['suspect', 'accused'] OR p.label = 'Suspect'
        RETURN p.id AS person_id, coalesce(p.display_name, p.id) AS name, p.status AS status
        """,
        {"cid": case_id},
    )
    accused_list = [
        {"person_id": a["person_id"], "name": a["name"], "status": a["status"]}
        for a in accused_nodes
    ]

    # 2. Get Admissibility / Integrity Certificates
    certificates_nodes = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        RETURN c.id AS cert_id, c.evidence_ref AS evidence_ref,
               c.overall_integrity_grade AS grade, c.generated_at AS certified_at
        """,
        {"cid": case_id},
    )
    certificates_list = [
        {
            "certificate_id": c["cert_id"],
            "evidence_ref": c["evidence_ref"],
            "integrity_grade": c["grade"],
            "certified_at": c["certified_at"],
        }
        for c in certificates_nodes
    ]

    # 3. Get Prosecution Theory (Top Hypothesis)
    theory_nodes = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid})
        WHERE h.posterior_probability IS NOT NULL
        RETURN h.id AS id, h.description AS description, h.posterior_probability AS probability
        ORDER BY h.posterior_probability DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    theory_summary = {
        "hypothesis_id": theory_nodes[0]["id"] if theory_nodes else None,
        "description": theory_nodes[0]["description"] if theory_nodes else "No established case theory",
        "probability": theory_nodes[0]["probability"] if theory_nodes else 0.0,
    }

    # 4. Get Missing Legal Elements Report
    missing_report = analyze_missing_elements(case_id)
    applicable_charges = []
    has_missing_elements = False
    unsupported_allegations = []

    for sec in missing_report.get("applicable_sections", []):
        # Per-allegation evidence breakdown
        allegation = _build_allegation_breakdown(client, case_id, sec)

        applicable_charges.append({
            "section_id": sec["section_id"],
            "section_reference": sec["section_reference"],
            "statute": sec["statute"],
            "title": sec["title"],
            "status": sec["status"],
            "satisfied_elements_count": sec["satisfied_elements_count"],
            "total_elements_count": sec["total_elements_count"],
            "recommendations": sec["recommendations"],
            "applicable_exceptions": sec.get("applicable_exceptions", []),
            "burden_of_proof": sec.get("burden_of_proof", []),
            **allegation,
        })
        if sec["status"] != "fully_satisfied":
            has_missing_elements = True
        if sec["status"] == "unsatisfied":
            unsupported_allegations.append({
                "section_reference": sec["section_reference"],
                "title": sec["title"],
                "reason": f"None of {sec['total_elements_count']} required elements are supported by evidence.",
            })

    # 5. Get Procedural Compliance Timeline and Blockers
    # We pass None for DB to prevent double logging in timeline scan
    timeline_report = get_procedural_timeline(case_id, db) if db else get_procedural_timeline(case_id, None)
    
    compliance_blockers = []
    if "error" not in timeline_report:
        for item in timeline_report.get("timeline", []):
            if item["status"] == "non_compliant" or item["is_overdue"]:
                compliance_blockers.append({
                    "requirement_id": item["requirement_id"],
                    "title": item["title"],
                    "required_by": item["required_by"],
                    "severity": item["severity"],
                    "guidance": item["remediation_guidance"],
                })

    # 6. Calculate Readiness Score
    # We score 0-100% based on:
    # - Charges status (fully satisfied = 100%, partially = 50%, unsatisfied = 0%)
    # - Compliance blockers (each blocker subtracts 10%, critical blocker sets overall score to 0)
    charge_score = 0.0
    if applicable_charges:
        charge_score = sum(
            1.0 if c["status"] == "fully_satisfied" else 0.5 if c["status"] == "partially_satisfied" else 0.0
            for c in applicable_charges
        ) / len(applicable_charges)
    else:
        charge_score = 0.0

    overall_score = charge_score * 1.0
    critical_blocker_present = False

    for cb in compliance_blockers:
        if cb["severity"] == "critical":
            critical_blocker_present = True
        else:
            overall_score = max(0.0, overall_score - 0.1)

    if critical_blocker_present or not applicable_charges:
        overall = 0.0
    else:
        overall = round(overall_score, 2)

    # Readiness Tier
    if overall >= 0.8:
        readiness_tier = "ready_for_review"
    elif overall >= 0.6:
        readiness_tier = "near_ready"
    elif overall >= 0.4:
        readiness_tier = "developing"
    else:
        readiness_tier = "not_ready"

    # Narrative
    narrative = f"Chargesheet readiness is {readiness_tier} (Score: {overall * 100:.0f}%). "
    if critical_blocker_present:
        narrative += "Critical procedural compliance blockers are present, preventing legal readiness. "
    elif has_missing_elements:
        narrative += "Some legal elements are not fully covered by evidence. "
    else:
        narrative += "All charges are fully satisfied by verified evidence with zero compliance blockers."

    # Calculate compliance and element readiness percentages for frontend display
    total_timeline = 0
    compliant_count = 0
    if "error" not in timeline_report:
        timeline_items = timeline_report.get("timeline", [])
        total_timeline = len(timeline_items)
        compliant_count = sum(1 for item in timeline_items if item["status"] == "compliant")
    procedural_compliance_pct = int((compliant_count / total_timeline) * 100) if total_timeline > 0 else 100
    element_readiness_pct = int(charge_score * 100)

    report = {
        "report_id": report_id,
        "case_id": case_id,
        "generated_at": now,
        "overall_readiness_score": overall,
        "readiness_tier": readiness_tier,
        "procedural_compliance_percentage": procedural_compliance_pct,
        "element_readiness_percentage": element_readiness_pct,
        "applicable_charges": applicable_charges,
        "compliance_blockers": compliance_blockers,
        "certificates": certificates_list,
        "accused": accused_list,
        "prosecution_theory": theory_summary,
        "unsupported_allegations": unsupported_allegations,
        "summary_narrative": narrative,
        "disclaimer": "Advisory only. Final charging decisions require independent human prosecutorial assessment.",
    }

    # Store in Neo4j (as ChargesheetReadinessReport or specialized node type)
    client.execute_write(
        """
        CREATE (r:ChargesheetReadinessReport {
            id: $rid, case_id: $cid, generated_at: $now,
            overall_readiness_score: $score,
            readiness_tier: $tier,
            summary_narrative: $narr,
            report_data: $data,
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "rid": report_id, "cid": case_id, "now": now,
            "score": overall, "tier": readiness_tier,
            "narr": narrative, "data": json.dumps(report, default=str),
        },
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Chargesheet intelligence report generated: {readiness_tier} (score={overall:.2f})",
            actor="system:chargesheet_intelligence",
            graph_refs=[report_id],
        )
        db.commit()

    return report


def _build_allegation_breakdown(client, case_id: str, section_data: dict) -> dict:
    """Build per-allegation evidence breakdown for a charge section."""
    section_id = section_data["section_id"]

    # Supporting witnesses
    witnesses = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})
        WHERE p.status IN ['witness', 'victim', 'informant']
        OPTIONAL MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['witness_statements', 'victim_statement']
        RETURN DISTINCT p.id AS person_id, coalesce(p.display_name, p.id) AS name,
               p.status AS role
        """,
        {"cid": case_id, "sid": section_id},
    )
    supporting_witnesses = [
        {"person_id": w["person_id"], "name": w["name"], "role": w.get("role", "witness")}
        for w in witnesses
    ]

    # Supporting digital artifacts
    digital_artifacts = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['device_seizure', 'digital_forensics', 'network_logs',
                                   'access_logs', 'account_activity_logs']
        RETURN DISTINCT m.evidence_ref AS ref, m.evidence_type AS type,
               m.chain_of_custody_status AS coc_status
        """,
        {"cid": case_id, "sid": section_id},
    )
    supporting_digital = [
        {"evidence_ref": d["ref"], "type": d.get("type", ""),
         "integrity_status": d.get("coc_status", "unverified")}
        for d in digital_artifacts
    ]

    # Financial support
    financial = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['financial_records', 'transaction_logs', 'bank_statements']
        RETURN DISTINCT m.evidence_ref AS ref, m.evidence_type AS type
        """,
        {"cid": case_id, "sid": section_id},
    )
    financial_support = [
        {"evidence_ref": f["ref"], "type": f.get("type", "")}
        for f in financial
    ]

    # Communication support
    comms = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['communication_records', 'threat_evidence']
        RETURN DISTINCT m.evidence_ref AS ref, m.evidence_type AS type
        """,
        {"cid": case_id, "sid": section_id},
    )
    communication_support = [
        {"evidence_ref": c["ref"], "type": c.get("type", "")}
        for c in comms
    ]

    # Documentary support
    docs = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['documentary_evidence', 'contractual_agreements',
                                   'ownership_records', 'document_analysis']
        RETURN DISTINCT m.evidence_ref AS ref, m.evidence_type AS type
        """,
        {"cid": case_id, "sid": section_id},
    )
    supporting_documents = [
        {"evidence_ref": d["ref"], "type": d.get("type", "")}
        for d in docs
    ]

    # Forensic reports
    forensics = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[:SATISFIES_ELEMENT]->(le:LegalElement)
              <-[:HAS_ELEMENT]-(ls:LegalSection {id: $sid})
        WHERE m.evidence_type IN ['expert_opinion', 'laboratory_report', 'malware_analysis',
                                   'integrity_certificate']
        RETURN DISTINCT m.evidence_ref AS ref, m.evidence_type AS type
        """,
        {"cid": case_id, "sid": section_id},
    )
    supporting_forensic_reports = [
        {"evidence_ref": f["ref"], "type": f.get("type", "")}
        for f in forensics
    ]

    return {
        "supporting_witnesses": supporting_witnesses,
        "supporting_digital_artifacts": supporting_digital,
        "supporting_documents": supporting_documents,
        "supporting_forensic_reports": supporting_forensic_reports,
        "financial_support": financial_support,
        "communication_support": communication_support,
    }
