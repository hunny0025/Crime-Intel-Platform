"""Legal Element Mapping Engine — maps evidence to formal elements of offense.

Scans graph for evidence satisfying each LegalElement, computing satisfaction_score
from chain confidence and relationship confidence.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.reasoning.probabilistic_engine import get_chain_confidence, DEFAULT_DECAY_FACTOR
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType
from app.legal.explainable_reasoning import create_reasoning_trace

logger = logging.getLogger(__name__)

# Minimum satisfaction score to create a mapping
DEFAULT_THRESHOLD = 0.4


def map_elements_for_case(case_id: str, threshold: float = DEFAULT_THRESHOLD,
                          db: Optional[Session] = None) -> dict:
    """
    Map evidence to LegalElements for all sections relevant to this case.

    Flow:
    1. Find case's CrimeCategory → LegalSections → LegalElements
    2. For each element, scan graph for matching evidence
    3. Create SATISFIES_ELEMENT relationships above threshold
    """
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get all legal elements for this case's crime category
    elements = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
              -[:MAPS_TO_LEGAL_SECTION]->(ls:LegalSection)-[:HAS_ELEMENT]->(le:LegalElement)
        RETURN le.id AS element_id, le.element_text AS element_text,
               le.evidence_types_typically_required AS required_types,
               ls.id AS section_id, ls.section_reference AS section_ref
        """,
        {"cid": case_id},
    )

    if not elements:
        # Fallback: try all LegalElements linked to sections connected to case
        elements = client.execute_read(
            """
            MATCH (ls:LegalSection)-[:HAS_ELEMENT]->(le:LegalElement)
            RETURN le.id AS element_id, le.element_text AS element_text,
                   le.evidence_types_typically_required AS required_types,
                   ls.id AS section_id, ls.section_reference AS section_ref
            """,
        )

    mappings_created = 0
    results = []

    for elem in elements:
        required = _parse_list(elem.get("required_types"))
        matches = _find_matching_evidence(client, case_id, required, elem["element_id"])

        for match in matches:
            if match["satisfaction_score"] >= threshold:
                # Check if mapping already exists
                existing = client.execute_read(
                    """
                    MATCH ()-[r:SATISFIES_ELEMENT]->(le:LegalElement {id: $eid})
                    WHERE r.evidence_ref = $eref
                    RETURN r.satisfaction_score AS score
                    """,
                    {"eid": elem["element_id"], "eref": match["evidence_ref"]},
                )
                if existing:
                    continue

                # Create SATISFIES_ELEMENT relationship
                rel_id = str(uuid.uuid4())
                reliability = match.get("reliability_score", 0.5)
                coc_status = match.get("chain_of_custody_status", "unverified")
                ev_value = match.get("evidentiary_value", "circumstantial")
                client.execute_write(
                    """
                    MATCH (le:LegalElement {id: $eid})
                    CREATE (m:EvidenceMapping {
                        id: $rid, case_id: $cid,
                        evidence_ref: $eref, evidence_type: $etype,
                        satisfaction_score: $score,
                        reliability_score: $reliability,
                        chain_of_custody_status: $coc_status,
                        evidentiary_value: $ev_value,
                        mapping_basis: $basis,
                        mapped_at: $now,
                        mapped_by: 'system:element_mapper',
                        confirmation_status: 'auto_suggested',
                        classification_tag: 'case_sensitive',
                        created_at: $now
                    })-[:SATISFIES_ELEMENT {
                        satisfaction_score: $score,
                        mapping_basis: $basis,
                        mapped_at: $now,
                        mapped_by: 'system:element_mapper',
                        confirmation_status: 'auto_suggested'
                    }]->(le)
                    """,
                    {
                        "rid": rel_id, "cid": case_id,
                        "eid": elem["element_id"],
                        "eref": match["evidence_ref"],
                        "etype": match["evidence_type"],
                        "score": match["satisfaction_score"],
                        "reliability": reliability,
                        "coc_status": coc_status,
                        "ev_value": ev_value,
                        "basis": match["mapping_basis"],
                        "now": now,
                    },
                )
                mappings_created += 1

                # Create explainable reasoning trace
                create_reasoning_trace(
                    case_id=case_id,
                    engine_source="element_mapper",
                    recommendation_text=f"Evidence '{match['evidence_ref']}' mapped to element '{elem.get('element_text', '')[:60]}'",
                    why=match["mapping_basis"],
                    supporting_evidence=[{"ref": match["evidence_ref"], "type": match["evidence_type"], "score": match["satisfaction_score"]}],
                    satisfied_elements=[{"id": elem["element_id"], "text": elem.get("element_text", "")}],
                    confidence_level="high" if match["satisfaction_score"] >= 0.7 else "medium" if match["satisfaction_score"] >= 0.5 else "low",
                    legal_basis=f"Section {elem.get('section_id', '')}",
                    linked_node_ids=[rel_id, elem["element_id"]],
                )

        results.append({
            "element_id": elem["element_id"],
            "element_text": elem.get("element_text", ""),
            "section_id": elem["section_id"],
            "matches_found": len(matches),
            "mappings_above_threshold": sum(
                1 for m in matches if m["satisfaction_score"] >= threshold
            ),
        })

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Element mapping completed: {mappings_created} SATISFIES_ELEMENT created",
            actor="system:element_mapper",
            reasoning=f"Scanned {len(elements)} elements, threshold={threshold}",
        )
        db.commit()

    return {
        "case_id": case_id,
        "elements_scanned": len(elements),
        "mappings_created": mappings_created,
        "threshold": threshold,
        "details": results,
    }


def get_element_map(case_id: str) -> dict:
    """Return all LegalSections with their elements and satisfaction status."""
    client = get_neo4j_client()

    sections = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
              -[:MAPS_TO_LEGAL_SECTION]->(ls:LegalSection)
        RETURN ls.id AS section_id, ls.section_reference AS section_ref,
               ls.title AS title
        """,
        {"cid": case_id},
    )

    if not sections:
        sections = client.execute_read(
            "MATCH (ls:LegalSection) RETURN ls.id AS section_id, "
            "ls.section_reference AS section_ref, ls.title AS title",
        )

    result = []
    for sec in sections:
        elements = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[:HAS_ELEMENT]->(le:LegalElement)
            OPTIONAL MATCH (m)-[r:SATISFIES_ELEMENT]->(le)
            WHERE m.case_id = $cid
            RETURN le.id AS element_id, le.element_text AS element_text,
                   collect({
                       mapping_id: m.id,
                       satisfaction_score: r.satisfaction_score,
                       mapping_basis: r.mapping_basis,
                       confirmation_status: r.confirmation_status
                   }) AS mappings
            """,
            {"sid": sec["section_id"], "cid": case_id},
        )

        element_list = []
        for e in elements:
            mappings = [m for m in e["mappings"]
                        if m.get("mapping_id") is not None]
            # Determine status
            confirmed_or_auto = [
                m for m in mappings
                if m.get("confirmation_status") in ("investigator_confirmed", "auto_suggested")
            ]
            max_score = max((m.get("satisfaction_score", 0) for m in confirmed_or_auto), default=0)

            if max_score >= 0.7:
                status = "satisfied"
            elif max_score >= 0.4:
                status = "partially_satisfied"
            else:
                status = "unsatisfied"

            element_list.append({
                "element_id": e["element_id"],
                "element_text": e.get("element_text", ""),
                "status": status,
                "mappings": mappings,
            })

        result.append({
            "section_id": sec["section_id"],
            "section_reference": sec.get("section_ref", ""),
            "title": sec.get("title", ""),
            "elements": element_list,
        })

    return {"case_id": case_id, "sections": result}


def get_evidence_law_map(case_id: str) -> dict:
    """Return a flat list of evidence-to-element mapping entries with detailed metadata."""
    client = get_neo4j_client()
    mappings = client.execute_read(
        """
        MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le:LegalElement)
        OPTIONAL MATCH (le)<-[:HAS_ELEMENT]-(ls:LegalSection)
        RETURN m.id AS mapping_id, m.evidence_ref AS evidence_ref,
               m.evidence_type AS evidence_type, r.satisfaction_score AS satisfaction_score,
               r.mapping_basis AS mapping_basis, r.confirmation_status AS verification_status,
               r.human_override AS human_override, r.mapped_at AS mapped_at,
               le.id AS element_id, le.element_text AS element_text,
               ls.id AS section_id, ls.section_number AS section_number, ls.statute AS statute
        """,
        {"cid": case_id},
    )
    res = []
    for row in mappings:
        res.append({
            "mapping_id": row["mapping_id"],
            "evidence_ref": row["evidence_ref"],
            "evidence_type": row["evidence_type"],
            "satisfaction_score": row["satisfaction_score"],
            "mapping_basis": row["mapping_basis"],
            "verification_status": row["verification_status"],
            "human_override": row.get("human_override", False) or False,
            "mapped_at": row["mapped_at"],
            "element": {
                "id": row["element_id"],
                "text": row["element_text"],
            },
            "section": {
                "id": row["section_id"],
                "number": row["section_number"],
                "statute": row["statute"],
            }
        })
    return {
        "case_id": case_id,
        "mappings": res,
        "disclaimer": "Advisory only. Final charging decisions require independent prosecutorial assessment."
    }


def confirm_mapping(case_id: str, mapping_id: str,
                    db: Optional[Session] = None) -> dict:
    """Investigator confirms a SATISFIES_ELEMENT mapping."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (m:EvidenceMapping {id: $mid, case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
        SET m.confirmation_status = 'investigator_confirmed',
            r.confirmation_status = 'investigator_confirmed',
            m.human_override = true,
            r.human_override = true,
            m.confirmed_at = $now
        """,
        {"mid": mapping_id, "cid": case_id, "now": now},
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Element mapping {mapping_id} confirmed by investigator",
            actor="system:element_mapper",
            graph_refs=[mapping_id],
        )
        db.commit()

    return {"mapping_id": mapping_id, "status": "investigator_confirmed"}


def reject_mapping(case_id: str, mapping_id: str, rejection_reason: str,
                   db: Optional[Session] = None) -> dict:
    """Investigator rejects a SATISFIES_ELEMENT mapping."""
    client = get_neo4j_client()
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (m:EvidenceMapping {id: $mid, case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
        SET m.confirmation_status = 'investigator_rejected',
            r.confirmation_status = 'investigator_rejected',
            m.human_override = true,
            r.human_override = true,
            m.rejection_reason = $reason,
            m.rejected_at = $now
        """,
        {"mid": mapping_id, "cid": case_id, "reason": rejection_reason, "now": now},
    )

    if db:
        write_memory_record(
            db=db, case_id=case_id,
            record_type=MemoryRecordType.decision_made,
            description=f"Element mapping {mapping_id} rejected: {rejection_reason[:80]}",
            actor="system:element_mapper",
            graph_refs=[mapping_id],
            reasoning=rejection_reason,
        )
        db.commit()

    return {"mapping_id": mapping_id, "status": "investigator_rejected"}


def incremental_map_for_evidence_type(case_id: str, evidence_type: str,
                                      db: Optional[Session] = None) -> dict:
    """Re-map only LegalElements whose required types overlap with evidence_type."""
    client = get_neo4j_client()

    elements = client.execute_read(
        """
        MATCH (le:LegalElement)
        WHERE le.evidence_types_typically_required CONTAINS $etype
        RETURN le.id AS element_id, le.element_text AS element_text,
               le.evidence_types_typically_required AS required_types
        """,
        {"etype": evidence_type},
    )

    if not elements:
        return {"remapped": 0}

    mappings = 0
    for elem in elements:
        required = _parse_list(elem.get("required_types"))
        matches = _find_matching_evidence(client, case_id, required, elem["element_id"])
        for match in matches:
            if match["satisfaction_score"] >= DEFAULT_THRESHOLD:
                existing = client.execute_read(
                    "MATCH ()-[r:SATISFIES_ELEMENT]->(le:LegalElement {id: $eid}) "
                    "WHERE r.evidence_ref = $eref RETURN count(r) AS cnt",
                    {"eid": elem["element_id"], "eref": match["evidence_ref"]},
                )
                if not existing or existing[0]["cnt"] == 0:
                    rel_id = str(uuid.uuid4())
                    now = datetime.now(timezone.utc).isoformat()
                    client.execute_write(
                        """
                        MATCH (le:LegalElement {id: $eid})
                        CREATE (m:EvidenceMapping {
                            id: $rid, case_id: $cid, evidence_ref: $eref,
                            evidence_type: $etype, satisfaction_score: $score,
                            mapping_basis: $basis, mapped_at: $now,
                            mapped_by: 'system:element_mapper',
                            confirmation_status: 'auto_suggested',
                            classification_tag: 'case_sensitive', created_at: $now
                        })-[:SATISFIES_ELEMENT {
                            satisfaction_score: $score, mapping_basis: $basis,
                            mapped_at: $now, mapped_by: 'system:element_mapper',
                            confirmation_status: 'auto_suggested'
                        }]->(le)
                        """,
                        {
                            "rid": rel_id, "cid": case_id, "eid": elem["element_id"],
                            "eref": match["evidence_ref"], "etype": match["evidence_type"],
                            "score": match["satisfaction_score"], "basis": match["mapping_basis"],
                            "now": now,
                        },
                    )
                    mappings += 1

    return {"evidence_type": evidence_type, "remapped": mappings}


# ── Internal helpers ─────────────────────────────────────────────────────

def _find_matching_evidence(client, case_id: str, required_types: list,
                            element_id: str) -> list[dict]:
    """Find evidence in the case graph matching required evidence types."""
    matches = []

    for req_type in required_types:
        # Direct: find relationships of matching type
        rel_type_map = {
            "communication_record": "COMMUNICATED_WITH",
            "device_seizure": "OWNS",
            "device_artifact": "OWNS",
            "location_record": "AT",
            "financial_record": "TRANSFERRED_TO",
            "gps_record": "AT",
            "cell_tower": "AT",
            "cctv": "AT",
        }

        rel_type = rel_type_map.get(req_type.lower())
        if rel_type:
            rels = client.execute_read(
                f"""
                MATCH (a)-[r:{rel_type}]->(b)
                WHERE a.case_id = $cid OR b.case_id = $cid
                RETURN r.id AS rel_id, type(r) AS rel_type,
                       r.confidence AS conf, r.evidence_basis AS eb,
                       a.id AS from_id, b.id AS to_id
                LIMIT 10
                """,
                {"cid": case_id},
            )

            for rel in rels:
                conf = rel.get("conf", 0.7) or 0.7
                chain_conf = conf * (DEFAULT_DECAY_FACTOR ** 0)  # Direct = 0 hops

                score = min(chain_conf, 1.0)
                coc_status = _assess_chain_of_custody(client, rel.get("from_id", ""))
                reliability = _compute_reliability(conf, coc_status)
                ev_value = _classify_evidentiary_value(rel_type, req_type)
                matches.append({
                    "evidence_ref": rel.get("rel_id") or f"{rel['from_id']}->{rel['to_id']}",
                    "evidence_type": req_type,
                    "satisfaction_score": round(score, 4),
                    "reliability_score": round(reliability, 4),
                    "chain_of_custody_status": coc_status,
                    "evidentiary_value": ev_value,
                    "mapping_basis": f"Direct {rel_type} relationship (confidence={conf:.2f}) "
                                     f"satisfies evidence type '{req_type}' "
                                     f"for element {element_id}",
                })

        # Also check EvidenceArtifacts by source_tool / content_type
        artifacts = client.execute_read(
            """
            MATCH (n)
            WHERE n.case_id = $cid
            AND (n.source_tool = $rtype OR n.content_type = $rtype
                 OR n.event_type = $rtype)
            RETURN n.id AS id, labels(n)[0] AS label,
                   coalesce(n.display_name, n.id) AS display
            LIMIT 5
            """,
            {"cid": case_id, "rtype": req_type},
        )
        for art in artifacts:
            coc_status = _assess_chain_of_custody(client, art["id"])
            matches.append({
                "evidence_ref": art["id"],
                "evidence_type": req_type,
                "satisfaction_score": 0.5,  # Indirect match via type
                "reliability_score": 0.4 if coc_status == "intact" else 0.2,
                "chain_of_custody_status": coc_status,
                "evidentiary_value": "circumstantial",
                "mapping_basis": f"Artifact/node {art['display']} ({art['label']}) "
                                 f"matches evidence type '{req_type}' for element {element_id}",
            })

    return matches


def _parse_list(val) -> list:
    """Parse a JSON list or comma-separated string into a Python list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val.replace("'", '"'))
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            return [v.strip() for v in val.split(",") if v.strip()]
    return []


def _assess_chain_of_custody(client, node_id: str) -> str:
    """Assess chain of custody status for an evidence node."""
    if not node_id:
        return "unverified"
    result = client.execute_read(
        "MATCH (n {id: $nid}) RETURN n.hash_verified AS hv, n.chain_verified AS cv",
        {"nid": node_id},
    )
    if not result:
        return "unverified"
    row = result[0]
    if row.get("hv") is False:
        return "broken"
    if row.get("hv") is True or row.get("cv") is True:
        return "intact"
    return "unverified"


def _compute_reliability(confidence: float, coc_status: str) -> float:
    """Compute reliability score from source confidence and chain-of-custody."""
    coc_factor = {"intact": 1.0, "unverified": 0.6, "broken": 0.1}.get(coc_status, 0.5)
    return round(confidence * coc_factor, 4)


def _classify_evidentiary_value(rel_type: str, evidence_type: str) -> str:
    """Classify evidentiary value based on relationship and evidence type."""
    primary_types = {"COMMUNICATED_WITH", "TRANSFERRED_TO", "OWNS"}
    secondary_types = {"AT"}
    if rel_type in primary_types:
        return "primary"
    if rel_type in secondary_types:
        return "corroborative"
    if evidence_type in ("witness_statements", "victim_statement"):
        return "primary"
    if evidence_type in ("cctv", "gps_record", "cell_tower"):
        return "corroborative"
    return "circumstantial"


def get_evidence_strength_matrix(case_id: str) -> dict:
    """Return per-section evidence strength with SUPPORTS/WEAKENS counts."""
    client = get_neo4j_client()

    sections = client.execute_read(
        """
        MATCH (ca:CaseAnchor {case_id: $cid})-[:CLASSIFIED_AS]->(cat:CrimeCategory)
              -[:MAPS_TO_LEGAL_SECTION]->(ls:LegalSection)
        RETURN ls.id AS section_id, ls.section_number AS section_number,
               ls.title AS title, ls.statute AS statute
        """,
        {"cid": case_id},
    )
    if not sections:
        sections = client.execute_read(
            "MATCH (ls:LegalSection) RETURN ls.id AS section_id, "
            "ls.section_number AS section_number, ls.title AS title, ls.statute AS statute",
        )

    matrix = []
    for sec in sections:
        # Count mappings by status
        mappings = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[:HAS_ELEMENT]->(le:LegalElement)
            OPTIONAL MATCH (m:EvidenceMapping {case_id: $cid})-[r:SATISFIES_ELEMENT]->(le)
            WHERE m.confirmation_status IN ['auto_suggested', 'investigator_confirmed']
            RETURN le.id AS element_id, le.element_text AS element_text,
                   count(m) AS mapping_count,
                   max(r.satisfaction_score) AS max_score,
                   collect(DISTINCT m.evidentiary_value) AS ev_values,
                   collect(DISTINCT m.chain_of_custody_status) AS coc_statuses
            """,
            {"sid": sec["section_id"], "cid": case_id},
        )

        elements = []
        supports_count = 0
        weakens_count = 0
        for m in mappings:
            max_s = m.get("max_score") or 0
            if max_s >= 0.4:
                supports_count += 1
            elif m.get("mapping_count", 0) > 0 and max_s < 0.4:
                weakens_count += 1
            elements.append({
                "element_id": m["element_id"],
                "element_text": m.get("element_text", ""),
                "mapping_count": m.get("mapping_count", 0),
                "max_satisfaction_score": max_s,
                "evidentiary_values": [v for v in (m.get("ev_values") or []) if v],
                "chain_of_custody_statuses": [c for c in (m.get("coc_statuses") or []) if c],
            })

        total_elements = len(elements)
        strength = supports_count / total_elements if total_elements > 0 else 0

        # Get cross-referenced sections
        xrefs = client.execute_read(
            """
            MATCH (ls:LegalSection {id: $sid})-[r:CROSS_REFERENCES]->(ls2:LegalSection)
            RETURN ls2.section_number AS section_number, ls2.title AS title,
                   r.relationship_type AS relationship_type, r.description AS description
            """,
            {"sid": sec["section_id"]},
        )

        matrix.append({
            "section_id": sec["section_id"],
            "section_number": sec.get("section_number", ""),
            "title": sec.get("title", ""),
            "statute": sec.get("statute", ""),
            "total_elements": total_elements,
            "elements_supported": supports_count,
            "elements_weak": weakens_count,
            "elements_unsupported": total_elements - supports_count - weakens_count,
            "evidence_strength": round(strength, 4),
            "elements": elements,
            "cross_references": [
                {"section": x["section_number"], "title": x["title"],
                 "relationship": x["relationship_type"], "description": x["description"]}
                for x in xrefs
            ],
        })

    return {
        "case_id": case_id,
        "strength_matrix": matrix,
        "disclaimer": "Advisory only. Evidence strength is an automated assessment and requires independent prosecutorial review.",
    }
