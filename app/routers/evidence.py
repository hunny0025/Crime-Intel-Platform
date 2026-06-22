"""Evidence artifact endpoints — upload, retrieve, list, and chain verification."""

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, EvidenceArtifact, ClassificationTag
from app.storage.minio_client import get_minio_client
from app.schemas import (
    EvidenceArtifactResponse,
    ChainVerificationReport,
    ChainBreak,
)

router = APIRouter(tags=["evidence"])


def compute_record_hash(
    artifact_id: uuid.UUID,
    case_id: uuid.UUID,
    source_tool: str,
    source_device_id: str | None,
    collection_timestamp_utc: datetime,
    original_timezone: str,
    content_hash: str,
    previous_record_hash: str | None,
    content_pointer: str,
    classification_tag: str,
) -> str:
    """Compute the SHA-256 record hash from all record fields."""
    parts = [
        str(artifact_id),
        str(case_id),
        source_tool,
        source_device_id or "",
        collection_timestamp_utc.isoformat(),
        original_timezone,
        content_hash,
        previous_record_hash or "",
        content_pointer,
        classification_tag,
    ]
    concatenated = "|".join(parts)
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def write_evidence_artifact(
    db: Session,
    case_id: uuid.UUID,
    content: bytes,
    source_tool: str,
    source_device_id: str | None,
    collection_timestamp_utc: datetime,
    original_timezone: str,
    classification_tag: ClassificationTag,
) -> EvidenceArtifact:
    """
    Core write path: compute hashes, upload to MinIO, insert chained record.
    This function is used by both the direct upload endpoint and the ingestion adapter.
    """
    minio = get_minio_client()

    # Generate IDs
    artifact_id = uuid.uuid4()
    content_pointer = f"{case_id}/{artifact_id}"

    # Compute content hash
    content_hash = hashlib.sha256(content).hexdigest()

    # Upload to MinIO
    minio.upload_bytes(content_pointer, content)

    # Get previous record hash (latest artifact for this case)
    previous = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.case_id == case_id)
        .order_by(EvidenceArtifact.created_at.desc())
        .first()
    )
    previous_record_hash = previous.record_hash if previous else None

    # Compute record hash
    classification_value = (
        classification_tag.value
        if isinstance(classification_tag, ClassificationTag)
        else classification_tag
    )
    record_hash = compute_record_hash(
        artifact_id=artifact_id,
        case_id=case_id,
        source_tool=source_tool,
        source_device_id=source_device_id,
        collection_timestamp_utc=collection_timestamp_utc,
        original_timezone=original_timezone,
        content_hash=content_hash,
        previous_record_hash=previous_record_hash,
        content_pointer=content_pointer,
        classification_tag=classification_value,
    )

    # Insert the record
    artifact = EvidenceArtifact(
        artifact_id=artifact_id,
        case_id=case_id,
        source_tool=source_tool,
        source_device_id=source_device_id,
        collection_timestamp_utc=collection_timestamp_utc,
        original_timezone=original_timezone,
        content_hash=content_hash,
        previous_record_hash=previous_record_hash,
        record_hash=record_hash,
        content_pointer=content_pointer,
        classification_tag=classification_tag,
        chain_of_custody_log=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": "system",
                "action": "created",
            }
        ],
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/cases/{case_id}/evidence", response_model=EvidenceArtifactResponse, status_code=201)
async def upload_evidence(
    case_id: uuid.UUID,
    source_tool: str = Form(...),
    source_device_id: str | None = Form(None),
    collection_timestamp_utc: datetime = Form(...),
    original_timezone: str = Form("UTC"),
    classification_tag: ClassificationTag = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload raw evidence bytes with metadata. Chains into the case's evidence chain."""
    # Verify case exists
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    content = await file.read()

    artifact = write_evidence_artifact(
        db=db,
        case_id=case_id,
        content=content,
        source_tool=source_tool,
        source_device_id=source_device_id,
        collection_timestamp_utc=collection_timestamp_utc,
        original_timezone=original_timezone,
        classification_tag=classification_tag,
    )

    return artifact


@router.get("/evidence/{artifact_id}", response_model=EvidenceArtifactResponse)
def get_evidence(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retrieve evidence metadata and a presigned MinIO URL for content.
    Appends a 'read' entry to the chain_of_custody_log."""
    artifact = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.artifact_id == artifact_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Generate presigned URL
    minio = get_minio_client()
    presigned_url = minio.get_presigned_url(artifact.content_pointer)

    # Append read entry to chain of custody log
    log = list(artifact.chain_of_custody_log or [])
    log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": "system",
        "action": "read",
    })
    artifact.chain_of_custody_log = log
    db.commit()
    db.refresh(artifact)

    response = EvidenceArtifactResponse.model_validate(artifact)
    response.presigned_url = presigned_url

    try:
        from app.intelligence.reliability import compute_reliability
        from dataclasses import asdict
        score = compute_reliability(str(artifact.artifact_id), str(artifact.case_id), db)
        if score:
            response.reliability_score = asdict(score)
    except Exception:
        pass

    return response


@router.get("/evidence/{artifact_id}/download")
def download_evidence_file(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    """Directly download the evidence file content."""
    artifact = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.artifact_id == artifact_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    minio = get_minio_client()
    try:
        content = minio.download_bytes(artifact.content_pointer)
        filename = artifact.content_pointer.split('/')[-1]
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file content: {e}")


@router.get("/cases/{case_id}/evidence", response_model=list[EvidenceArtifactResponse])
def list_evidence(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """List all evidence artifacts for a case in chain order (creation time)."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    artifacts = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.case_id == case_id)
        .order_by(EvidenceArtifact.created_at.asc())
        .all()
    )
    return artifacts


@router.get("/cases/{case_id}/chain-of-custody/verify", response_model=ChainVerificationReport)
def verify_chain(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Walk the evidence chain for a case and verify each record_hash.
    Reports any breaks found in the chain."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    artifacts = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.case_id == case_id)
        .order_by(EvidenceArtifact.created_at.asc())
        .all()
    )

    breaks = []

    for i, artifact in enumerate(artifacts):
        # Recompute the record hash from stored fields
        classification_value = (
            artifact.classification_tag.value
            if isinstance(artifact.classification_tag, ClassificationTag)
            else artifact.classification_tag
        )
        recomputed = compute_record_hash(
            artifact_id=artifact.artifact_id,
            case_id=artifact.case_id,
            source_tool=artifact.source_tool,
            source_device_id=artifact.source_device_id,
            collection_timestamp_utc=artifact.collection_timestamp_utc,
            original_timezone=artifact.original_timezone,
            content_hash=artifact.content_hash,
            previous_record_hash=artifact.previous_record_hash,
            content_pointer=artifact.content_pointer,
            classification_tag=classification_value,
        )

        # Check 1: recomputed hash matches stored record_hash
        if recomputed != artifact.record_hash:
            breaks.append(ChainBreak(
                artifact_id=artifact.artifact_id,
                position=i,
                expected_hash=recomputed,
                actual_hash=artifact.record_hash,
                error="record_hash mismatch: recomputed hash does not match stored record_hash",
            ))

        # Check 2: stored record_hash matches next artifact's previous_record_hash
        if i < len(artifacts) - 1:
            next_artifact = artifacts[i + 1]
            if next_artifact.previous_record_hash != artifact.record_hash:
                breaks.append(ChainBreak(
                    artifact_id=next_artifact.artifact_id,
                    position=i + 1,
                    expected_hash=artifact.record_hash,
                    actual_hash=next_artifact.previous_record_hash or "",
                    error="chain link broken: previous_record_hash does not match preceding record's record_hash",
                ))

    return ChainVerificationReport(
        valid=len(breaks) == 0,
        artifacts_checked=len(artifacts),
        breaks=breaks,
    )


@router.post("/evidence/{artifact_id}/reliability")
def calculate_reliability(artifact_id: uuid.UUID, db: Session = Depends(get_db)):
    """Compute and return the reliability score (triggering database persist)."""
    artifact = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.artifact_id == artifact_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    from app.intelligence.reliability import compute_reliability
    from dataclasses import asdict

    score = compute_reliability(str(artifact.artifact_id), str(artifact.case_id), db)
    if not score:
        raise HTTPException(status_code=500, detail="Failed to compute reliability score")

    return asdict(score)


@router.post("/cases/{case_id}/evidence/reliability-batch")
def calculate_reliability_batch(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Compute and return reliability scores for all artifacts in a case (triggering database persist)."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    artifacts = (
        db.query(EvidenceArtifact)
        .filter(EvidenceArtifact.case_id == case_id)
        .all()
    )

    from app.intelligence.reliability import compute_reliability
    from dataclasses import asdict

    results = {}
    for artifact in artifacts:
        score = compute_reliability(str(artifact.artifact_id), str(case_id), db)
        if score:
            results[str(artifact.artifact_id)] = asdict(score)

    return results
