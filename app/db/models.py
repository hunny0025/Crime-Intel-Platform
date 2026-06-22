import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, DateTime, Enum, ForeignKey, Integer, Float, Text, Index, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── Enums ────────────────────────────────────────────────────────────────

class CaseStatus(str, enum.Enum):
    open = "open"
    under_investigation = "under_investigation"
    closed = "closed"
    closed_convicted = "closed_convicted"
    closed_acquitted = "closed_acquitted"
    closed_insufficient_evidence = "closed_insufficient_evidence"
    closed_other = "closed_other"


class ClassificationTag(str, enum.Enum):
    public_osint = "public_osint"
    case_sensitive = "case_sensitive"
    pii = "pii"
    evidentiary = "evidentiary"
    legal_privileged = "legal_privileged"


class MemoryRecordType(str, enum.Enum):
    evidence_arrival = "evidence_arrival"
    node_created = "node_created"
    relationship_created = "relationship_created"
    hypothesis_created = "hypothesis_created"
    hypothesis_eliminated = "hypothesis_eliminated"
    probability_updated = "probability_updated"
    assumption_identified = "assumption_identified"
    contradiction_found = "contradiction_found"
    gap_identified = "gap_identified"
    lead_pursued = "lead_pursued"
    lead_status_changed = "lead_status_changed"
    decision_made = "decision_made"
    theory_revised = "theory_revised"


class ActionType(str, enum.Enum):
    review_contradiction = "review_contradiction"
    pursue_evidence_gap = "pursue_evidence_gap"
    review_high_attention_entity = "review_high_attention_entity"


class ActionStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    dismissed = "dismissed"


# ── Cases ────────────────────────────────────────────────────────────────

class Case(Base):
    __tablename__ = "cases"

    case_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_type = Column(String(255), nullable=False)
    status = Column(
        Enum(CaseStatus, name="case_status", create_constraint=True),
        nullable=False,
        default=CaseStatus.open,
    )
    classification_tag = Column(
        Enum(ClassificationTag, name="classification_tag", create_constraint=True),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by = Column(String(255), nullable=False)
    agency_id = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    entities = relationship("CaseEntity", back_populates="case", cascade="all, delete-orphan")
    evidence_artifacts = relationship("EvidenceArtifact", back_populates="case", cascade="all, delete-orphan")
    ingestion_audit_logs = relationship("IngestionAuditLog", back_populates="case", cascade="all, delete-orphan")
    memory_records = relationship("MemoryRecord", back_populates="case", cascade="all, delete-orphan")
    investigation_actions = relationship("InvestigationAction", back_populates="case", cascade="all, delete-orphan")
    osint_records = relationship("OSINTRecord", back_populates="case", cascade="all, delete-orphan")


# ── Case Entities (join table) ───────────────────────────────────────────

class CaseEntity(Base):
    __tablename__ = "case_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)

    case = relationship("Case", back_populates="entities")

    __table_args__ = (
        Index("ix_case_entities_case_id", "case_id"),
    )


# ── Evidence Artifacts ───────────────────────────────────────────────────

class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifacts"

    artifact_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_tool = Column(String(255), nullable=False)
    source_device_id = Column(String(255), nullable=True)
    collection_timestamp_utc = Column(DateTime(timezone=True), nullable=False)
    original_timezone = Column(String(50), nullable=False)
    content_hash = Column(String(64), nullable=False)
    previous_record_hash = Column(String(64), nullable=True)
    record_hash = Column(String(64), nullable=False)
    content_pointer = Column(String(500), nullable=False)
    classification_tag = Column(
        Enum(ClassificationTag, name="classification_tag", create_constraint=True, create_type=False),
        nullable=False,
    )
    chain_of_custody_log = Column(JSONB, nullable=False, default=list)
    acquisition_method = Column(String(255), nullable=True)
    composite_reliability_score = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    case = relationship("Case", back_populates="evidence_artifacts")

    __table_args__ = (
        Index("ix_evidence_artifacts_case_id", "case_id"),
    )


# ── Ingestion Audit Log ─────────────────────────────────────────────────

class IngestionAuditLog(Base):
    __tablename__ = "ingestion_audit_log"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    actor = Column(String(255), nullable=False)
    source_format = Column(String(255), nullable=False)
    num_artifacts = Column(Integer, nullable=False)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    kafka_event_id = Column(UUID(as_uuid=True), nullable=False)

    case = relationship("Case", back_populates="ingestion_audit_logs")

    __table_args__ = (
        Index("ix_ingestion_audit_log_case_id", "case_id"),
    )


# ── Investigation Memory (append-only reasoning audit log) ───────────────

class MemoryRecord(Base):
    __tablename__ = "memory_records"

    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    record_type = Column(
        Enum(MemoryRecordType, name="memory_record_type", create_constraint=True),
        nullable=False,
    )
    description = Column(Text, nullable=False)
    evidence_basis = Column(JSONB, nullable=True)  # list of artifact_id strings
    graph_refs = Column(JSONB, nullable=True)       # list of graph node/rel ids
    beliefs_before = Column(JSONB, nullable=True)   # {hypothesis_id: probability}
    beliefs_after = Column(JSONB, nullable=True)
    actor = Column(String(255), nullable=False)
    reasoning = Column(Text, nullable=True)
    memory_tags = Column(JSONB, nullable=True)

    case = relationship("Case", back_populates="memory_records")

    __table_args__ = (
        Index("ix_memory_records_case_id", "case_id"),
        Index("ix_memory_records_case_type", "case_id", "record_type"),
        Index("ix_memory_records_timestamp", "case_id", "timestamp"),
    )


# ── Investigation Actions (prioritized action queue) ─────────────────────

class InvestigationAction(Base):
    __tablename__ = "investigation_actions"

    action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type = Column(
        Enum(ActionType, name="action_type", create_constraint=True),
        nullable=False,
    )
    target_ref = Column(String(255), nullable=False)  # id of Contradiction/Gap/entity
    priority_score = Column(Float, nullable=False, default=0.0)
    status = Column(
        Enum(ActionStatus, name="action_status", create_constraint=True),
        nullable=False,
        default=ActionStatus.pending,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status_updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    dismissal_reason = Column(Text, nullable=True)

    case = relationship("Case", back_populates="investigation_actions")

    __table_args__ = (
        Index("ix_investigation_actions_case_id", "case_id"),
        Index("ix_investigation_actions_status", "case_id", "status"),
    )


# ── OSINT Records (Phase 4) ─────────────────────────────────────────────

class OSINTRecord(Base):
    __tablename__ = "osint_records"

    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(String(100), nullable=False)   # whois/dns/crt_sh/social/crypto
    query = Column(String(500), nullable=False)          # what was searched
    retrieved_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    raw_result = Column(JSONB, nullable=False)
    extracted_entities = Column(JSONB, nullable=True)     # [{entity_type, value, confidence}]
    classification_tag = Column(
        Enum(ClassificationTag, name="classification_tag", create_constraint=True, create_type=False),
        nullable=False,
        default=ClassificationTag.public_osint,
    )

    case = relationship("Case", back_populates="osint_records")

    __table_args__ = (
        Index("ix_osint_records_case_id", "case_id"),
        Index("ix_osint_records_source_type", "case_id", "source_type"),
    )


# ── Learning System ─────────────────────────────────────────────────────

class ModelWeight(Base):
    """Persisted model weights for the learning feedback system.

    Each row stores the current tuning weight for a single model/agent.
    Weights are loaded on startup and saved on every feedback event,
    ensuring no learning is lost on restart.
    """
    __tablename__ = "model_weights"

    model_name = Column(String(100), primary_key=True)
    weight = Column(Float, nullable=False, default=1.0)
    total_feedback_count = Column(Integer, nullable=False, default=0)
    accepted_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    corrected_count = Column(Integer, nullable=False, default=0)
    last_updated = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class FeedbackRecord(Base):
    """Persisted investigator feedback on AI recommendations.

    Immutable audit trail — feedback is never deleted or modified.
    Required for forensic accountability: every AI recommendation
    and every human override must be traceable.
    """
    __tablename__ = "feedback_records"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), nullable=False)
    recommendation_id = Column(String(200), nullable=False)
    source_model = Column(String(100), nullable=False)
    feedback_type = Column(String(50), nullable=False)  # accepted|rejected|corrected|irrelevant
    investigator_id = Column(String(200), nullable=False)
    correction = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_feedback_records_case_id", "case_id"),
        Index("ix_feedback_records_source_model", "source_model"),
    )


# ── Chargesheet System ──────────────────────────────────────────────────

class ChargesheetPackageRecord(Base):
    """Persisted chargesheet package for audit trail and retrieval.

    Stores the full serialized ChargesheetPackage as JSONB for
    complete reproducibility. Each generation creates a new version.
    """
    __tablename__ = "chargesheet_packages"

    chargesheet_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    version = Column(Integer, nullable=False, default=1)
    overall_readiness_score = Column(Float, nullable=False, default=0.0)
    readiness_tier = Column(String(50), nullable=False, default="not_ready")
    trial_strength = Column(String(50), nullable=False, default="weak")
    filing_ready = Column(String(10), nullable=False, default="false")
    file_count = Column(Integer, nullable=False, default=0)
    hold_count = Column(Integer, nullable=False, default=0)
    drop_count = Column(Integer, nullable=False, default=0)
    summary_narrative = Column(Text, nullable=True)
    package_data = Column(JSONB, nullable=False)
    evidence_count_at_generation = Column(Integer, nullable=False, default=0)
    is_stale = Column(String(10), nullable=False, default="false")

    __table_args__ = (
        Index("ix_chargesheet_packages_case_id", "case_id"),
        Index("ix_chargesheet_packages_case_version", "case_id", "version"),
    )


class ChargesheetAllegationRecord(Base):
    """Queryable allegation storage for per-charge analysis.

    Each row corresponds to one charge/section in a chargesheet package.
    Enables filtering and reporting across allegations without deserializing
    the full package JSONB.
    """
    __tablename__ = "chargesheet_allegations"

    allegation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chargesheet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chargesheet_packages.chargesheet_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id = Column(UUID(as_uuid=True), nullable=False)
    section_id = Column(String(100), nullable=False)
    section_reference = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    statute = Column(String(100), nullable=False, default="BNS_2023")
    filing_recommendation = Column(String(10), nullable=False, default="HOLD")
    satisfied_count = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)
    coverage_percentage = Column(Float, nullable=False, default=0.0)
    allegation_data = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_chargesheet_allegations_case_id", "case_id"),
        Index("ix_chargesheet_allegations_chargesheet_id", "chargesheet_id"),
    )


class ChargesheetNote(Base):
    """Prosecutor notes on specific allegations.

    Immutable audit trail — notes are never deleted or modified.
    Each note is linked to a specific allegation in a chargesheet.
    """
    __tablename__ = "chargesheet_notes"

    note_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    allegation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chargesheet_allegations.allegation_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id = Column(UUID(as_uuid=True), nullable=False)
    author = Column(String(255), nullable=False)
    note_text = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_chargesheet_notes_allegation_id", "allegation_id"),
        Index("ix_chargesheet_notes_case_id", "case_id"),
    )


class PostgresAgency(Base):
    __tablename__ = "agencies"

    agency_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agency_name = Column(String(255), nullable=False)


class AIREAuditActionRecord(Base):
    __tablename__ = "aire_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
    )
    aire_step = Column(String(255), nullable=False)
    action_type = Column(String(255), nullable=False)
    target_ref = Column(String(255), nullable=False)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reversible = Column(Boolean, default=True, nullable=False)
    reversal_endpoint = Column(String(500), nullable=True)
    autonomy_level = Column(String(50), nullable=False)
    agency_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agencies.agency_id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

