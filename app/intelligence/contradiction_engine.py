"""Contradiction Engine — detects temporal/spatial co-location contradictions.

Checks every Person for pairs of AT relationships to incompatible Locations
with overlapping time windows. Creates Contradiction nodes + memory records.
"""

import logging
import math
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.graph import crud
from app.graph.hypothesis import create_contradiction, add_involves
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Default distance threshold in km — two locations farther apart than this
# are considered incompatible for simultaneous presence.
DISTANCE_THRESHOLD_KM = 5.0


def _parse_coordinates(coord_str: str) -> Optional[tuple[float, float]]:
    """Parse 'lat,lon' string into (lat, lon) tuple."""
    if not coord_str:
        return None
    parts = coord_str.split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _locations_incompatible(loc_a: dict, loc_b: dict, threshold_km: float = DISTANCE_THRESHOLD_KM) -> tuple[bool, float]:
    """
    Check if two locations are incompatible for simultaneous presence.
    Returns (is_incompatible, distance_km).
    """
    type_a = loc_a.get("location_type", "")
    type_b = loc_b.get("location_type", "")

    # Different cell towers are always incompatible (simplified rule)
    if type_a == "cell_tower" and type_b == "cell_tower":
        if loc_a.get("id") != loc_b.get("id"):
            return True, float("inf")
        return False, 0.0

    # GPS/address locations — compute distance
    coord_a = _parse_coordinates(loc_a.get("coordinates", ""))
    coord_b = _parse_coordinates(loc_b.get("coordinates", ""))

    if coord_a and coord_b:
        dist = _haversine_km(coord_a[0], coord_a[1], coord_b[0], coord_b[1])
        return dist > threshold_km, dist

    # Different addresses without coordinates — treat as incompatible if distinct
    addr_a = (loc_a.get("address") or "").strip().lower()
    addr_b = (loc_b.get("address") or "").strip().lower()
    if addr_a and addr_b and addr_a != addr_b:
        return True, float("inf")

    return False, 0.0


def _time_overlap(t1_from: str, t1_to: str, t2_from: str, t2_to: str) -> Optional[float]:
    """
    Return overlap duration in seconds if intervals overlap, else None.
    Times are ISO strings.
    """
    try:
        a_start = datetime.fromisoformat(t1_from.replace("Z", "+00:00")) if t1_from else datetime.min.replace(tzinfo=timezone.utc)
        a_end = datetime.fromisoformat(t1_to.replace("Z", "+00:00")) if t1_to else datetime.max.replace(tzinfo=timezone.utc)
        b_start = datetime.fromisoformat(t2_from.replace("Z", "+00:00")) if t2_from else datetime.min.replace(tzinfo=timezone.utc)
        b_end = datetime.fromisoformat(t2_to.replace("Z", "+00:00")) if t2_to else datetime.max.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

    overlap_start = max(a_start, b_start)
    overlap_end = min(a_end, b_end)
    if overlap_start < overlap_end:
        return (overlap_end - overlap_start).total_seconds()
    return None


def _compute_severity(overlap_seconds: float, conf_a: float, conf_b: float) -> str:
    """Derive severity from overlap duration and combined confidence."""
    combined_conf = (conf_a + conf_b) / 2.0
    # High: >1h overlap AND combined confidence >0.7
    if overlap_seconds > 3600 and combined_conf > 0.7:
        return "high"
    # Medium: >10min overlap OR combined confidence >0.5
    if overlap_seconds > 600 or combined_conf > 0.5:
        return "medium"
    return "low"


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    hours = seconds / 3600
    return f"{hours:.1f}h"


def check_person_at_contradictions(
    case_id: str,
    person_id: str,
    db: Session,
    threshold_km: float = DISTANCE_THRESHOLD_KM,
) -> list[dict]:
    """
    Check a single Person for temporal/spatial contradictions across AT relationships.
    Returns list of created Contradiction dicts.
    """
    client = get_neo4j_client()
    contradictions_created = []

    # Get all AT relationships for this person
    at_rels = client.execute_read(
        """
        MATCH (p:Person {id: $person_id, case_id: $case_id})-[r:AT]->(loc:Location)
        RETURN p.display_name AS person_name,
               loc {.*} AS location,
               r.valid_from AS valid_from,
               r.valid_to AS valid_to,
               r.confidence AS confidence,
               r.evidence_basis AS evidence_basis
        """,
        {"person_id": person_id, "case_id": case_id},
    )

    if len(at_rels) < 2:
        return []

    # Check all pairs
    for i in range(len(at_rels)):
        for j in range(i + 1, len(at_rels)):
            a = at_rels[i]
            b = at_rels[j]

            loc_a = a["location"]
            loc_b = b["location"]

            # Same location — no contradiction possible
            if loc_a.get("id") == loc_b.get("id"):
                continue

            # Check incompatibility
            incompatible, distance = _locations_incompatible(loc_a, loc_b, threshold_km)
            if not incompatible:
                continue

            # Check time overlap
            overlap = _time_overlap(
                a.get("valid_from", ""), a.get("valid_to", ""),
                b.get("valid_from", ""), b.get("valid_to", ""),
            )
            if overlap is None or overlap <= 0:
                continue

            # Contradiction found!
            conf_a = float(a.get("confidence") or 0.5)
            conf_b = float(b.get("confidence") or 0.5)
            severity = _compute_severity(overlap, conf_a, conf_b)

            dist_str = f"{distance:.1f}km" if distance != float("inf") else "distinct locations"
            desc = (
                f"Person {a['person_name']} is placed AT {loc_a.get('address') or loc_a.get('coordinates') or loc_a.get('id')} "
                f"from {a.get('valid_from')} to {a.get('valid_to')} "
                f"(evidence: {a.get('evidence_basis', [])}) "
                f"and AT {loc_b.get('address') or loc_b.get('coordinates') or loc_b.get('id')} "
                f"from {b.get('valid_from')} to {b.get('valid_to')} "
                f"(evidence: {b.get('evidence_basis', [])}), "
                f"an overlap of {_format_duration(overlap)}, "
                f"but these locations are {dist_str} apart."
            )

            # Create Contradiction node
            contra = create_contradiction({
                "case_id": case_id,
                "description": desc,
                "severity": severity,
                "contradiction_type": "temporal",
                "classification_tag": "case_sensitive",
            })
            contra_id = contra.get("id", "")

            # Link to involved nodes
            add_involves(contra_id, person_id, "placed at incompatible locations simultaneously")
            add_involves(contra_id, loc_a["id"], "location A")
            add_involves(contra_id, loc_b["id"], "location B")

            # Write memory record
            all_evidence = list(set(
                (a.get("evidence_basis") or []) + (b.get("evidence_basis") or [])
            ))
            write_memory_record(
                db=db,
                case_id=case_id,
                record_type=MemoryRecordType.contradiction_found,
                description=desc,
                actor="system:contradiction_engine",
                evidence_basis=all_evidence,
                graph_refs=[contra_id, person_id, loc_a["id"], loc_b["id"]],
                reasoning=desc,
            )
            db.commit()

            contradictions_created.append(contra)
            logger.info("Contradiction created: %s (severity=%s)", contra_id, severity)

    return contradictions_created


def scan_case_contradictions(case_id: str, db: Session) -> list[dict]:
    """Full sweep: check all Persons in the case for AT contradictions."""
    client = get_neo4j_client()
    persons = client.execute_read(
        "MATCH (p:Person {case_id: $case_id}) RETURN p.id AS id",
        {"case_id": case_id},
    )
    all_contradictions = []
    for p in persons:
        contras = check_person_at_contradictions(case_id, p["id"], db)
        all_contradictions.extend(contras)
    return all_contradictions


def get_contradictions_detail(case_id: str) -> list[dict]:
    """Return all Contradictions with resolved entity details."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (c:Contradiction {case_id: $case_id})
        OPTIONAL MATCH (c)-[inv:INVOLVES]->(involved)
        RETURN c {.*} AS contradiction,
               c.severity AS severity,
               collect({
                   node_id: involved.id,
                   label: labels(involved)[0],
                   display: coalesce(involved.display_name, involved.address, involved.coordinates, involved.id),
                   nature: inv.nature
               }) AS involved_entities
        ORDER BY CASE severity
            WHEN 'high' THEN 0
            WHEN 'medium' THEN 1
            ELSE 2
        END
        """,
        {"case_id": case_id},
    )
    return [
        {
            **row["contradiction"],
            "involved_entities": [e for e in row["involved_entities"] if e.get("node_id")],
        }
        for row in result
    ]
