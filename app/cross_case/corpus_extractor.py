"""Case Corpus Extraction Pipeline — PII-safe pattern extraction from closed cases.

Converts closed cases into CasePattern entries in the global Methodology Library.
"""

import re
import uuid
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client

logger = logging.getLogger(__name__)

PII_PATTERNS = [
    re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'),  # Email
    re.compile(r'\+?\d{10,15}'),  # Phone
    re.compile(r'\b\d{12}\b'),  # Aadhaar-like
    re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'),  # PAN-like
]


def extract_case_pattern(case_id: str, db: Optional[Session] = None) -> dict:
    """Extract CasePattern from a closed case — PII-safe."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()
    pattern_id = str(uuid.uuid4())

    # Crime categories
    categories = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
        RETURN cat.id AS id, cat.name AS name
        """,
        {"cid": case_id},
    )
    crime_category_ids = [c["id"] for c in categories]

    # Legal sections
    sections = client.execute_read(
        """
        MATCH (q:LegalQualification {case_id: $cid})
        WHERE q.status = 'applicable'
        RETURN q.legal_section_id AS sid
        """,
        {"cid": case_id},
    )
    legal_sections = [s["sid"] for s in sections]

    # Evidence type profile (proportions)
    evidence_types = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid AND n.source_tool IS NOT NULL
        RETURN n.source_tool AS tool, count(n) AS cnt
        """,
        {"cid": case_id},
    )
    total_evidence = sum(e["cnt"] for e in evidence_types) or 1
    evidence_profile = {e["tool"]: round(e["cnt"] / total_evidence, 4)
                        for e in evidence_types}

    # Entity type profile
    entity_types = client.execute_read(
        """
        MATCH (n)
        WHERE n.case_id = $cid
        RETURN labels(n)[0] AS label, count(n) AS cnt
        """,
        {"cid": case_id},
    )
    total_entities = sum(e["cnt"] for e in entity_types) or 1
    entity_profile = {e["label"]: round(e["cnt"] / total_entities, 4)
                      for e in entity_types}

    # Hypothesis metrics
    hyp_peak = client.execute_read(
        "MATCH (h:Hypothesis {case_id: $cid}) RETURN count(h) AS cnt",
        {"cid": case_id},
    )
    hypothesis_count_at_peak = hyp_peak[0]["cnt"] if hyp_peak else 0

    # Time to first elimination
    first_elim = client.execute_read(
        """
        MATCH (h:Hypothesis {case_id: $cid, status: 'eliminated'})
        RETURN h.eliminated_at AS at
        ORDER BY h.eliminated_at LIMIT 1
        """,
        {"cid": case_id},
    )
    case_start = client.execute_read(
        "MATCH (ca:CaseAnchor {case_id: $cid}) RETURN ca.created_at AS at",
        {"cid": case_id},
    )
    time_to_first_elimination = None
    if first_elim and case_start:
        try:
            elim_dt = datetime.fromisoformat(str(first_elim[0]["at"]).replace("Z", "+00:00"))
            start_dt = datetime.fromisoformat(str(case_start[0]["at"]).replace("Z", "+00:00"))
            time_to_first_elimination = (elim_dt - start_dt).days
        except (ValueError, TypeError):
            pass

    # Decisive evidence types
    decisive = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
        WHERE r.satisfaction_score >= 0.8
        RETURN DISTINCT m.evidence_type AS etype
        """,
        {"cid": case_id},
    )
    decisive_types = [d["etype"] for d in decisive if d.get("etype")]

    # Defense vectors from latest simulation
    defense_vectors = client.execute_read(
        """
        MATCH (d:DefenseSimulation {case_id: $cid})
        RETURN d.attack_vector_count AS cnt
        ORDER BY d.generated_at DESC LIMIT 1
        """,
        {"cid": case_id},
    )
    common_defense = []  # Would extract from stored vectors in production

    # Build pattern
    hashed_case_id = hashlib.sha256(case_id.encode()).hexdigest()

    pattern = {
        "id": pattern_id,
        "extracted_from_case_id": hashed_case_id,
        "extracted_at": now,
        "crime_category_ids": crime_category_ids,
        "legal_sections_charged": legal_sections,
        "evidence_type_profile": evidence_profile,
        "entity_type_profile": entity_profile,
        "hypothesis_count_at_peak": hypothesis_count_at_peak,
        "time_to_first_elimination_days": time_to_first_elimination,
        "decisive_evidence_types": decisive_types,
        "common_defense_vectors": common_defense,
        "outcome": "closed",  # Would be from case status
    }

    # PII safety check
    pattern_str = json.dumps(pattern)
    pii_safe = not any(p.search(pattern_str) for p in PII_PATTERNS)

    # Store CasePattern node (global, not case-scoped)
    client.execute_write(
        """
        CREATE (cp:CasePattern {
            id: $pid, extracted_from_case_id: $hcid,
            extracted_at: $now,
            crime_category_ids: $cats,
            legal_sections_charged: $sections,
            evidence_type_profile: $eprofile,
            entity_type_profile: $entityprofile,
            hypothesis_count_at_peak: $hyp_peak,
            time_to_first_elimination_days: $ttfe,
            decisive_evidence_types: $decisive,
            outcome: $outcome,
            PII_SAFE: $pii_safe,
            created_at: $now
        })
        """,
        {
            "pid": pattern_id, "hcid": hashed_case_id, "now": now,
            "cats": json.dumps(crime_category_ids),
            "sections": json.dumps(legal_sections),
            "eprofile": json.dumps(evidence_profile),
            "entityprofile": json.dumps(entity_profile),
            "hyp_peak": hypothesis_count_at_peak,
            "ttfe": time_to_first_elimination,
            "decisive": json.dumps(decisive_types),
            "outcome": "closed",
            "pii_safe": pii_safe,
        },
    )

    pattern["PII_SAFE"] = pii_safe
    return pattern


def extract_all_eligible(db: Optional[Session] = None) -> dict:
    """Batch extraction for all closed cases."""
    client = get_neo4j_client()

    # Find cases with closed status that haven't been extracted
    closed = client.execute_read(
        """
        MATCH (ca:CaseAnchor)
        WHERE ca.status IN ['closed_convicted', 'closed_acquitted',
                             'closed_insufficient_evidence', 'closed_other', 'closed']
        AND NOT EXISTS {
            MATCH (cp:CasePattern {extracted_from_case_id: ca.case_id})
        }
        RETURN ca.case_id AS cid
        """,
    )

    extracted = 0
    for case in closed:
        try:
            extract_case_pattern(case["cid"], db)
            extracted += 1
        except Exception as e:
            logger.warning("Failed to extract case %s: %s", case["cid"], e)

    return {"eligible": len(closed), "extracted": extracted}
