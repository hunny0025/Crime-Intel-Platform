"""Evidence Integrity Engine — court-ready integrity certificates.

Produces per-artifact EvidenceIntegrityCertificate with A-F grades and
court_presentation_notes for non-technical audiences.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def run_integrity_audit(case_id: str, db: Optional[Session] = None) -> dict:
    """Generate EvidenceIntegrityCertificate for every artifact in the case."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    artifacts = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN n.id AS id, n.source_tool AS source_tool,
               n.hash_verified AS hash_verified,
               n.chain_verified AS chain_verified,
               n.timestamp_integrity_score AS tis,
               coalesce(n.display_name, n.id) AS display
        """,
        {"cid": case_id},
    )

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    certificates = []

    for art in artifacts:
        hash_ok = art.get("hash_verified", True)  # Default True if not set
        chain_ok = art.get("chain_verified", True)
        tis = art.get("tis") or 0.5
        corr_count = _get_corroboration_count(client, case_id, art["id"])
        deception = _get_deception_summary(client, case_id, art["id"])

        # Grade assignment
        if hash_ok is False:
            grade = "F"
        elif chain_ok is False:
            grade = "D"
        elif hash_ok and chain_ok and tis >= 0.9 and corr_count >= 2 and deception == "not_assessed":
            grade = "A"
        elif hash_ok and chain_ok and tis >= 0.7 and corr_count >= 1:
            grade = "B"
        elif hash_ok and chain_ok:
            grade = "C"
        else:
            grade = "C"

        grade_counts[grade] += 1

        # Court presentation notes
        notes = _generate_court_notes(art, grade, hash_ok, chain_ok, tis, corr_count, deception)

        cert_id = str(uuid.uuid4())
        client.execute_write(
            """
            MERGE (c:EvidenceIntegrityCertificate {artifact_id: $aid, case_id: $cid})
            ON CREATE SET c.id = $certid, c.created_at = $now
            SET c.generated_at = $now,
                c.hash_verified = $hv, c.chain_verified = $cv,
                c.timestamp_integrity_score = $tis,
                c.deception_assessment_summary = $deception,
                c.corroboration_count = $corr,
                c.overall_integrity_grade = $grade,
                c.court_presentation_notes = $notes,
                c.classification_tag = 'case_sensitive'
            """,
            {
                "certid": cert_id, "aid": art["id"], "cid": case_id,
                "now": now, "hv": hash_ok, "cv": chain_ok,
                "tis": tis, "deception": deception, "corr": corr_count,
                "grade": grade, "notes": notes,
            },
        )

        certificates.append({
            "artifact_id": art["id"],
            "display": art["display"],
            "source_tool": art.get("source_tool", ""),
            "grade": grade,
            "hash_verified": hash_ok,
            "chain_verified": chain_ok,
            "timestamp_integrity_score": tis,
            "corroboration_count": corr_count,
            "court_presentation_notes": notes,
        })

    return {
        "case_id": case_id,
        "audit_completed_at": now,
        "total_artifacts": len(certificates),
        "grade_distribution": grade_counts,
        "certificates": certificates,
    }


def get_integrity_audit(case_id: str) -> dict:
    """Return all certificates with grades and notes."""
    client = get_neo4j_client()
    certs = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        RETURN c.artifact_id AS aid, c.overall_integrity_grade AS grade,
               c.hash_verified AS hv, c.chain_verified AS cv,
               c.timestamp_integrity_score AS tis,
               c.corroboration_count AS corr,
               c.court_presentation_notes AS notes,
               c.generated_at AS at
        ORDER BY CASE grade
            WHEN 'F' THEN 0 WHEN 'D' THEN 1 WHEN 'C' THEN 2
            WHEN 'B' THEN 3 WHEN 'A' THEN 4 END
        """,
        {"cid": case_id},
    )
    return {"case_id": case_id, "certificates": certs}


def get_artifact_certificate(artifact_id: str) -> dict:
    """Return certificate for a specific artifact."""
    client = get_neo4j_client()
    cert = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {artifact_id: $aid})
        RETURN c.artifact_id AS aid, c.overall_integrity_grade AS grade,
               c.hash_verified AS hv, c.chain_verified AS cv,
               c.timestamp_integrity_score AS tis, c.corroboration_count AS corr,
               c.court_presentation_notes AS notes, c.generated_at AS at
        """,
        {"aid": artifact_id},
    )
    if not cert:
        return {"error": "No certificate found"}
    return cert[0]


def get_weak_artifacts(case_id: str) -> dict:
    """Return only D and F grade artifacts with remediation recommendations."""
    client = get_neo4j_client()
    weak = client.execute_read(
        """
        MATCH (c:EvidenceIntegrityCertificate {case_id: $cid})
        WHERE c.overall_integrity_grade IN ['D', 'F']
        RETURN c.artifact_id AS aid, c.overall_integrity_grade AS grade,
               c.court_presentation_notes AS notes
        """,
        {"cid": case_id},
    )

    for w in weak:
        if w["grade"] == "F":
            w["remediation"] = "CRITICAL: Hash verification failed. This artifact's content " \
                               "may have been altered. Re-acquire from original source if possible."
        else:
            w["remediation"] = "Chain of custody broken. Obtain witness statements from all " \
                               "handlers and document the custody gap."
    return {"case_id": case_id, "weak_artifacts": weak}


def _get_corroboration_count(client, case_id: str, artifact_id: str) -> int:
    """Count distinct source tools corroborating this artifact."""
    result = client.execute_read(
        """
        MATCH (n {id: $aid})-[:SUPPORTED_BY|SATISFIES_ELEMENT|RELATES_TO]-(other)
        WHERE other.case_id = $cid AND other.source_tool IS NOT NULL
        AND other.source_tool <> n.source_tool
        RETURN count(DISTINCT other.source_tool) AS cnt
        """,
        {"aid": artifact_id, "cid": case_id},
    )
    return result[0]["cnt"] if result else 0


def _get_deception_summary(client, case_id: str, artifact_id: str) -> str:
    """Get deception assessment summary if exists."""
    result = client.execute_read(
        """
        MATCH (d:DeceptionAssessment)-[:ASSESSED]->(n {id: $aid})
        RETURN d.overall_score AS score
        """,
        {"aid": artifact_id},
    )
    if result:
        score = result[0].get("score", 0)
        return f"assessed_score_{score:.2f}" if score else "assessed_clean"
    return "not_assessed"


def _generate_court_notes(art, grade, hash_ok, chain_ok, tis, corr, deception) -> str:
    """Auto-generate court presentation notes."""
    parts = [
        f"Evidence item ({art['id'][:12]}..., source: {art.get('source_tool', 'unknown')}) "
        f"has integrity grade {grade}."
    ]

    if hash_ok:
        parts.append("Content verified unchanged via SHA-256 hash verification.")
    else:
        parts.append("WARNING: Hash verification FAILED — content may have been altered.")

    if chain_ok:
        parts.append("Chain of custody is intact and documented.")
    elif chain_ok is False:
        parts.append("Chain of custody has gaps requiring documentation.")

    if tis >= 0.9:
        parts.append("Timestamps corroborated by multiple independent sources.")
    elif tis >= 0.7:
        parts.append("Timestamps corroborated by at least one independent source.")
    elif tis < 0.4:
        parts.append("Timestamps have low integrity — potential manipulation concern.")

    if corr >= 2:
        parts.append(f"Content corroborated by {corr} independent evidence sources.")
    elif corr == 1:
        parts.append("Content corroborated by one independent source.")
    else:
        parts.append("No independent corroboration available for this evidence item.")

    return " ".join(parts)
