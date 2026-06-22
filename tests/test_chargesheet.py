"""Tests for Chargesheet Generation System.

Covers: generation, field validation, filing recommendations, history,
export, staleness, prosecution strategy, missing evidence, disclaimer.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest


# ── Pydantic Model Tests ────────────────────────────────────────────────

class TestChargesheetModels:
    """Test Pydantic model construction and serialization."""

    def test_chargesheet_package_construction(self):
        from app.legal.chargesheet_models import (
            ChargesheetPackage, Allegation, LegalElement, EvidenceBundle,
            FilingRecommendation, ReadinessTier, TrialStrength,
            LEGAL_DISCLAIMER,
        )

        package = ChargesheetPackage(
            case_id="test-case-001",
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_readiness_score=0.65,
            readiness_tier=ReadinessTier.near_ready,
            trial_strength=TrialStrength.moderate,
            filing_ready=False,
            case_summary="Test case summary",
            allegations=[
                Allegation(
                    section_id="ls-bns-318",
                    title="Cheating",
                    filing_recommendation=FilingRecommendation.FILE,
                    satisfied_count=3,
                    total_count=4,
                    coverage_percentage=75.0,
                    elements=[
                        LegalElement(
                            element_id="le-bns318-1",
                            element_text="Deception established",
                            status="satisfied",
                            evidence_bundle=EvidenceBundle(
                                element_id="le-bns318-1",
                                element_text="Deception established",
                                status="satisfied",
                            ),
                        ),
                    ],
                ),
            ],
        )

        assert package.case_id == "test-case-001"
        assert package.overall_readiness_score == 0.65
        assert package.readiness_tier == ReadinessTier.near_ready
        assert package.allegations[0].filing_recommendation == FilingRecommendation.FILE
        assert package.disclaimer == LEGAL_DISCLAIMER

    def test_filing_recommendation_enum(self):
        from app.legal.chargesheet_models import FilingRecommendation

        assert FilingRecommendation.FILE == "FILE"
        assert FilingRecommendation.HOLD == "HOLD"
        assert FilingRecommendation.DROP == "DROP"

    def test_readiness_tier_enum(self):
        from app.legal.chargesheet_models import ReadinessTier

        assert ReadinessTier.ready_for_filing == "ready_for_filing"
        assert ReadinessTier.not_ready == "not_ready"

    def test_package_serialization(self):
        from app.legal.chargesheet_models import ChargesheetPackage

        package = ChargesheetPackage(
            case_id="test-serialization",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        data = package.model_dump()

        assert isinstance(data, dict)
        assert data["case_id"] == "test-serialization"
        assert "disclaimer" in data
        assert data["disclaimer"]  # Not empty
        assert "ADVISORY" in data["disclaimer"]

    def test_disclaimer_always_present(self):
        from app.legal.chargesheet_models import ChargesheetPackage, LEGAL_DISCLAIMER

        # Even minimal construction includes disclaimer
        package = ChargesheetPackage(
            case_id="test-disclaimer",
            generated_at="2026-01-01T00:00:00Z",
        )
        assert package.disclaimer == LEGAL_DISCLAIMER
        data = package.model_dump()
        assert data["disclaimer"] == LEGAL_DISCLAIMER


# ── Filing Recommendation Logic Tests ───────────────────────────────────

class TestFilingRecommendations:
    """Test filing recommendation thresholds."""

    def test_file_threshold(self):
        """70%+ coverage → FILE."""
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import Allegation, FilingRecommendation

        allegations = [
            Allegation(
                section_id="ls-test",
                title="Test",
                coverage_percentage=75.0,
            ),
        ]
        engine = ChargesheetEngine.__new__(ChargesheetEngine)
        result = engine._compute_filing_recommendations(allegations)
        assert result[0].filing_recommendation == FilingRecommendation.FILE

    def test_hold_threshold(self):
        """40-69% coverage → HOLD."""
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import Allegation, FilingRecommendation

        allegations = [
            Allegation(
                section_id="ls-test",
                title="Test",
                coverage_percentage=55.0,
            ),
        ]
        engine = ChargesheetEngine.__new__(ChargesheetEngine)
        result = engine._compute_filing_recommendations(allegations)
        assert result[0].filing_recommendation == FilingRecommendation.HOLD

    def test_drop_threshold(self):
        """<40% coverage → DROP."""
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import Allegation, FilingRecommendation

        allegations = [
            Allegation(
                section_id="ls-test",
                title="Test",
                coverage_percentage=20.0,
            ),
        ]
        engine = ChargesheetEngine.__new__(ChargesheetEngine)
        result = engine._compute_filing_recommendations(allegations)
        assert result[0].filing_recommendation == FilingRecommendation.DROP


# ── Readiness Score Tests ───────────────────────────────────────────────

class TestReadinessScoring:
    """Test readiness score calculation and tier mapping."""

    def test_tier_mapping(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import ReadinessTier

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        assert engine._score_to_tier(0.85) == ReadinessTier.ready_for_filing
        assert engine._score_to_tier(0.65) == ReadinessTier.near_ready
        assert engine._score_to_tier(0.45) == ReadinessTier.developing
        assert engine._score_to_tier(0.25) == ReadinessTier.not_ready

    def test_trial_strength_estimation(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import TrialStrength

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        # Strong: high score + high coverage
        assert engine._estimate_trial_strength(0.80, 0.75, False, []) == TrialStrength.strong
        # Moderate: medium score
        assert engine._estimate_trial_strength(0.55, 0.50, False, []) == TrialStrength.moderate
        # Weak: low score
        assert engine._estimate_trial_strength(0.30, 0.20, False, []) == TrialStrength.weak
        # Weak: critical blocker
        assert engine._estimate_trial_strength(0.90, 0.90, True, []) == TrialStrength.weak

    def test_element_coverage_calculation(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import Allegation

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        allegations = [
            Allegation(section_id="s1", title="A", satisfied_count=3, total_count=4),
            Allegation(section_id="s2", title="B", satisfied_count=1, total_count=4),
        ]
        # 4 satisfied out of 8 total = 0.5
        coverage = engine._compute_element_coverage(allegations)
        assert abs(coverage - 0.5) < 0.01

    def test_empty_allegations_zero_coverage(self):
        from app.legal.chargesheet_engine import ChargesheetEngine

        engine = ChargesheetEngine.__new__(ChargesheetEngine)
        assert engine._compute_element_coverage([]) == 0.0


# ── Weak Point Detection Tests ──────────────────────────────────────────

class TestWeakPointDetection:
    """Test weakness identification in allegations."""

    def test_missing_evidence_detected(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import (
            Allegation, LegalElement, EvidenceBundle, WeakPoint,
        )

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        allegation = Allegation(
            section_id="ls-test",
            title="Test Charge",
            elements=[
                LegalElement(
                    element_id="le-1",
                    element_text="Intent established",
                    status="unsatisfied",
                    evidence_bundle=EvidenceBundle(
                        element_id="le-1",
                        element_text="Intent established",
                        status="unsatisfied",
                    ),
                    priority_score=0.9,
                ),
            ],
        )

        weak_points = engine._get_weak_points(allegation)
        assert len(weak_points) >= 1
        assert weak_points[0].weakness_type == "missing_evidence"
        assert weak_points[0].severity == "critical"

    def test_single_source_warning(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import (
            Allegation, LegalElement, EvidenceBundle, EvidenceItem,
        )

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        allegation = Allegation(
            section_id="ls-test",
            title="Test",
            elements=[
                LegalElement(
                    element_id="le-1",
                    element_text="Property transfer",
                    status="partially_satisfied",
                    evidence_bundle=EvidenceBundle(
                        element_id="le-1",
                        element_text="Property transfer",
                        status="partially_satisfied",
                        items=[
                            EvidenceItem(
                                evidence_ref="ev-001",
                                evidence_type="bank_statement",
                                confidence=0.7,
                            ),
                        ],
                        strongest_confidence=0.7,
                    ),
                ),
            ],
        )

        weak_points = engine._get_weak_points(allegation)
        types = [wp.weakness_type for wp in weak_points]
        assert "single_source" in types


# ── Export Tests ─────────────────────────────────────────────────────────

class TestChargesheetExport:
    """Test the text export engine."""

    def test_export_contains_header(self):
        from app.legal.chargesheet_export import export_chargesheet_text

        package_data = {
            "case_id": "test-export",
            "generated_at": "2026-01-01T00:00:00Z",
            "version": 1,
            "case_type": "Online Investment Fraud",
            "overall_readiness_score": 0.65,
            "readiness_tier": "near_ready",
            "trial_strength": "moderate",
            "filing_ready": False,
            "element_readiness_percentage": 50,
            "procedural_compliance_percentage": 80,
            "file_count": 2,
            "hold_count": 1,
            "drop_count": 0,
            "case_summary": "Test case.",
            "summary_narrative": "Test narrative.",
            "allegations": [],
            "accused_persons": [],
            "prosecution_theory": {},
            "compliance_blockers": [],
            "prosecution_strategy": [],
            "defense_risks": [],
            "integrity_certificates": [],
        }

        text = export_chargesheet_text(package_data)
        assert "CHARGESHEET INTELLIGENCE REPORT" in text
        assert "test-export" in text
        assert "ADVISORY" in text
        assert "FILING READINESS SUMMARY" in text
        assert "65%" in text  # Score formatted as percentage

    def test_export_disclaimer_present(self):
        from app.legal.chargesheet_export import export_chargesheet_text
        from app.legal.chargesheet_models import LEGAL_DISCLAIMER

        package_data = {
            "case_id": "disclaimer-test",
            "generated_at": "2026-01-01",
            "version": 1,
            "overall_readiness_score": 0.0,
            "readiness_tier": "not_ready",
            "trial_strength": "weak",
            "filing_ready": False,
        }

        text = export_chargesheet_text(package_data)
        assert LEGAL_DISCLAIMER in text

    def test_export_allegations_formatted(self):
        from app.legal.chargesheet_export import export_chargesheet_text

        package_data = {
            "case_id": "allege-test",
            "generated_at": "2026-01-01",
            "version": 1,
            "overall_readiness_score": 0.5,
            "readiness_tier": "developing",
            "trial_strength": "moderate",
            "filing_ready": False,
            "allegations": [
                {
                    "title": "Cheating (BNS 318)",
                    "section_id": "ls-bns-318",
                    "section_reference": "Section 318",
                    "statute": "BNS_2023",
                    "filing_recommendation": "FILE",
                    "coverage_percentage": 75.0,
                    "satisfied_count": 3,
                    "total_count": 4,
                    "elements": [
                        {
                            "element_text": "Deception",
                            "status": "satisfied",
                        },
                    ],
                    "weak_points": [],
                    "supporting_witnesses": [{"name": "Witness A"}],
                    "supporting_digital_artifacts": [],
                    "supporting_documents": [],
                    "supporting_forensic_reports": [],
                    "financial_support": [],
                },
            ],
        }

        text = export_chargesheet_text(package_data)
        assert "[FILE]" in text
        assert "Cheating" in text
        assert "75%" in text
        assert "1 witness" in text


# ── Staleness Tests ─────────────────────────────────────────────────────

class TestChargesheetStaleness:
    """Test staleness marking via AIRE integration."""

    def test_staleness_step_triggers_on_evidence_event(self):
        from app.reasoning.aire import _step_chargesheet_staleness

        with patch("app.legal.chargesheet_engine.mark_chargesheet_stale") as mock_mark:
            mock_mark.return_value = {"marked_stale": "cs-123", "reason": "test"}
            result = _step_chargesheet_staleness("test-case", "evidence.normalized")
            mock_mark.assert_called_once()
            assert result["marked_stale"] == "cs-123"

    def test_staleness_step_skips_irrelevant_events(self):
        from app.reasoning.aire import _step_chargesheet_staleness

        result = _step_chargesheet_staleness("test-case", "case.created")
        assert result.get("skipped") is True


# ── Prosecution Strategy Tests ──────────────────────────────────────────

class TestProsecutionStrategy:
    """Test prosecution strategy generation."""

    def test_strongest_charge_identified(self):
        from app.legal.chargesheet_engine import ChargesheetEngine
        from app.legal.chargesheet_models import Allegation, FilingRecommendation

        engine = ChargesheetEngine.__new__(ChargesheetEngine)

        allegations = [
            Allegation(
                section_id="s1", title="Weak Charge",
                filing_recommendation=FilingRecommendation.HOLD,
                coverage_percentage=40.0,
            ),
            Allegation(
                section_id="s2", title="Strong Charge",
                filing_recommendation=FilingRecommendation.FILE,
                coverage_percentage=85.0,
                satisfied_count=4, total_count=5,
            ),
        ]

        strategy = engine._build_prosecution_strategy(allegations)
        assert len(strategy) >= 1
        strongest_note = next(
            (n for n in strategy if n.note_type == "strongest_charge"), None,
        )
        assert strongest_note is not None
        assert "Strong Charge" in strongest_note.description
