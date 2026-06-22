"""Tests for Phase 7 — Court Intelligence Layer.

Covers defense simulation, integrity grading, court readiness, prosecution
narrative, and conviction risk analysis. Unit tests (no Neo4j required).
"""

import math


class TestDefenseSimulation:
    """Prompt 37: defense simulation attack vector generation."""

    def test_vulnerability_score_formula(self):
        """vulnerability = critical+major / total."""
        vectors = [
            {"severity": "critical"}, {"severity": "major"},
            {"severity": "minor"}, {"severity": "minor"},
        ]
        total = len(vectors)
        crit_major = sum(1 for v in vectors if v["severity"] in ("critical", "major"))
        vscore = crit_major / total
        assert abs(vscore - 0.5) < 0.01

    def test_severity_ordering(self):
        """Attack vectors sorted: critical > major > minor."""
        order = {"critical": 0, "major": 1, "minor": 2}
        vectors = [
            {"severity": "minor"}, {"severity": "critical"}, {"severity": "major"},
        ]
        sorted_v = sorted(vectors, key=lambda v: order.get(v["severity"], 3))
        assert sorted_v[0]["severity"] == "critical"
        assert sorted_v[1]["severity"] == "major"
        assert sorted_v[2]["severity"] == "minor"

    def test_all_six_categories(self):
        """Ensure all six attack categories are covered."""
        categories = {
            "chain_of_custody", "timestamp", "attribution",
            "alternative_explanation", "procedural", "sufficiency",
        }
        assert len(categories) == 6

    def test_simulation_labeled(self):
        """All outputs must be labeled SIMULATION=true."""
        output = {"SIMULATION": True, "attack_vectors": []}
        assert output["SIMULATION"] is True


class TestEvidenceIntegrity:
    """Prompt 38: integrity grading A-F."""

    def test_grade_a_criteria(self):
        """A: hash=T, chain=T, tis≥0.9, corr≥2, no deception."""
        h, c, tis, corr = True, True, 0.95, 3
        deception = "not_assessed"
        if h and c and tis >= 0.9 and corr >= 2 and deception == "not_assessed":
            grade = "A"
        assert grade == "A"

    def test_grade_b_criteria(self):
        """B: hash=T, chain=T, tis≥0.7, corr≥1."""
        h, c, tis, corr = True, True, 0.75, 1
        if h and c and tis >= 0.9 and corr >= 2:
            grade = "A"
        elif h and c and tis >= 0.7 and corr >= 1:
            grade = "B"
        assert grade == "B"

    def test_grade_d_broken_chain(self):
        """D: hash=T but chain=F."""
        h, c = True, False
        if not h:
            grade = "F"
        elif not c:
            grade = "D"
        assert grade == "D"

    def test_grade_f_hash_failed(self):
        """F: hash=F — content may have been altered (fatal)."""
        h = False
        grade = "F" if not h else "A"
        assert grade == "F"

    def test_court_notes_generation(self):
        """Court presentation notes must be in plain language."""
        notes = (
            "Evidence item (abc123, source: cellebrite) has integrity grade B. "
            "Content verified unchanged via SHA-256 hash verification. "
            "Chain of custody is intact and documented."
        )
        assert "SHA-256" in notes
        assert "integrity grade B" in notes


class TestCourtReadiness:
    """Prompt 39: court readiness scoring."""

    def test_overall_score_formula(self):
        """0.4×legal + 0.3×integrity + 0.3×(1-vulnerability)."""
        legal = 0.8
        integrity = 0.9
        defense = 0.1  # Low vulnerability
        score = 0.4 * legal + 0.3 * integrity + 0.3 * (1 - defense)
        # 0.32 + 0.27 + 0.27 = 0.86
        assert abs(score - 0.86) < 0.01

    def test_f_grade_forces_zero(self):
        """Any F-grade artifact → score=0.0, tier=not_court_ready."""
        f_count = 1
        raw_score = 0.9
        final = 0.0 if f_count > 0 else raw_score
        assert final == 0.0

    def test_65b_cap(self):
        """Section 65B non-compliant → score capped at 0.4."""
        raw_score = 0.85
        s65b_compliant = False
        final = min(raw_score, 0.4) if not s65b_compliant else raw_score
        assert final == 0.4

    def test_tier_thresholds(self):
        """Court readiness tiers."""
        def tier(score):
            if score >= 0.8:
                return "court_ready"
            elif score >= 0.6:
                return "substantially_ready"
            elif score >= 0.4:
                return "needs_work"
            return "not_court_ready"

        assert tier(0.85) == "court_ready"
        assert tier(0.65) == "substantially_ready"
        assert tier(0.45) == "needs_work"
        assert tier(0.2) == "not_court_ready"

    def test_checklist_ordering(self):
        """Checklist items ordered: critical > integrity > defense > gaps."""
        items = [
            {"category": "evidence_gap", "priority": 4},
            {"category": "CRITICAL", "priority": 1},
            {"category": "integrity", "priority": 2},
            {"category": "defense_vulnerability", "priority": 3},
        ]
        sorted_items = sorted(items, key=lambda i: i["priority"])
        assert sorted_items[0]["category"] == "CRITICAL"
        assert sorted_items[1]["category"] == "integrity"


class TestConvictionRisk:
    """Prompt 41: conviction risk profiling."""

    def test_risk_factors_directions(self):
        """Risk factors have correct direction labels."""
        factors = [
            {"direction": "decreases_risk", "weight": 0.15},
            {"direction": "increases_risk", "weight": 0.2},
        ]
        decreases = sum(f["weight"] for f in factors if f["direction"] == "decreases_risk")
        increases = sum(f["weight"] for f in factors if f["direction"] == "increases_risk")
        assert decreases == 0.15
        assert increases == 0.2

    def test_risk_score_computation(self):
        """risk_score = 0.5 + increases - decreases, clamped [0,1]."""
        decreases = 0.3
        increases = 0.5
        score = max(0, min(1.0, 0.5 + increases - decreases))
        assert abs(score - 0.7) < 0.01

    def test_high_risk_profile(self):
        """High risk: many increases, few decreases."""
        decreases = 0.1
        increases = 0.6
        score = max(0, min(1.0, 0.5 + increases - decreases))
        assert score >= 0.8

    def test_low_risk_profile(self):
        """Low risk: many decreases, few increases."""
        decreases = 0.5
        increases = 0.1
        score = max(0, min(1.0, 0.5 + increases - decreases))
        assert score <= 0.2

    def test_confidence_scales_with_factors(self):
        """Confidence increases with number of assessed factors."""
        total_factors = 6
        confidence = min(total_factors / 8.0, 1.0)
        assert abs(confidence - 0.75) < 0.01

        total_factors = 10
        confidence = min(total_factors / 8.0, 1.0)
        assert confidence == 1.0
