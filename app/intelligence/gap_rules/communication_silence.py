"""Evidence Gap Rule 1 — Communication Silence Gap.

For every active communication pair (3+ COMMUNICATED_WITH relationships),
detect abnormal silence periods that overlap significant investigation events.
"""

import logging
import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.graph import crud
from app.graph.hypothesis import create_evidence_gap, add_relates_to
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# A gap must exceed median × this factor to be considered abnormal
GAP_FACTOR = 5.0
# Minimum communications to establish a "regular" pattern
MIN_COMMUNICATIONS = 3


def check_communication_silence(case_id: str, db: Session) -> list[dict]:
    """
    Detect communication silence gaps for all active communication pairs in a case.

    Returns list of created EvidenceGap dicts.
    """
    client = get_neo4j_client()
    gaps_created = []

    # Find all communication pairs with 3+ interactions
    pairs = client.execute_read(
        """
        MATCH (a:Person {case_id: $case_id})-[r:COMMUNICATED_WITH]-(b:Person)
        WHERE a.id < b.id
        WITH a, b, collect(r) AS rels
        WHERE size(rels) >= $min_comms
        RETURN a.id AS person_a_id, a.display_name AS name_a,
               b.id AS person_b_id, b.display_name AS name_b,
               [rel in rels | {
                   valid_from: rel.valid_from,
                   valid_to: rel.valid_to,
                   evidence_basis: rel.evidence_basis
               }] AS communications
        """,
        {"case_id": case_id, "min_comms": MIN_COMMUNICATIONS},
    )

    # Get significant events (anything that isn't communication or file_artifact)
    significant_events = client.execute_read(
        """
        MATCH (e:Event {case_id: $case_id})
        WHERE e.event_type <> 'communication' AND e.event_type <> 'file_artifact'
        RETURN e {.*} AS event
        """,
        {"case_id": case_id},
    )

    for pair in pairs:
        comms = pair["communications"]

        # Parse timestamps and sort
        timestamps = []
        for c in comms:
            ts_str = c.get("valid_from") or c.get("valid_to")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    continue

        if len(timestamps) < MIN_COMMUNICATIONS:
            continue

        timestamps.sort()

        # Compute consecutive deltas
        deltas = []
        for k in range(1, len(timestamps)):
            delta = (timestamps[k] - timestamps[k - 1]).total_seconds()
            if delta > 0:
                deltas.append(delta)

        if not deltas:
            continue

        median_gap = statistics.median(deltas)
        threshold = median_gap * GAP_FACTOR

        # Find abnormal gaps
        for k in range(1, len(timestamps)):
            gap_seconds = (timestamps[k] - timestamps[k - 1]).total_seconds()
            if gap_seconds <= threshold:
                continue

            gap_start = timestamps[k - 1]
            gap_end = timestamps[k]

            # Check overlap with significant events
            overlapping_events = []
            for evt in significant_events:
                evt_data = evt["event"]
                evt_from_str = evt_data.get("valid_from")
                evt_to_str = evt_data.get("valid_to")
                try:
                    evt_from = datetime.fromisoformat(str(evt_from_str).replace("Z", "+00:00")) if evt_from_str else None
                    evt_to = datetime.fromisoformat(str(evt_to_str).replace("Z", "+00:00")) if evt_to_str else None
                except (ValueError, TypeError):
                    continue

                # Check overlap
                if evt_from and evt_from <= gap_end and (evt_to is None or evt_to >= gap_start):
                    overlapping_events.append(evt_data)
                elif evt_to and evt_to >= gap_start and (evt_from is None or evt_from <= gap_end):
                    overlapping_events.append(evt_data)

            if not overlapping_events:
                continue

            # Create EvidenceGap
            median_str = _format_duration(median_gap)
            evt_desc = ", ".join(
                e.get("event_type", "unknown") for e in overlapping_events[:3]
            )

            description = (
                f"Persons {pair['name_a']} and {pair['name_b']} normally "
                f"communicate every ~{median_str} but show no communication "
                f"from {gap_start.isoformat()} to {gap_end.isoformat()}, "
                f"which overlaps with significant event(s): {evt_desc}."
            )

            gap = create_evidence_gap({
                "case_id": case_id,
                "description": description,
                "expected_value": "high",
                "urgency": "medium",
                "status": "open",
                "classification_tag": "case_sensitive",
            })
            gap_id = gap.get("id", "")

            # Link to persons and events
            add_relates_to(gap_id, pair["person_a_id"])
            add_relates_to(gap_id, pair["person_b_id"])
            for evt_data in overlapping_events[:3]:
                if evt_data.get("id"):
                    add_relates_to(gap_id, evt_data["id"])

            write_memory_record(
                db=db,
                case_id=case_id,
                record_type=MemoryRecordType.gap_identified,
                description=description,
                actor="system:gap_engine",
                graph_refs=[gap_id, pair["person_a_id"], pair["person_b_id"]],
                reasoning=f"Communication silence gap ({_format_duration(gap_seconds)}) "
                          f"exceeds {GAP_FACTOR}x median gap ({median_str}) "
                          f"and overlaps significant events.",
            )
            db.commit()
            gaps_created.append(gap)

    return gaps_created


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    hours = seconds / 3600
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"
