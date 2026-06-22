"""Ingestion endpoint — accepts a file + source_format, runs the adapter,
writes each canonical record through the evidence write path, publishes
a Kafka event, and writes an audit log entry."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, ClassificationTag, IngestionAuditLog
from app.events.producer import get_kafka_producer
from app.ingestion.runner import run_adapter
from app.routers.evidence import write_evidence_artifact
from app.schemas import IngestionResponse, AuditLogEntry

router = APIRouter(tags=["ingestion"])


@router.post("/cases/{case_id}/ingest", response_model=IngestionResponse, status_code=201)
async def ingest(
    case_id: uuid.UUID,
    source_format: str = Form(...),
    actor: str = Form("system"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Ingest a file using a config-driven adapter, write artifacts, publish event."""
    # Verify case exists
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Read file and run adapter
    file_bytes = await file.read()

    try:
        canonical_records = run_adapter(source_format, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not canonical_records:
        raise HTTPException(status_code=400, detail="Adapter produced no records from input file")

    # Write each canonical record through the evidence write path
    artifact_ids = []
    for record in canonical_records:
        # Build content from the canonical record (JSON-encode the record itself)
        content = json.dumps(record.get("_raw", record), default=str).encode("utf-8")

        # Determine collection timestamp
        collection_ts = record.get("collection_timestamp_utc")
        if collection_ts is None or not isinstance(collection_ts, datetime):
            collection_ts = datetime.now(timezone.utc)

        artifact = write_evidence_artifact(
            db=db,
            case_id=case_id,
            content=content,
            source_tool=source_format,
            source_device_id=None,
            collection_timestamp_utc=collection_ts,
            original_timezone="UTC",
            classification_tag=case.classification_tag,
        )
        artifact_ids.append(artifact.artifact_id)

    # Publish Kafka event
    producer = get_kafka_producer()
    envelope = producer.publish(
        topic="evidence.ingested",
        case_id=case_id,
        event_type="evidence.ingested",
        payload={
            "artifact_ids": [str(aid) for aid in artifact_ids],
            "source_format": source_format,
            "num_artifacts": len(artifact_ids),
        },
    )

    # Write audit log entry
    audit_entry = IngestionAuditLog(
        audit_id=uuid.uuid4(),
        case_id=case_id,
        actor=actor,
        source_format=source_format,
        num_artifacts=len(artifact_ids),
        kafka_event_id=envelope.event_id,
    )
    db.add(audit_entry)
    db.commit()

    return IngestionResponse(
        case_id=case_id,
        source_format=source_format,
        artifacts_created=len(artifact_ids),
        artifact_ids=artifact_ids,
        kafka_event_id=envelope.event_id,
    )


@router.get("/cases/{case_id}/ingestion-audit", response_model=list[AuditLogEntry])
def get_ingestion_audit(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the ingestion audit log for a case."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    entries = (
        db.query(IngestionAuditLog)
        .filter(IngestionAuditLog.case_id == case_id)
        .order_by(IngestionAuditLog.timestamp.asc())
        .all()
    )
    return entries
