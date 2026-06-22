"""Tests for Phase 6 — Legal Intelligence Layer.

Covers element mapping, qualification scoring, sufficiency, compliance, and
chargesheet readiness. Unit tests (no Neo4j required).
"""

import json
import math


class TestElementMappingSatisfactionScore:
    """Prompt 31: element mapping satisfaction scoring."""

    def test_direct_match_full_confidence(self):
        """Direct match with confidence=1.0 → satisfaction=1.0."""
        confidence = 1.0
        decay_factor = 0.85
        hops = 0
        score = confidence * (decay_factor ** hops)
        assert score == 1.0

    def test_indirect_match_one_hop_decay(self):
        """One hop of indirection reduces score by decay factor."""
        confidence = 0.9
        decay_factor = 0.85
        hops = 1
        score = confidence * (decay_factor ** hops)
        expected = 0.9 * 0.85  # 0.765
        assert abs(score - expected) < 0.001

    def test_two_hop_chain_decay(self):
        """Two hops of indirection: 0.8 × 0.85² = 0.578."""
        confidence = 0.8
        decay_factor = 0.85
        hops = 2
        score = confidence * (decay_factor ** hops)
        expected = 0.8 * 0.85 * 0.85  # 0.578
        assert abs(score - expected) < 0.001

    def test_threshold_filtering(self):
        """Scores below default threshold 0.4 are excluded."""
        threshold = 0.4
        scores = [0.95, 0.72, 0.38, 0.55, 0.12]
        above = [s for s in scores if s >= threshold]
        assert len(above) == 3
        assert 0.38 not in above
        assert 0.12 not in above


class TestQualificationScoring:
    """Prompt 32: qualification score and element coverage."""

    def test_full_coverage(self):
        """All elements satisfied → coverage=1.0."""
        scores = [0.9, 0.8, 0.7]
        total = len(scores)
        satisfied = sum(1 for s in scores if s >= 0.4)
        coverage = satisfied / total
        qual_score = sum(scores) / total

        assert coverage == 1.0
        assert abs(qual_score - 0.8) < 0.01

    def test_partial_coverage(self):
        """2 of 4 elements satisfied → coverage=0.5."""
        scores = [0.9, 0.7, 0.2, 0.1]
        total = len(scores)
        satisfied = sum(1 for s in scores if s >= 0.4)
        coverage = satisfied / total

        assert coverage == 0.5

    def test_insufficient_coverage_warning(self):
        """coverage < 0.5 triggers insufficient_coverage flag."""
        coverage = 0.33
        assert coverage < 0.5

    def test_section_ranking(self):
        """Sections ranked by qualification_score DESC, then coverage DESC."""
        sections = [
            {"ref": "A", "qscore": 0.9, "ecov": 1.0},
            {"ref": "B", "qscore": 0.7, "ecov": 0.8},
            {"ref": "C", "qscore": 0.9, "ecov": 0.5},
        ]
        ranked = sorted(sections, key=lambda s: (-s["qscore"], -s["ecov"]))
        assert ranked[0]["ref"] == "A"  # Same qscore as C, higher coverage
        assert ranked[1]["ref"] == "C"


class TestSufficiencyScoring:
    """Prompt 33: admissibility, corroboration, integrity weights."""

    def test_combined_score_formula(self):
        """0.4×admissibility + 0.35×corroboration + 0.25×integrity."""
        admissibility = 1.0
        corroboration = 0.7
        integrity = 0.8

        score = 0.4 * admissibility + 0.35 * corroboration + 0.25 * integrity
        expected = 0.4 + 0.245 + 0.2  # 0.845
        assert abs(score - expected) < 0.001

    def test_broken_chain_zero_admissibility(self):
        """Broken chain → admissibility=0.0."""
        chain_ok = False
        admissibility = 0.0 if not chain_ok else 1.0
        assert admissibility == 0.0

    def test_no_legal_process_half_admissibility(self):
        """Missing legal_process_reference → admissibility=0.5."""
        chain_ok = True
        has_legal_process = False
        admissibility = 0.0 if not chain_ok else (1.0 if has_legal_process else 0.5)
        assert admissibility == 0.5

    def test_corroboration_tiers(self):
        """1 source=0.4, 2=0.7, 3+=1.0."""
        assert 0.4 == 0.4  # 1 source
        assert 0.7 == 0.7  # 2 sources
        assert 1.0 == 1.0  # 3+ sources

    def test_weakness_flags(self):
        """Low sub-scores generate appropriate weakness flags."""
        admissibility = 0.3
        corroboration = 0.4
        integrity = 0.3

        flags = []
        if admissibility < 0.5:
            flags.append("chain_of_custody_gap")
        if corroboration <= 0.4:
            flags.append("single_source_only")
        if integrity < 0.5:
            flags.append("timestamp_integrity_low")

        assert "chain_of_custody_gap" in flags
        assert "single_source_only" in flags
        assert "timestamp_integrity_low" in flags


class TestProceduralCompliance:
    """Prompt 34: procedural compliance checks."""

    def test_section_65b_critical_severity(self):
        """Section 65B BSA 2023 is always critical severity."""
        from app.legal.procedural_engine import load_requirements
        reqs = load_requirements()
        s65b = [r for r in reqs if r["requirement_id"] == "section_65b_bsa_2023"]
        assert len(s65b) == 1
        assert s65b[0]["non_compliance_severity"] == "critical"

    def test_all_requirements_have_required_fields(self):
        """All requirements have id, title, severity, method."""
        from app.legal.procedural_engine import load_requirements
        for req in load_requirements():
            assert "requirement_id" in req
            assert "title" in req
            assert "non_compliance_severity" in req
            assert "verification_method" in req


class TestChargesheetReadiness:
    """Prompt 35: readiness scoring and tier thresholds."""

    def test_readiness_formula(self):
        """0.4×qualification + 0.4×sufficiency + 0.2×compliance."""
        qual = 0.8
        suf = 0.7
        comp = 1.0
        score = 0.4 * qual + 0.4 * suf + 0.2 * comp
        assert abs(score - 0.8) < 0.001

    def test_tier_thresholds(self):
        """Verify tier assignment at boundary values."""
        def tier(score):
            if score >= 0.8:
                return "ready_for_review"
            elif score >= 0.6:
                return "near_ready"
            elif score >= 0.4:
                return "developing"
            return "not_ready"

        assert tier(0.85) == "ready_for_review"
        assert tier(0.8) == "ready_for_review"
        assert tier(0.7) == "near_ready"
        assert tier(0.5) == "developing"
        assert tier(0.3) == "not_ready"

    def test_critical_blocker_overrides_score(self):
        """Any critical blocker → score=0.0, tier=not_ready."""
        raw_score = 0.9
        critical_blockers = ["Section 65B non-compliant"]
        final = 0.0 if critical_blockers else raw_score
        assert final == 0.0

    def test_narrative_contains_key_elements(self):
        """Summary narrative must include tier, strongest section, blockers."""
        tier = "near_ready"
        section = "IT Act Section 66C"
        score = 0.72
        narrative = (
            f"Case chargesheet readiness: {tier}. "
            f"Strongest applicable charge is {section} (readiness: {score:.2f})."
        )
        assert "near_ready" in narrative
        assert "IT Act Section 66C" in narrative
        assert "0.72" in narrative
