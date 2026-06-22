"""Chargesheet Pydantic Models — production-grade typed data structures.

Every model is fully typed, serializable, and carries the mandatory legal
disclaimer. These models are the contract between the ChargesheetEngine,
API layer, and export engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────

class FilingRecommendation(str, Enum):
    FILE = "FILE"
    HOLD = "HOLD"
    DROP = "DROP"


class TrialStrength(str, Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"


class ReadinessTier(str, Enum):
    ready_for_filing = "ready_for_filing"
    near_ready = "near_ready"
    developing = "developing"
    not_ready = "not_ready"


# ── Evidence Models ──────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    """Single piece of evidence linked to a legal element."""
    evidence_ref: str
    evidence_type: str
    source_tool: Optional[str] = None
    chain_of_custody_status: str = "unverified"
    integrity_grade: Optional[str] = None
    confidence: float = 0.0
    artifact_id: Optional[str] = None


class EvidenceBundle(BaseModel):
    """Aggregated evidence supporting one legal element."""
    element_id: str
    element_text: str
    status: str  # satisfied | partially_satisfied | unsatisfied
    items: list[EvidenceItem] = Field(default_factory=list)
    strongest_confidence: float = 0.0
    evidence_categories: dict[str, list[str]] = Field(default_factory=dict)


# ── Legal Element & Allegation ───────────────────────────────────────────

class LegalElement(BaseModel):
    """A single legal element required by a charge section."""
    element_id: str
    element_text: str
    status: str
    evidence_bundle: EvidenceBundle
    priority_score: float = 0.0
    investigation_action: Optional[str] = None


class WeakPoint(BaseModel):
    """An identified weakness in the prosecution's case."""
    element_id: str
    element_text: str
    weakness_type: str  # missing_evidence | low_confidence | broken_chain | single_source
    description: str
    remediation: Optional[str] = None
    severity: str = "medium"  # critical | high | medium | low


class MissingEvidence(BaseModel):
    """Evidence that should be collected to strengthen the case."""
    element_id: str
    element_text: str
    required_evidence_types: list[str] = Field(default_factory=list)
    evidence_category: str = "other"
    priority: float = 0.0
    suggested_action: str = ""


class Allegation(BaseModel):
    """A single charge/allegation in the chargesheet."""
    allegation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    section_id: str
    section_reference: Optional[str] = None
    statute: str = "BNS_2023"
    title: str
    filing_recommendation: FilingRecommendation = FilingRecommendation.HOLD
    elements: list[LegalElement] = Field(default_factory=list)
    satisfied_count: int = 0
    total_count: int = 0
    coverage_percentage: float = 0.0
    weak_points: list[WeakPoint] = Field(default_factory=list)
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)
    supporting_witnesses: list[dict] = Field(default_factory=list)
    supporting_digital_artifacts: list[dict] = Field(default_factory=list)
    supporting_documents: list[dict] = Field(default_factory=list)
    supporting_forensic_reports: list[dict] = Field(default_factory=list)
    financial_support: list[dict] = Field(default_factory=list)
    communication_support: list[dict] = Field(default_factory=list)
    applicable_exceptions: list[dict] = Field(default_factory=list)
    burden_of_proof: list[dict] = Field(default_factory=list)


# ── Timeline ─────────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    """Key event in the case chronology."""
    timestamp: str
    event_type: str
    description: str
    actor: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)


# ── Prosecution & Defense ────────────────────────────────────────────────

class ProsecutionStrategyNote(BaseModel):
    """Advisory note for prosecution strategy."""
    note_type: str  # strongest_charge | corroboration | sequence | witness_order
    description: str
    related_sections: list[str] = Field(default_factory=list)
    priority: str = "medium"


class DefenseRisk(BaseModel):
    """Anticipated defense argument and suggested counter."""
    risk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    risk_type: str  # alibi | procedural_violation | evidence_tampering | consent_defense
    description: str
    likelihood: str = "medium"  # high | medium | low
    affected_sections: list[str] = Field(default_factory=list)
    suggested_counter: str = ""


# ── Accused Person ───────────────────────────────────────────────────────

class AccusedPerson(BaseModel):
    """Person named in the chargesheet."""
    person_id: str
    name: str
    status: Optional[str] = None
    role_in_offence: Optional[str] = None
    linked_allegations: list[str] = Field(default_factory=list)


# ── Compliance ───────────────────────────────────────────────────────────

class ComplianceBlocker(BaseModel):
    """Procedural compliance issue blocking filing."""
    requirement_id: str
    title: str
    required_by: Optional[str] = None
    severity: str = "medium"
    guidance: str = ""
    is_overdue: bool = False


# ── The Full Chargesheet Package ─────────────────────────────────────────

LEGAL_DISCLAIMER = (
    "ADVISORY ONLY — This chargesheet package is automatically generated "
    "for investigative support purposes. All outputs are advisory and require "
    "independent human prosecutorial assessment, legal review, and judicial "
    "oversight before any filing decision. The system does not make charging "
    "decisions. Final authority rests with the investigating officer and "
    "prosecution authority."
)


class ChargesheetPackage(BaseModel):
    """Complete chargesheet package — the primary output of the system.

    Contains everything needed for prosecutorial review:
    allegations, evidence bundles, prosecution strategy,
    defense risks, compliance status, and filing readiness.
    """
    chargesheet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    generated_at: str
    version: int = 1

    # Filing readiness
    overall_readiness_score: float = 0.0
    readiness_tier: ReadinessTier = ReadinessTier.not_ready
    trial_strength: TrialStrength = TrialStrength.weak
    filing_ready: bool = False

    # Case summary
    case_summary: str = ""
    case_type: Optional[str] = None

    # Allegations
    allegations: list[Allegation] = Field(default_factory=list)
    file_count: int = 0
    hold_count: int = 0
    drop_count: int = 0

    # Accused
    accused_persons: list[AccusedPerson] = Field(default_factory=list)

    # Prosecution theory
    prosecution_theory: dict = Field(default_factory=dict)

    # Strategy
    prosecution_strategy: list[ProsecutionStrategyNote] = Field(default_factory=list)
    defense_risks: list[DefenseRisk] = Field(default_factory=list)

    # Compliance
    compliance_blockers: list[ComplianceBlocker] = Field(default_factory=list)
    procedural_compliance_percentage: int = 0
    element_readiness_percentage: int = 0

    # Certificates
    integrity_certificates: list[dict] = Field(default_factory=list)

    # Timeline
    case_timeline: list[TimelineEvent] = Field(default_factory=list)

    # Narrative
    summary_narrative: str = ""

    # Staleness tracking
    is_stale: bool = False
    stale_reason: Optional[str] = None
    evidence_count_at_generation: int = 0

    # Mandatory disclaimer
    disclaimer: str = LEGAL_DISCLAIMER
