"""Court Readiness Engine — synthesizes integrity, defense, and legal readiness.

overall_court_score = 0.4×legal + 0.3×integrity + 0.3×(1-defense_vulnerability).
F-grade artifact → score 0.0. Section 65B non-compliant → capped at 0.4.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.court.defense_simulator import run_defense_simulation
from app.court.integrity_engine import run_integrity_audit
from app.legal.chargesheet_engine import get_chargesheet_readiness
from app.legal.procedural_engine import check_section_65b

logger = logging.getLogger(__name__)


def generate_court_readiness(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate CourtReadinessReport."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    report_id = str(uuid.uuid4())

    # Run integrity audit
    integrity = run_integrity_audit(case_id, db)
    grade_dist = integrity.get("grade_distribution", {})

    # Run defense simulation
    defense = run_defense_simulation(case_id, db)
    defense_summary = defense.get("summary", {})
    vulnerability = defense.get("overall_vulnerability_score", 0)

    # Get legal readiness
    legal = get_chargesheet_readiness(case_id)
    legal_score = legal.get("overall_readiness_score", 0)

    # Section 65B status
    s65b = check_section_65b(case_id)
    s65b_status = s65b.get("status", "not_applicable")

    # Compute integrity contribution
    total_artifacts = sum(grade_dist.values())
    ab_count = grade_dist.get("A", 0) + grade_dist.get("B", 0)
    d_count = grade_dist.get("D", 0)
    f_count = grade_dist.get("F", 0)

    integrity_fraction = ab_count / total_artifacts if total_artifacts > 0 else 0
    # D-grade penalty
    for _ in range(d_count):
        integrity_fraction *= 0.8
    # F-grade is fatal
    if f_count > 0:
        integrity_fraction = 0.0

    # Defense vulnerability contribution
    defense_contribution = max(
        1.0 - (0.5 * defense_summary.get("critical", 0) +
               0.2 * defense_summary.get("major", 0)) /
        max(total_artifacts, 1),
        0.0,
    )

    # Digital evidence quality score (separate dimension)
    digital_quality = _compute_digital_evidence_quality(client, case_id)

    # Chain of custody integrity score (separate dimension)
    chain_of_custody_score = _compute_chain_of_custody_score(client, case_id)

    # Witness strength score
    witness_strength = _compute_witness_strength(client, case_id)

    # 6-dimension scoring formula:
    # 0.25×legal + 0.20×integrity + 0.20×(1-defense_vulnerability)
    # + 0.15×digital_quality + 0.10×chain_of_custody + 0.10×witness_strength
    overall = (
        0.25 * legal_score +
        0.20 * integrity_fraction +
        0.20 * defense_contribution +
        0.15 * digital_quality +
        0.10 * chain_of_custody_score +
        0.10 * witness_strength
    )

    # Fatal overrides
    critical_issues = []

    if f_count > 0:
        overall = 0.0
        critical_issues.append(
            f"{f_count} artifact(s) with grade F — hash verification failed"
        )

    if s65b_status == "non_compliant":
        overall = min(overall, 0.4)
        critical_issues.append("Section 65B BSA 2023 certificate not confirmed")

    # Blockers from chargesheet readiness
    for blocker in legal.get("critical_blockers", []):
        critical_issues.append(blocker)
        overall = 0.0

    # Determine tier
    if overall >= 0.8:
        tier = "court_ready"
    elif overall >= 0.6:
        tier = "substantially_ready"
    elif overall >= 0.4:
        tier = "needs_work"
    else:
        tier = "not_court_ready"


    # Preparation checklist
    checklist = _generate_checklist(
        critical_issues, grade_dist, defense.get("attack_vectors", []),
        case_id, client,
    )

    # Build Witness Matrix
    witnesses_data = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})
        WHERE p.role = 'witness' OR (p)-[:PARTICIPATED_IN]->(:Event {event_type: 'statement'})
        OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(e:Event {event_type: 'statement'})
        RETURN p.id AS person_id, coalesce(p.display_name, p.id) AS name, p.role AS role,
               e.id AS statement_id, e.description AS statement_text, e.valid_from AS timestamp
        """,
        {"cid": case_id}
    )
    witness_matrix = []
    seen_witnesses = set()
    for w in witnesses_data:
        witness_id = w["person_id"]
        if witness_id not in seen_witnesses:
            seen_witnesses.add(witness_id)
            witness_matrix.append({
                "witness_id": witness_id,
                "name": w["name"],
                "role": w["role"],
                "statements": []
            })
        if w["statement_id"]:
            for entry in witness_matrix:
                if entry["witness_id"] == witness_id:
                    entry["statements"].append({
                        "statement_id": w["statement_id"],
                        "summary": w["statement_text"],
                        "timestamp": w["timestamp"],
                    })

    # Build Document Matrix
    document_matrix = []
    if db:
        from app.db.models import EvidenceArtifact
        import uuid as pyuuid
        db_artifacts = db.query(EvidenceArtifact).filter(EvidenceArtifact.case_id == pyuuid.UUID(case_id)).all()

        certificates = client.execute_read(
            """
            MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
            RETURN c.id AS cert_id, c.evidence_ref AS evidence_ref,
                   c.overall_integrity_grade AS grade, c.generated_at AS certified_at
            """,
            {"cid": case_id}
        )
        cert_map = {c["evidence_ref"]: c for c in certificates}

        for art in db_artifacts:
            art_id_str = str(art.artifact_id)
            cert = cert_map.get(art_id_str)
            document_matrix.append({
                "artifact_id": art_id_str,
                "source_tool": art.source_tool,
                "content_hash": art.content_hash,
                "content_pointer": art.content_pointer,
                "certificate": {
                    "certificate_id": cert["cert_id"],
                    "grade": cert["grade"],
                    "certified_at": cert["certified_at"],
                } if cert else None
            })

    report = {
        "report_id": report_id,
        "case_id": case_id,
        "generated_at": now,
        "overall_court_score": round(overall, 4),
        "readiness_tier": tier,
        "evidence_integrity_summary": grade_dist,
        "defense_vulnerability_summary": defense_summary,
        "legal_readiness_score": legal_score,
        "section_65b_status": s65b_status,
        "critical_issues": critical_issues,
        "preparation_checklist": checklist,
        "checklist": checklist,
        "witness_matrix": witness_matrix,
        "document_matrix": document_matrix,
    }

    client.execute_write(
        """
        CREATE (r:CourtReadinessReport {
            id: $rid, case_id: $cid, generated_at: $now,
            overall_court_score: $score, readiness_tier: $tier,
            report_data: $data,
            classification_tag: 'case_sensitive', created_at: $now
        })
        """,
        {
            "rid": report_id, "cid": case_id, "now": now,
            "score": overall, "tier": tier,
            "data": json.dumps(report, default=str),
        },
    )

    return report


def get_court_readiness(case_id: str) -> dict:
    """Return latest court readiness report."""
    client = get_neo4j_client()
    r = client.execute_read(
        """
        MATCH (r:CourtReadinessReport {case_id: $cid})
        RETURN r.report_data AS data
        ORDER BY r.generated_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    if not r or not r[0].get("data"):
        return {"error": "No court readiness report found"}
    return json.loads(r[0]["data"])


def get_preparation_checklist(case_id: str) -> dict:
    """Return only the preparation checklist."""
    report = get_court_readiness(case_id)
    return {
        "case_id": case_id,
        "checklist": report.get("preparation_checklist", []),
    }


def _generate_checklist(critical_issues, grade_dist, attack_vectors,
                        case_id, client) -> list[dict]:
    """Generate ordered preparation checklist."""
    checklist = []
    priority = 0

    # Critical issues first
    for issue in critical_issues:
        priority += 1
        checklist.append({
            "priority": priority,
            "category": "CRITICAL",
            "description": f"CRITICAL: {issue} — resolving this is required before proceeding",
            "estimated_impact": "blocking",
        })

    # D-grade artifacts
    d_count = grade_dist.get("D", 0)
    if d_count > 0:
        priority += 1
        checklist.append({
            "priority": priority,
            "category": "integrity",
            "description": f"Strengthen chain of custody for {d_count} artifact(s) "
                           f"with grade D — reduces integrity score",
            "estimated_impact": "high",
        })

    # Critical defense vectors
    critical_vectors = [v for v in attack_vectors if v.get("severity") == "critical"]
    for v in critical_vectors[:3]:
        priority += 1
        checklist.append({
            "priority": priority,
            "category": "defense_vulnerability",
            "description": f"Address defense vulnerability: {v['description'][:80]}",
            "recommended_counter": v.get("recommended_counter", ""),
            "estimated_impact": "high",
        })

    # Unsatisfied elements with open gaps
    gaps = client.execute_read(
        """
        MATCH (g:EvidenceGap {case_id: $cid, status: 'open'})
        RETURN g.description AS desc
        LIMIT 5
        """,
        {"cid": case_id},
    )
    for g in gaps:
        priority += 1
        checklist.append({
            "priority": priority,
            "category": "evidence_gap",
            "description": f"Pursue evidence: {g['desc'][:80]}",
            "estimated_impact": "medium",
        })

    return checklist


def _compute_digital_evidence_quality(client, case_id: str) -> float:
    """Score digital evidence quality based on integrity certificates and BSA compliance."""
    certs = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        RETURN c.overall_integrity_grade AS grade
        """,
        {"cid": case_id},
    )
    if not certs:
        return 0.5  # Default when no digital evidence is present

    grade_scores = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.3, "F": 0.0}
    total = 0.0
    for c in certs:
        total += grade_scores.get(c.get("grade", "C"), 0.5)
    return total / len(certs)


def _compute_chain_of_custody_score(client, case_id: str) -> float:
    """Aggregate chain-of-custody integrity across all evidence mappings."""
    mappings = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})
        RETURN m.chain_of_custody_status AS coc
        """,
        {"cid": case_id},
    )
    if not mappings:
        return 0.5

    coc_scores = {"intact": 1.0, "unverified": 0.5, "broken": 0.0}
    total = sum(coc_scores.get(m.get("coc", "unverified"), 0.5) for m in mappings)
    return total / len(mappings)


def _compute_witness_strength(client, case_id: str) -> float:
    """Score witness strength based on count and statement availability."""
    witnesses = client.execute_read(
        """
        MATCH (p:Person {case_id: $cid})
        WHERE p.role = 'witness' OR p.status = 'witness'
        OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(e:Event {event_type: 'statement'})
        RETURN p.id AS pid, count(e) AS stmt_count
        """,
        {"cid": case_id},
    )
    if not witnesses:
        return 0.3

    with_statements = sum(1 for w in witnesses if w.get("stmt_count", 0) > 0)
    total = len(witnesses)

    # Score: base from having witnesses + bonus for statements
    base = min(total / 5.0, 1.0)  # Up to 5 witnesses = full base
    stmt_bonus = (with_statements / total) * 0.3 if total > 0 else 0
    return min(base * 0.7 + stmt_bonus, 1.0)
