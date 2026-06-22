"""Behavioral Intelligence Engine — baseline modeling and anomaly detection.

Generalizes the Phase 3 communication-silence rule into proper behavioral
baseline computation with z-score anomaly detection.
"""

import uuid
import math
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.graph.driver import get_neo4j_client
from app.memory.writer import write_memory_record
from app.db.models import MemoryRecordType

logger = logging.getLogger(__name__)

# Minimum event count for a usable baseline
DEFAULT_MIN_EVENTS = 10
# Z-score threshold for anomaly detection
DEFAULT_Z_THRESHOLD = 2.0


def compute_baseline(
    case_id: str,
    person_id: str,
    db: Session,
    min_events: int = DEFAULT_MIN_EVENTS,
) -> dict:
    """
    Compute behavioral baselines from a Person's Event participation.

    Baselines computed:
    - communication_frequency: messages per day-of-week and hour-of-day
    - active_hours: hours during which the Person's Events typically occur

    Returns the baseline dict. If insufficient data, returns flagged result.
    """
    client = get_neo4j_client()

    # Get all events this person participated in
    events = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[:PARTICIPATED_IN]->(e:Event)
        WHERE e.valid_from IS NOT NULL
        RETURN e.id AS event_id, e.event_type AS event_type,
               e.valid_from AS valid_from, e.valid_to AS valid_to
        ORDER BY e.valid_from
        """,
        {"pid": person_id, "cid": case_id},
    )

    if len(events) < min_events:
        return {
            "status": "insufficient_data",
            "event_count": len(events),
            "min_required": min_events,
            "message": f"Only {len(events)} events found, need {min_events} for reliable baseline",
        }

    # Parse timestamps
    timestamps = []
    for evt in events:
        try:
            ts_str = str(evt["valid_from"]).replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_str)
            timestamps.append(ts)
        except (ValueError, TypeError):
            continue

    if len(timestamps) < min_events:
        return {"status": "insufficient_data", "event_count": len(timestamps)}

    # Communication frequency: per day-of-week (0=Mon..6=Sun)
    dow_counts = defaultdict(int)
    hod_counts = defaultdict(int)
    for ts in timestamps:
        dow_counts[ts.weekday()] += 1
        hod_counts[ts.hour] += 1

    # Normalize to per-week averages
    total_weeks = max(1, (timestamps[-1] - timestamps[0]).days / 7)
    dow_freq = {str(d): round(c / total_weeks, 2) for d, c in dow_counts.items()}
    hod_freq = {str(h): round(c / total_weeks, 2) for h, c in hod_counts.items()}

    # Active hours: hours with activity
    active_hours = sorted(h for h, c in hod_counts.items() if c >= 2)

    baseline_data = {
        "communication_frequency": {
            "by_day_of_week": dow_freq,
            "by_hour_of_day": hod_freq,
        },
        "active_hours": active_hours,
        "total_events": len(timestamps),
        "date_range": {
            "from": timestamps[0].isoformat(),
            "to": timestamps[-1].isoformat(),
        },
    }

    now = datetime.now(timezone.utc).isoformat()

    # Store/update BehavioralBaseline node
    client.execute_write(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})
        MERGE (p)-[:HAS_BASELINE]->(b:BehavioralBaseline {case_id: $cid, metric_type: 'combined'})
        ON CREATE SET b.id = $bid, b.baseline_data = $data, b.computed_at = $now,
                      b.based_on_event_count = $count, b.classification_tag = 'case_sensitive',
                      b.created_at = $now
        ON MATCH SET b.baseline_data = $data, b.computed_at = $now,
                     b.based_on_event_count = $count
        """,
        {
            "pid": person_id, "cid": case_id,
            "bid": str(uuid.uuid4()),
            "data": str(baseline_data),  # Neo4j doesn't support nested maps; store as string
            "now": now, "count": len(timestamps),
        },
    )

    return {"status": "computed", "baseline": baseline_data}


def scan_anomalies(
    case_id: str,
    person_id: str,
    from_ts: str,
    to_ts: str,
    db: Session,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
) -> list[dict]:
    """
    Compare events in [from_ts, to_ts] against the Person's baseline.
    Returns list of detected anomalies.
    """
    client = get_neo4j_client()
    anomalies_created = []

    # Get baseline
    baseline_result = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[:HAS_BASELINE]->(b:BehavioralBaseline)
        RETURN b.baseline_data AS data, b.based_on_event_count AS count
        """,
        {"pid": person_id, "cid": case_id},
    )

    if not baseline_result:
        return [{"error": "No baseline computed for this person"}]

    import json
    baseline_str = baseline_result[0]["data"]
    try:
        baseline = json.loads(baseline_str.replace("'", '"'))
    except (json.JSONDecodeError, AttributeError):
        baseline = eval(baseline_str)  # Fallback for Python dict strings

    # Get events in the scan window
    events = client.execute_read(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})-[:PARTICIPATED_IN]->(e:Event)
        WHERE e.valid_from >= $from AND e.valid_from <= $to
        RETURN e.id AS event_id, e.event_type AS event_type,
               e.valid_from AS valid_from
        """,
        {"pid": person_id, "cid": case_id, "from": from_ts, "to": to_ts},
    )

    # Frequency deviation check per day-of-week
    dow_expected = baseline.get("communication_frequency", {}).get("by_day_of_week", {})
    dow_observed = defaultdict(int)
    event_timestamps = []

    for evt in events:
        try:
            ts = datetime.fromisoformat(str(evt["valid_from"]).replace("Z", "+00:00"))
            dow_observed[str(ts.weekday())] += 1
            event_timestamps.append((ts, evt))
        except (ValueError, TypeError):
            continue

    # Check each day-of-week for deviations
    expected_values = list(dow_expected.values())
    if expected_values:
        mean_expected = statistics.mean(expected_values)
        std_expected = statistics.stdev(expected_values) if len(expected_values) > 1 else 1.0

        for dow_str, expected in dow_expected.items():
            observed = dow_observed.get(dow_str, 0)
            if std_expected > 0:
                z_score = (observed - expected) / std_expected
                if abs(z_score) > z_threshold:
                    dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(dow_str)]
                    anomaly = _create_anomaly(
                        client, case_id, person_id,
                        anomaly_type="frequency_deviation",
                        description=(
                            f"Expected ~{expected:.1f} messages on {dow_name} "
                            f"based on baseline; observed {observed}"
                        ),
                        severity="high" if abs(z_score) > 3.0 else "medium",
                        statistical_basis={
                            "expected": expected,
                            "observed": observed,
                            "z_score": round(z_score, 2),
                            "day_of_week": dow_name,
                        },
                    )
                    anomalies_created.append(anomaly)

    # Timing deviation: events outside active hours
    active_hours = set(baseline.get("active_hours", []))
    if active_hours:
        for ts, evt in event_timestamps:
            if ts.hour not in active_hours:
                anomaly = _create_anomaly(
                    client, case_id, person_id,
                    anomaly_type="timing_deviation",
                    description=(
                        f"Event at {ts.strftime('%H:%M')} is outside typical "
                        f"active hours {sorted(active_hours)}"
                    ),
                    severity="low",
                    statistical_basis={
                        "event_hour": ts.hour,
                        "active_hours": sorted(active_hours),
                        "event_id": evt.get("event_id"),
                    },
                    event_ids=[evt.get("event_id")],
                )
                anomalies_created.append(anomaly)

    # Write memory records
    for anomaly in anomalies_created:
        write_memory_record(
            db=db,
            case_id=case_id,
            record_type=MemoryRecordType.contradiction_found,
            description=anomaly.get("description", "Behavioral anomaly detected"),
            actor="system:behavioral_engine",
            graph_refs=[anomaly.get("id", ""), person_id],
            reasoning=str(anomaly.get("statistical_basis", {})),
        )
    if anomalies_created:
        db.commit()

    return anomalies_created


def _create_anomaly(
    client, case_id: str, person_id: str,
    anomaly_type: str, description: str, severity: str,
    statistical_basis: dict, event_ids: list = None,
) -> dict:
    """Create a BehavioralAnomaly node linked to the Person."""
    anomaly_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    client.execute_write(
        """
        MATCH (p:Person {id: $pid, case_id: $cid})
        CREATE (a:BehavioralAnomaly {
            id: $aid, case_id: $cid,
            anomaly_type: $atype, description: $desc,
            severity: $sev, detected_at: $now,
            statistical_basis: $stats,
            classification_tag: 'case_sensitive',
            created_at: $now
        })
        CREATE (p)-[:HAS_ANOMALY]->(a)
        """,
        {
            "pid": person_id, "cid": case_id, "aid": anomaly_id,
            "atype": anomaly_type, "desc": description, "sev": severity,
            "now": now, "stats": str(statistical_basis),
        },
    )

    # Link to events via INVOLVES
    for eid in (event_ids or []):
        if eid:
            client.execute_write(
                """
                MATCH (a:BehavioralAnomaly {id: $aid}), (e:Event {id: $eid})
                CREATE (a)-[:INVOLVES]->(e)
                """,
                {"aid": anomaly_id, "eid": eid},
            )

    return {
        "id": anomaly_id,
        "anomaly_type": anomaly_type,
        "description": description,
        "severity": severity,
        "statistical_basis": statistical_basis,
    }
