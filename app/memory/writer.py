"""Investigation Memory — shared write interface.

This module is the canonical way to write memory records. All engines
(Contradiction Engine, Evidence Gap Engine, Attention Engine, Navigation
Engine, and future Phase 5 agents) use this function.

Signature:
    write_memory_record(
        db: Session,                     # SQLAlchemy session
        case_id: str,                    # case UUID as string
        record_type: MemoryRecordType,   # enum value
        description: str,                # human-readable summary
        actor: str,                      # "system:<engine_name>" or human investigator id
        evidence_basis: list[str] = None,   # artifact_id UUIDs
        graph_refs: list[str] = None,       # graph node/relationship ids
        beliefs_before: dict = None,        # {hypothesis_id: probability}
        beliefs_after: dict = None,
        reasoning: str = None,              # why this record was created
    ) -> MemoryRecord

Returns the created MemoryRecord ORM object.

IMPORTANT: This table is APPEND-ONLY. The write function does INSERT only.
No UPDATE or DELETE operations are ever performed on memory_records.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import MemoryRecord, MemoryRecordType

logger = logging.getLogger(__name__)


def write_memory_record(
    db: Optional[Session] = None,
    case_id: str = None,
    record_type: MemoryRecordType = None,
    description: str = "",
    actor: str = "system",
    evidence_basis: Optional[list[str]] = None,
    graph_refs: Optional[list[str]] = None,
    beliefs_before: Optional[dict] = None,
    beliefs_after: Optional[dict] = None,
    reasoning: Optional[str] = None,
    tags: Optional[dict] = None,
) -> MemoryRecord:
    """
    Write a single memory record (append-only).

    Args:
        db: Optional active SQLAlchemy session. If None, a new session is created, committed, and closed.
        case_id: The case this record belongs to.
        record_type: One of MemoryRecordType enum values.
        description: Human-readable summary of what happened.
        actor: Who/what created this record.
        evidence_basis: List of artifact_id strings (UUIDs) referenced.
        graph_refs: List of graph node or relationship ids referenced.
        beliefs_before: For probability_updated records: snapshot before.
        beliefs_after: For probability_updated records: snapshot after.
        reasoning: Explanation of why this record was created.
        tags: Optional JSONB dict of memory tags.

    Returns:
        The created MemoryRecord.
    """
    record = MemoryRecord(
        record_id=uuid.uuid4(),
        case_id=uuid.UUID(case_id) if isinstance(case_id, str) else case_id,
        timestamp=datetime.now(timezone.utc),
        record_type=record_type,
        description=description,
        evidence_basis=evidence_basis,
        graph_refs=graph_refs,
        beliefs_before=beliefs_before,
        beliefs_after=beliefs_after,
        actor=actor,
        reasoning=reasoning,
        memory_tags=tags,
    )

    if db is None:
        from app.db.session import SessionLocal
        standalone_db = SessionLocal()
        try:
            standalone_db.add(record)
            standalone_db.commit()
            # Refresh to load attributes if needed
            standalone_db.refresh(record)
        except Exception:
            standalone_db.rollback()
            raise
        finally:
            standalone_db.close()
    else:
        db.add(record)
        db.flush()  # Assign record_id without committing

    logger.info(
        "Memory record: [%s] %s — %s (actor=%s)",
        record_type.value if hasattr(record_type, "value") else record_type, case_id, description[:80], actor,
    )
    return record
