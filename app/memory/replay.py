"""Investigation Memory — hypothesis probability replay.

Reconstructs hypothesis probabilities at a given timestamp by replaying
all probability_updated memory records up to that point.
"""

import uuid
from datetime import datetime

from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.db.models import MemoryRecord, MemoryRecordType


def replay_beliefs_as_of(db: Session, case_id: str, as_of: datetime) -> dict:
    """
    Reconstruct hypothesis probabilities as they existed at `as_of` timestamp.

    Replays all probability_updated records chronologically up to the given
    timestamp, returning the final beliefs_after snapshot.

    Returns:
        dict mapping hypothesis_id -> probability, or empty dict if no
        probability_updated records exist before the timestamp.
    """
    case_uuid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id

    records = (
        db.query(MemoryRecord)
        .filter(
            MemoryRecord.case_id == case_uuid,
            MemoryRecord.record_type == MemoryRecordType.probability_updated,
            MemoryRecord.timestamp <= as_of,
        )
        .order_by(asc(MemoryRecord.timestamp))
        .all()
    )

    if not records:
        return {}

    # The last record's beliefs_after is the state at that point
    beliefs = {}
    for record in records:
        if record.beliefs_after:
            beliefs.update(record.beliefs_after)

    return beliefs
