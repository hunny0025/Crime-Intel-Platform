"""Pydantic schemas for request/response validation across all endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.db.models import CaseStatus, ClassificationTag


# ── Cases ────────────────────────────────────────────────────────────────

class CreateCaseRequest(BaseModel):
    case_type: str
    status: CaseStatus = CaseStatus.open
    classification_tag: ClassificationTag
    created_by: str


class CaseResponse(BaseModel):
    case_id: uuid.UUID
    case_type: str
    status: CaseStatus
    classification_tag: ClassificationTag
    created_at: datetime
    updated_at: datetime
    created_by: str

    model_config = {"from_attributes": True}


# ── Case Entities ────────────────────────────────────────────────────────

class CreateEntityRequest(BaseModel):
    entity_id: uuid.UUID
    entity_type: str
    role: str


class EntityResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    entity_id: uuid.UUID
    entity_type: str
    role: str

    model_config = {"from_attributes": True}


# ── Evidence Artifacts ───────────────────────────────────────────────────

class EvidenceUploadMetadata(BaseModel):
    """Metadata submitted alongside the raw evidence file upload."""
    source_tool: str
    source_device_id: Optional[str] = None
    collection_timestamp_utc: datetime
    original_timezone: str = "UTC"
    classification_tag: ClassificationTag


class EvidenceArtifactResponse(BaseModel):
    artifact_id: uuid.UUID
    case_id: uuid.UUID
    source_tool: str
    source_device_id: Optional[str]
    collection_timestamp_utc: datetime
    original_timezone: str
    content_hash: str
    previous_record_hash: Optional[str]
    record_hash: str
    content_pointer: str
    classification_tag: ClassificationTag
    chain_of_custody_log: list
    created_at: datetime
    presigned_url: Optional[str] = None
    acquisition_method: Optional[str] = None
    composite_reliability_score: Optional[float] = None
    reliability_score: Optional[dict] = None

    model_config = {"from_attributes": True}


class ChainBreak(BaseModel):
    artifact_id: uuid.UUID
    position: int
    expected_hash: str
    actual_hash: str
    error: str


class ChainVerificationReport(BaseModel):
    valid: bool
    artifacts_checked: int
    breaks: list[ChainBreak] = Field(default_factory=list)


# ── Ingestion ────────────────────────────────────────────────────────────

class IngestionResponse(BaseModel):
    case_id: uuid.UUID
    source_format: str
    artifacts_created: int
    artifact_ids: list[uuid.UUID]
    kafka_event_id: uuid.UUID


class AuditLogEntry(BaseModel):
    audit_id: uuid.UUID
    case_id: uuid.UUID
    actor: str
    source_format: str
    num_artifacts: int
    timestamp: datetime
    kafka_event_id: uuid.UUID

    model_config = {"from_attributes": True}


# ── Events ───────────────────────────────────────────────────────────────

class EventEnvelope(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    case_id: uuid.UUID
    timestamp: datetime
    event_type: str
    payload: dict
