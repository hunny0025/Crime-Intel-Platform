"""Behavioral Fingerprint + Recidivism Detection + Pattern Detection.

Combines Prompts 45-46: fingerprint extraction, cross-case entity linkage,
and modus operandi pattern detection.
"""

import hashlib
import json
import uuid
import logging
from datetime import datetime, timezone

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)


def extract_behavioral_fingerprint(case_id: str, person_id: str) -> dict:
    """Extract PII-safe behavioral fingerprint for a Person node."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    fp_id = str(uuid.uuid4())

    # Communication time signature (hours histogram)
    comms = client.execute_read(
        """
        MATCH (p:Person {id: $pid})-[r:COMMUNICATED_WITH]->()
        WHERE r.valid_from IS NOT NULL
        RETURN r.valid_from AS ts
        """,
        {"pid": person_id},
    )
    hour_hist = [0] * 24
    for c in comms:
        try:
            ts = str(c["ts"])
            if "T" in ts:
                hour = int(ts.split("T")[1][:2])
                hour_hist[hour] += 1
        except (ValueError, IndexError):
            pass
    total_comms = sum(hour_hist) or 1
    comm_time_sig = [round(h / total_comms, 4) for h in hour_hist]

    # Platform mix
    platforms = client.execute_read(
        """
        MATCH (p:Person {id: $pid})-[:OWNS|HAS_IDENTIFIER]->(a:Account)
        RETURN a.account_type AS atype, count(a) AS cnt
        """,
        {"pid": person_id},
    )
    total_platforms = sum(p["cnt"] for p in platforms) or 1
    platform_mix = {p["atype"]: round(p["cnt"] / total_platforms, 4)
                    for p in platforms if p.get("atype")}

    # Crime category involvement
    cats = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS cat_id
        """,
        {"cid": case_id},
    )
    crime_cats = [c["cat_id"] for c in cats]

    # Hash the person identifier
    person_hashed = hashlib.sha256(person_id.encode()).hexdigest()

    fingerprint = {
        "id": fp_id,
        "extracted_from_person_hashed_id": person_hashed,
        "communication_time_signature": comm_time_sig,
        "platform_mix": platform_mix,
        "crime_category_involvement": crime_cats,
        "extracted_at": now,
    }

    # Store
    client.execute_write(
        """
        CREATE (bf:BehavioralFingerprint {
            id: $fid,
            extracted_from_person_hashed_id: $hid,
            communication_time_signature: $cts,
            platform_mix: $pm,
            crime_category_involvement: $cats,
            extracted_at: $now, created_at: $now
        })
        """,
        {
            "fid": fp_id, "hid": person_hashed,
            "cts": json.dumps(comm_time_sig),
            "pm": json.dumps(platform_mix),
            "cats": json.dumps(crime_cats),
            "now": now,
        },
    )

    return fingerprint


def check_recidivism(case_id: str, person_id: str) -> dict:
    """Check if a person's behavioral fingerprint matches prior cases."""
    client = get_neo4j_client()

    # Get current person's fingerprint
    current_fp = extract_behavioral_fingerprint(case_id, person_id)

    # Find all fingerprints
    all_fps = client.execute_read(
        """
        MATCH (bf:BehavioralFingerprint)
        WHERE bf.extracted_from_person_hashed_id <> $hid
        RETURN bf.id AS id,
               bf.communication_time_signature AS cts,
               bf.platform_mix AS pm,
               bf.crime_category_involvement AS cats
        """,
        {"hid": current_fp["extracted_from_person_hashed_id"]},
    )

    matches = []
    for fp in all_fps:
        sim = _fingerprint_similarity(current_fp, fp)
        if sim > 0.6:  # Threshold for flagging
            matches.append({
                "fingerprint_id": fp["id"],
                "similarity_score": round(sim, 4),
                "shared_crime_categories": _safe_json(fp.get("cats")),
            })

    matches.sort(key=lambda m: m["similarity_score"], reverse=True)

    return {
        "person_id": person_id,
        "case_id": case_id,
        "matches_found": len(matches),
        "matches": matches[:5],
        "recidivism_flag": len(matches) > 0,
    }


def detect_modus_operandi(case_id: str) -> dict:
    """Detect if the case's methodology pattern matches known MO patterns."""
    client = get_neo4j_client()

    # Get case's evidence and entity patterns
    evidence = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN n.source_tool AS tool, n.event_type AS etype
        """,
        {"cid": case_id},
    )

    # Get relationship patterns
    rels = client.execute_read(
        """
        MATCH (a)-[r]->(b)
        WHERE a.case_id = $cid
        RETURN type(r) AS rtype, count(r) AS cnt
        """,
        {"cid": case_id},
    )

    case_signature = {
        "evidence_tools": list(set(e["tool"] for e in evidence if e.get("tool"))),
        "event_types": list(set(e["etype"] for e in evidence if e.get("etype"))),
        "relationship_types": {r["rtype"]: r["cnt"] for r in rels},
    }

    # Compare against CasePattern methodology signatures
    patterns = client.execute_read(
        """
        MATCH (cp:CasePattern)
        WHERE cp.PII_SAFE = true
        RETURN cp.id AS id, cp.evidence_type_profile AS eprofile,
               cp.decisive_evidence_types AS decisive, cp.outcome AS outcome
        """,
    )

    mo_matches = []
    for p in patterns:
        overlap = _mo_overlap(case_signature, p)
        if overlap > 0.5:
            mo_matches.append({
                "pattern_id": p["id"],
                "overlap_score": round(overlap, 4),
                "outcome": p.get("outcome", "unknown"),
            })

    mo_matches.sort(key=lambda m: m["overlap_score"], reverse=True)

    return {
        "case_id": case_id,
        "case_signature": case_signature,
        "mo_matches": mo_matches[:5],
        "known_mo_detected": len(mo_matches) > 0,
    }


def _fingerprint_similarity(current: dict, other: dict) -> float:
    """Compute similarity between two behavioral fingerprints."""
    score = 0.0

    # Communication time signature cosine similarity
    cts_c = current.get("communication_time_signature", [0] * 24)
    cts_o = _safe_json(other.get("cts")) or [0] * 24
    if len(cts_o) == 24:
        dot = sum(a * b for a, b in zip(cts_c, cts_o))
        mag_c = sum(a**2 for a in cts_c) ** 0.5
        mag_o = sum(a**2 for a in cts_o) ** 0.5
        if mag_c > 0 and mag_o > 0:
            score += 0.5 * (dot / (mag_c * mag_o))

    # Platform mix overlap
    pm_c = current.get("platform_mix", {})
    pm_o = _safe_json_dict(other.get("pm"))
    shared_platforms = set(pm_c) & set(pm_o)
    all_platforms = set(pm_c) | set(pm_o)
    if all_platforms:
        score += 0.3 * (len(shared_platforms) / len(all_platforms))

    # Crime category overlap
    cats_c = set(current.get("crime_category_involvement", []))
    cats_o = set(_safe_json(other.get("cats")))
    if cats_c or cats_o:
        score += 0.2 * (len(cats_c & cats_o) / len(cats_c | cats_o))

    return score


def _mo_overlap(signature: dict, pattern: dict) -> float:
    """Compute modus operandi overlap between case signature and pattern."""
    ep = _safe_json_dict(pattern.get("eprofile"))
    decisive = set(_safe_json(pattern.get("decisive")))

    case_tools = set(signature.get("evidence_tools", []))
    overlap = case_tools & (set(ep.keys()) | decisive)
    total = case_tools | set(ep.keys()) | decisive

    return len(overlap) / len(total) if total else 0


def _safe_json(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _safe_json_dict(val):
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.replace("'", '"'))
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
