"""Probabilistic Reasoning Engine — uncertainty quantification across evidence chains.

Handles confidence degradation along inference hops, absence likelihood ratios,
and timestamp integrity scoring.
"""

import math
import json
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

# Confidence decay per inference hop
DEFAULT_DECAY_FACTOR = 0.85


def get_chain_confidence(
    case_id: str,
    relationship_id: str,
    decay_factor: float = DEFAULT_DECAY_FACTOR,
) -> dict:
    """
    Compute confidence chain from a relationship back to its root evidence.

    Confidence degrades per inference hop:
    - Direct observation (1 hop): confidence * 1.0
    - OSINT-derived: confidence as-is (≤0.8)
    - Each additional hop: × decay_factor
    """
    client = get_neo4j_client()

    # Get the relationship and its confidence
    rel = client.execute_read(
        """
        MATCH ()-[r]->()
        WHERE id(r) = $rid OR r.id = $rid
        RETURN r.confidence AS conf, r.evidence_basis AS eb,
               r.classification_tag AS tag, type(r) AS rel_type
        LIMIT 1
        """,
        {"rid": relationship_id},
    )

    if not rel:
        return {"chain_confidence": 0.0, "error": "Relationship not found"}

    base_conf = rel[0].get("conf", 1.0) or 1.0
    tag = rel[0].get("tag", "")
    evidence_basis = rel[0].get("eb", []) or []

    # Count inference hops (simplified: OSINT = 1 hop, direct = 0 hops)
    hops = 0
    if tag == "public_osint":
        hops = 1  # OSINT adds one indirection layer

    # Check evidence basis chain depth
    if evidence_basis:
        # Each evidence_basis item might reference another relationship
        hops += 1  # At minimum one hop from artifact to assertion

    chain_conf = base_conf * (decay_factor ** hops)

    return {
        "relationship_id": relationship_id,
        "base_confidence": base_conf,
        "hops": hops,
        "decay_factor": decay_factor,
        "chain_confidence": round(chain_conf, 4),
        "classification_tag": tag,
    }


# ── Absence Likelihood Ratio ────────────────────────────────────────────

# Default base rates for evidence generation
DEFAULT_ABSENCE_RATES = {
    "CellTowerPing": {"p_gen_innocent": 0.95, "p_gen_guilty": 0.05},
    "GPSRecord": {"p_gen_innocent": 0.90, "p_gen_guilty": 0.10},
    "CCTVFrame": {"p_gen_innocent": 0.80, "p_gen_guilty": 0.15},
    "CommunicationRecord": {"p_gen_innocent": 0.70, "p_gen_guilty": 0.30},
    "FinancialRecord": {"p_gen_innocent": 0.85, "p_gen_guilty": 0.20},
}


def compute_alr(evidence_type: str, db: Session = None) -> dict:
    """
    Compute Absence Likelihood Ratio for a missing evidence type.

    ALR = P(absent|guilty) / P(absent|innocent)
        = (1 - P_gen_guilty) / (1 - P_gen_innocent)

    ALR > 1 → absence more consistent with guilt (suppression)
    ALR < 1 → absence more consistent with innocence
    """
    # Try database rates first
    rates = None
    if db:
        try:
            row = db.execute(
                sql_text("SELECT p_gen_innocent, p_gen_guilty FROM absence_base_rates "
                         "WHERE evidence_type = :et"),
                {"et": evidence_type},
            ).first()
            if row:
                rates = {"p_gen_innocent": row[0], "p_gen_guilty": row[1]}
        except Exception:
            pass

    if not rates:
        rates = DEFAULT_ABSENCE_RATES.get(evidence_type,
                                          {"p_gen_innocent": 0.5, "p_gen_guilty": 0.5})

    p_absent_innocent = 1.0 - rates["p_gen_innocent"]
    p_absent_guilty = 1.0 - rates["p_gen_guilty"]

    # Avoid division by zero
    alr = p_absent_guilty / p_absent_innocent if p_absent_innocent > 0 else float('inf')

    return {
        "evidence_type": evidence_type,
        "p_gen_innocent": rates["p_gen_innocent"],
        "p_gen_guilty": rates["p_gen_guilty"],
        "p_absent_innocent": round(p_absent_innocent, 4),
        "p_absent_guilty": round(p_absent_guilty, 4),
        "alr": round(alr, 4),
        "interpretation": (
            "absence more consistent with suppression/guilt" if alr > 1
            else "absence more consistent with innocence" if alr < 1
            else "neutral"
        ),
    }


# ── Timestamp Integrity Scoring ─────────────────────────────────────────

def compute_timestamp_integrity(case_id: str, relationship_id: str) -> dict:
    """
    Compute timestamp integrity score for an AT/COMMUNICATED_WITH relationship.

    1.0 = corroborated by 2+ independent sources
    0.7 = corroborated by 1 source
    0.4 = single source (no corroboration)
    0.1 = inconsistent with another source (potential timestomping)
    """
    client = get_neo4j_client()

    # Get the relationship's participants and timestamp
    rel = client.execute_read(
        """
        MATCH (a)-[r]->(b)
        WHERE r.id = $rid
        RETURN a.id AS from_id, b.id AS to_id,
               r.valid_from AS ts, type(r) AS rtype,
               r.evidence_basis AS eb
        LIMIT 1
        """,
        {"rid": relationship_id},
    )

    if not rel:
        return {"score": 0.4, "basis": "relationship_not_found"}

    r = rel[0]
    ts = r.get("ts")
    from_id = r.get("from_id")
    to_id = r.get("to_id")

    if not ts:
        return {"score": 0.4, "basis": "no_timestamp"}

    # Find corroborating relationships (same entities, similar time window)
    corroborating = client.execute_read(
        """
        MATCH (a {id: $fid})-[r2]->(b)
        WHERE r2.id <> $rid
        AND r2.valid_from IS NOT NULL
        AND abs(duration.between(datetime(r2.valid_from), datetime($ts)).seconds) < 3600
        RETURN count(r2) AS cnt
        """,
        {"fid": from_id, "rid": relationship_id, "ts": str(ts)},
    )

    # Find contradicting timestamps
    contradicting = client.execute_read(
        """
        MATCH (a {id: $fid})-[r2:AT]->(other_loc)
        WHERE r2.id <> $rid
        AND other_loc.id <> $tid
        AND r2.valid_from IS NOT NULL
        AND abs(duration.between(datetime(r2.valid_from), datetime($ts)).seconds) < 1800
        RETURN count(r2) AS cnt
        """,
        {"fid": from_id, "rid": relationship_id, "tid": to_id, "ts": str(ts)},
    )

    corr_count = corroborating[0]["cnt"] if corroborating else 0
    contra_count = contradicting[0]["cnt"] if contradicting else 0

    if contra_count > 0:
        score = 0.1
        basis = "inconsistent_with_other_source"
    elif corr_count >= 2:
        score = 1.0
        basis = f"corroborated_by_{corr_count}_sources"
    elif corr_count == 1:
        score = 0.7
        basis = "corroborated_by_1_source"
    else:
        score = 0.4
        basis = "single_source"

    # Store on the relationship
    try:
        client.execute_write(
            "MATCH ()-[r {id: $rid}]->() SET r.timestamp_integrity_score = $score",
            {"rid": relationship_id, "score": score},
        )
    except Exception:
        pass

    return {
        "relationship_id": relationship_id,
        "score": score,
        "basis": basis,
        "corroborating_count": corr_count,
        "contradicting_count": contra_count,
    }


def generate_confidence_report(case_id: str, db: Session = None) -> dict:
    """
    For each active Hypothesis, return:
    - probability
    - top 5 supporting evidence chain confidence values
    - ALR contributions from absent evidence
    - overall evidence quality score
    """
    client = get_neo4j_client()
    from app.reasoning.hpl.grammar import check_implied_evidence_status

    hypotheses = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'active'})
        RETURN h.id AS id, h.probability AS prob, h.narrative AS narrative,
               h.implied_evidence AS implied
        ORDER BY h.probability DESC
        """,
        {"cid": case_id},
    )

    report = []
    for h in hypotheses:
        # Get supporting evidence chain confidences
        supporting = client.execute_read(
            """
            MATCH (h:Hypothesis {id: $hid})<-[s:SUPPORTED_BY]-(n)
            RETURN n.id AS id, s.confidence AS conf,
                   coalesce(n.display_name, n.event_type, n.id) AS display
            ORDER BY s.confidence DESC
            LIMIT 5
            """,
            {"hid": h["id"]},
        )

        chain_confs = [s.get("conf", 0.5) for s in supporting]
        quality_score = sum(chain_confs) / len(chain_confs) if chain_confs else 0.0

        # ALR for absent evidence
        implied = json.loads(h.get("implied", "[]").replace("'", '"')) if h.get("implied") else []
        alr_contributions = []
        if implied:
            statuses = check_implied_evidence_status(case_id, implied)
            for item in statuses:
                if item["status"] == "absent":
                    alr = compute_alr(item["evidence_type"], db)
                    alr_contributions.append(alr)

        report.append({
            "hypothesis_id": h["id"],
            "probability": h["prob"],
            "narrative": h["narrative"],
            "top_evidence_chains": [
                {"evidence_id": s["id"], "display": s["display"],
                 "chain_confidence": s.get("conf", 0.5)}
                for s in supporting
            ],
            "alr_contributions": alr_contributions,
            "evidence_quality_score": round(quality_score, 4),
        })

    return {"case_id": case_id, "hypotheses": report}


def ensure_absence_base_rates_table(db: Session):
    """Create absence_base_rates table if not exists and seed defaults."""
    try:
        db.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS absence_base_rates (
                evidence_type VARCHAR(100) PRIMARY KEY,
                p_gen_innocent FLOAT NOT NULL,
                p_gen_guilty FLOAT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        for etype, rates in DEFAULT_ABSENCE_RATES.items():
            db.execute(sql_text("""
                INSERT INTO absence_base_rates (evidence_type, p_gen_innocent, p_gen_guilty)
                VALUES (:et, :pi, :pg)
                ON CONFLICT (evidence_type) DO NOTHING
            """), {"et": etype, "pi": rates["p_gen_innocent"], "pg": rates["p_gen_guilty"]})
        db.commit()
    except Exception as e:
        logger.warning("Could not create absence_base_rates: %s", e)
        db.rollback()
