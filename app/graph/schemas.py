"""Pydantic models for all Neo4j graph node types."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.db.models import ClassificationTag


# ── Base ─────────────────────────────────────────────────────────────────

class GraphNodeBase(BaseModel):
    """Base fields shared by all case-scoped graph nodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    classification_tag: ClassificationTag = ClassificationTag.case_sensitive
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


# ── Core Investigation Ontology ──────────────────────────────────────────

class PersonCreate(GraphNodeBase):
    display_name: str
    role: str = "unknown"  # suspect/victim/witness/associate/unknown

class PersonResponse(PersonCreate):
    merge_log: list[dict] = Field(default_factory=list)

class DeviceCreate(GraphNodeBase):
    device_type: str
    identifiers: list[str] = Field(default_factory=list)  # IMEI, serial, etc.

class DeviceResponse(DeviceCreate):
    pass

class AccountCreate(GraphNodeBase):
    account_type: str  # email/social/financial/cloud/crypto_wallet
    platform: str

class AccountResponse(AccountCreate):
    pass

class LocationCreate(GraphNodeBase):
    location_type: str  # gps_point/address/cell_tower/wifi_ap
    coordinates: Optional[str] = None  # "lat,lon"
    address: Optional[str] = None

class LocationResponse(LocationCreate):
    pass

class OrganizationCreate(GraphNodeBase):
    org_type: str
    name: str

class OrganizationResponse(OrganizationCreate):
    pass

class EventCreate(GraphNodeBase):
    event_type: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = 1.0
    artifact_id: Optional[str] = None  # reference to evidence artifact

class EventResponse(EventCreate):
    pass


# ── Identity Ontology ────────────────────────────────────────────────────

class IdentityFacetCreate(BaseModel):
    case_id: str
    facet_type: str  # phone_number/email/upi_id/social_handle/device_imei/crypto_wallet_address
    value: str
    person_id: Optional[str] = None  # If provided, link to existing person
    classification_tag: ClassificationTag = ClassificationTag.case_sensitive

class IdentityFacetResponse(BaseModel):
    id: str
    case_id: str
    facet_type: str
    value: str
    classification_tag: str
    created_at: Optional[str] = None
    linked_persons: list[dict] = Field(default_factory=list)
    is_existing: bool = False

class MergePersonsRequest(BaseModel):
    person_id_keep: str
    person_id_merge: str
    reason: str = "manual_merge"

class MergePersonsResponse(BaseModel):
    surviving_person_id: str
    merged_person_id: str
    relationships_transferred: int
    facets_transferred: int


# ── Relationships ────────────────────────────────────────────────────────

class CreateRelationshipRequest(BaseModel):
    from_node_id: str
    to_node_id: str
    relationship_type: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = 1.0
    evidence_basis: list[str] = Field(default_factory=list)  # artifact_ids

class RelationshipResponse(BaseModel):
    from_node_id: str
    to_node_id: str
    relationship_type: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confidence: Optional[float] = None
    evidence_basis: list[str] = Field(default_factory=list)

class NeighborResponse(BaseModel):
    node: dict
    relationship: dict


# ── Crime / Legal Ontology ───────────────────────────────────────────────

class CrimeCategoryResponse(BaseModel):
    id: str
    name: str
    parent_category_id: Optional[str] = None
    children: list["CrimeCategoryResponse"] = Field(default_factory=list)

class LegalSectionResponse(BaseModel):
    id: str
    statute: str
    section_number: str
    title: str
    summary: str
    elements: list[dict] = Field(default_factory=list)

class ClassifyCaseRequest(BaseModel):
    crime_category_ids: list[str]


# ── Reasoning Ontology ───────────────────────────────────────────────────

class HypothesisCreate(GraphNodeBase):
    narrative: str
    probability: float = 0.5
    confidence_in_probability: float = 0.1
    status: str = "active"  # active/eliminated
    provenance: str = "manual"

class HypothesisResponse(HypothesisCreate):
    pass

class AssumptionCreate(GraphNodeBase):
    statement: str
    criticality: str = "medium"  # low/medium/high
    verification_status: str = "unverified"  # unverified/verified/contradicted

class AssumptionResponse(AssumptionCreate):
    pass

class ContradictionCreate(GraphNodeBase):
    description: str
    severity: str = "medium"  # low/medium/high
    contradiction_type: str = "logical"  # logical/probabilistic/behavioral/temporal
    detected_at: datetime = Field(default_factory=lambda: datetime.utcnow())

class ContradictionResponse(ContradictionCreate):
    pass

class EvidenceGapCreate(GraphNodeBase):
    description: str
    expected_value: str = "medium"  # low/medium/high
    urgency: str = "medium"  # low/medium/high
    status: str = "open"  # open/resolved

class EvidenceGapResponse(EvidenceGapCreate):
    pass

class PredictedByRequest(BaseModel):
    target_node_id: str

class TimelineEntry(BaseModel):
    event: dict
    connected_entities: list[dict] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence_basis: list[str] = Field(default_factory=list)

class GraphSummary(BaseModel):
    node_counts: dict[str, int] = Field(default_factory=dict)
    relationship_counts: dict[str, int] = Field(default_factory=dict)
    unprocessed_file_artifacts: int = 0
