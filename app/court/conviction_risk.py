"""Conviction Risk Analysis Engine — risk factor profiling.

NOT a prediction of guilt. An assessment of evidential case strength
as it would appear to a court given current evidence quality.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def generate_conviction_risk(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate ConvictionRiskProfile."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())

    risk_factors = []

    # ── Decreases risk (makes conviction more likely) ────────────────────

    # Multiple Grade A evidence
    grade_a = client.execute_read(
        "MATCH (c:EvidenceIntegrityCertificate {case_id: $cid}) "
        "WHERE c.overall_integrity_grade = 'A' RETURN count(c) AS cnt",
        {"cid": case_id},
    )
    a_count = grade_a[0]["cnt"] if grade_a else 0
    if a_count >= 2:
        risk_factors.append({
            "factor_type": "multiple_grade_a_evidence",
            "description": f"{a_count} Grade A evidence items with full corroboration",
            "direction": "decreases_risk",
            "weight": 0.15,
        })

    # All elements satisfied for at least one section
    full_sections = client.execute_read(
        """
        MATCH (q:LegalQualification {case_id: $cid})
        WHERE q.element_coverage = 1.0 AND q.qualification_score >= 0.8
        RETURN count(q) AS cnt
        """,
        {"cid": case_id},
    )
    if full_sections and full_sections[0]["cnt"] > 0:
        risk_factors.append({
            "factor_type": "full_element_coverage",
            "description": "At least one section has all elements fully satisfied",
            "direction": "decreases_risk",
            "weight": 0.2,
        })

    # Zero critical defense vectors
    critical_defense = client.execute_read(
        """
        MATCH (d:DefenseSimulation {case_id: $cid})
        WHERE d.overall_vulnerability_score = 0
        RETURN count(d) AS cnt
        """,
        {"cid": case_id},
    )
    no_critical_defense = critical_defense and critical_defense[0]["cnt"] > 0
    if no_critical_defense:
        risk_factors.append({
            "factor_type": "no_critical_defense_vectors",
            "description": "No critical defense attack vectors identified",
            "direction": "decreases_risk",
            "weight": 0.15,
        })

    # Eliminated competing hypotheses
    eliminated = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid, status: 'eliminated'}) "
        "RETURN count(h) AS cnt",
        {"cid": case_id},
    )
    elim_count = eliminated[0]["cnt"] if eliminated else 0
    if elim_count > 0:
        risk_factors.append({
            "factor_type": "eliminated_alternatives",
            "description": f"{elim_count} alternative hypothesis(es) eliminated — "
                           f"thorough investigation demonstrated",
            "direction": "decreases_risk",
            "weight": 0.1,
        })

    # Section 65B compliant
    s65b = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {
            case_id: $cid, requirement_id: 'section_65b_bsa_2023'
        })
        WHERE r.status = 'compliant'
        RETURN count(r) AS cnt
        """,
        {"cid": case_id},
    )
    if s65b and s65b[0]["cnt"] > 0:
        risk_factors.append({
            "factor_type": "section_65b_compliant",
            "description": "Section 65B BSA 2023 certificate confirmed",
            "direction": "decreases_risk",
            "weight": 0.1,
        })

    # ── Increases risk (makes conviction less likely) ────────────────────

    # Grade D/F evidence
    weak_evidence = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        WHERE c.overall_integrity_grade IN ['D', 'F']
        RETURN c.overall_integrity_grade AS grade, count(c) AS cnt
        """,
        {"cid": case_id},
    )
    for w in (weak_evidence or []):
        weight = 0.3 if w["grade"] == "F" else 0.15
        risk_factors.append({
            "factor_type": f"grade_{w['grade'].lower()}_evidence",
            "description": f"{w['cnt']} Grade {w['grade']} evidence item(s)",
            "direction": "increases_risk",
            "weight": weight,
        })

    # Active competing hypothesis > 0.15
    competing = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        WHERE h.probability > 0.15
        WITH h ORDER BY h.probability DESC
        SKIP 1
        RETURN h.narrative AS narrative, h.probability AS prob
        """,
        {"cid": case_id},
    )
    for c in (competing or []):
        risk_factors.append({
            "factor_type": "active_competing_hypothesis",
            "description": f"Active alternative: '{c['narrative'][:50]}' "
                           f"(probability {c['prob']:.2f}) — reasonable doubt risk",
            "direction": "increases_risk",
            "weight": 0.2,
        })

    # Missing elements
    missing = client.execute_read(
        """
        MATCH (q:LegalQualification {case_id: $cid})
        WHERE q.missing_elements IS NOT NULL AND q.missing_elements <> '[]'
        RETURN q.missing_elements AS missing
        """,
        {"cid": case_id},
    )
    for m in (missing or []):
        parsed = json.loads(m.get("missing", "[]").replace("'", '"')) if m.get("missing") else []
        if parsed:
            risk_factors.append({
                "factor_type": "missing_elements",
                "description": f"{len(parsed)} legal element(s) without evidence",
                "direction": "increases_risk",
                "weight": 0.1,
            })

    # Procedural non-compliance (critical)
    proc_nc = client.execute_read(
        """
        MATCH (r:ProceduralComplianceRecord {case_id: $cid})
        WHERE r.status = 'non_compliant' AND r.non_compliance_severity = 'critical'
        RETURN count(r) AS cnt
        """,
        {"cid": case_id},
    )
    if proc_nc and proc_nc[0]["cnt"] > 0:
        risk_factors.append({
            "factor_type": "critical_procedural_non_compliance",
            "description": f"{proc_nc[0]['cnt']} critical procedural requirement(s) not met",
            "direction": "increases_risk",
            "weight": 0.25,
        })

    # Aggregate risk score
    decreases = sum(f["weight"] for f in risk_factors if f["direction"] == "decreases_risk")
    increases = sum(f["weight"] for f in risk_factors if f["direction"] == "increases_risk")
    risk_score = max(0, min(1.0, 0.5 + increases - decreases))

    # Confidence in assessment
    total_factors = len(risk_factors)
    confidence = min(total_factors / 8.0, 1.0)  # 8+ factors = full confidence

    profile = {
        "profile_id": profile_id,
        "case_id": case_id,
        "generated_at": now,
        "risk_factors": risk_factors,
        "aggregated_risk_score": round(risk_score, 4),
        "confidence_in_assessment": round(confidence, 4),
    }

    client.execute_write(
        """
        CREATE (r:ConvictionRiskProfile {
            id: $pid, case_id: $cid, generated_at: $now,
            aggregated_risk_score: $score,
            confidence_in_assessment: $conf,
            report_data: $data,
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "pid": profile_id, "cid": case_id, "now": now,
            "score": risk_score, "conf": confidence,
            "data": json.dumps(profile, default=str),
        },
    )

    return profile


def get_conviction_risk(case_id: str) -> dict:
    """Return latest conviction risk profile."""
    client = get_neo4j_client()
    r = client.execute_read(
        """
        MATCH (r:ConvictionRiskProfile {case_id: $cid})
        RETURN r.report_data AS data
        ORDER BY r.generated_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    if not r or not r[0].get("data"):
        return {"error": "No conviction risk profile found"}
    return json.loads(r[0]["data"])
