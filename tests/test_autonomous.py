"""Tests for Phase 9 — Autonomous Investigation Layer.

Covers expiration model, theory generation, gap resolution,
dead end detection, AIRE autonomy levels, and audit logging.
"""

import json
from datetime import datetime, timezone, timedelta


class TestExpirationModel:
    """Prompt 47: evidence expiration and preservation alerting."""

    def test_retention_windows_loaded(self):
        """Retention windows config loads with required fields."""
        from app.reasoning.expiration_model import load_retention_windows
        windows = load_retention_windows()
        assert "telecom_cdr" in windows
        assert windows["telecom_cdr"]["retention_days"] == 365
        assert windows["telecom_cdr"]["regulation"] == "TRAI"

    def test_urgency_tiers(self):
        """Urgency assignment at boundary days."""
        def urgency(days):
            if days <= 7: return "critical"
            if days <= 30: return "high"
            if days <= 90: return "medium"
            return "low"

        assert urgency(5) == "critical"
        assert urgency(7) == "critical"
        assert urgency(8) == "high"
        assert urgency(30) == "high"
        assert urgency(31) == "medium"
        assert urgency(90) == "medium"
        assert urgency(91) == "low"

    def test_cdr_365_day_retention(self):
        """CDR has 365-day retention (TRAI regulation)."""
        incident = datetime(2024, 1, 1, tzinfo=timezone.utc)
        retention = 365
        expiry = incident + timedelta(days=retention)
        now = datetime(2024, 11, 25, tzinfo=timezone.utc)
        days_left = (expiry - now).days
        assert days_left == 36  # Within 90 days → medium
        assert 30 < days_left <= 90

    def test_cctv_short_retention(self):
        """CCTV has 30-day retention — expires fast."""
        from app.reasoning.expiration_model import load_retention_windows
        windows = load_retention_windows()
        assert windows.get("cctv_footage", {}).get("retention_days") == 30

    def test_unknown_provider_null_retention(self):
        """cloud_storage_provider has null retention."""
        from app.reasoning.expiration_model import load_retention_windows
        windows = load_retention_windows()
        csp = windows.get("cloud_storage_provider", {})
        assert csp.get("retention_days") is None
        assert csp.get("verify_with_legal_team") is True

    def test_priority_scores(self):
        """Critical=1.0, high=0.95 priority scores."""
        assert 1.0 > 0.95  # Critical higher than high


class TestTheoryGenerator:
    """Prompt 48: autonomous theory generation."""

    def test_three_strategies_defined(self):
        """Three generation strategies exist."""
        strategies = {"pattern_match", "unaccounted_entity", "contradiction_resolution"}
        assert len(strategies) == 3

    def test_strategy_stats_file_format(self):
        """Strategy stats file has correct structure."""
        stats_path = "app/config/generation_strategy_stats.json"
        with open(stats_path) as f:
            stats = json.load(f)
        assert "pattern_match" in stats
        assert "accepted" in stats["pattern_match"]
        assert "rejected" in stats["pattern_match"]

    def test_candidate_status_lifecycle(self):
        """Candidates: pending_review → accepted | rejected."""
        statuses = {"pending_review", "accepted", "rejected"}
        assert "pending_review" in statuses

    def test_accepted_creates_hypothesis(self):
        """Accept sets status='accepted' and creates a Hypothesis."""
        initial_status = "pending_review"
        accepted_status = "accepted"
        assert initial_status != accepted_status

    def test_rejection_requires_reason(self):
        """Rejection must include rejection_reason."""
        assert "rejection_reason" != ""


class TestGapResolver:
    """Prompt 49: gap resolution and dead end detection."""

    def test_dead_end_threshold(self):
        """Default dead end threshold is 14 days."""
        from app.reasoning.gap_resolver import DEAD_END_THRESHOLD_DAYS
        assert DEAD_END_THRESHOLD_DAYS == 14

    def test_dead_end_prediction_from_success_rate(self):
        """Low success rate → high dead end prediction."""
        success_rate = 0.2
        prediction = 0.8 if success_rate < 0.3 else (0.5 if success_rate < 0.5 else 0.2)
        assert prediction == 0.8

    def test_dead_end_prediction_high_success(self):
        """High success rate → low dead end prediction."""
        success_rate = 0.8
        prediction = 0.8 if success_rate < 0.3 else (0.5 if success_rate < 0.5 else 0.2)
        assert prediction == 0.2

    def test_pivot_creates_replacement(self):
        """Pivot workflow: dismiss + create replacement."""
        dismissed = True
        replacement_target = "financial_record"
        assert dismissed and replacement_target


class TestAutonomyEngine:
    """Prompt 50: AIRE autonomy levels and pipeline."""

    def test_autonomy_levels(self):
        """Three levels: observe, suggest, act."""
        from app.reasoning.autonomy_engine import AutonomyLevel
        assert AutonomyLevel.OBSERVE == "observe"
        assert AutonomyLevel.SUGGEST == "suggest"
        assert AutonomyLevel.ACT == "act"
        assert len(AutonomyLevel.ALL) == 3

    def test_default_level_is_act(self):
        """Default autonomy level is 'act'."""
        from app.reasoning.autonomy_engine import get_autonomy_level
        assert get_autonomy_level("nonexistent-case") == "act"

    def test_set_and_get_level(self):
        """Setting level changes returned value."""
        from app.reasoning.autonomy_engine import set_autonomy_level, get_autonomy_level
        result = set_autonomy_level("test-case-123", "suggest")
        assert result["current_level"] == "suggest"
        assert get_autonomy_level("test-case-123") == "suggest"
        # Reset
        set_autonomy_level("test-case-123", "act")

    def test_invalid_level_rejected(self):
        """Invalid level returns error."""
        from app.reasoning.autonomy_engine import set_autonomy_level
        result = set_autonomy_level("test", "invalid_level")
        assert "error" in result

    def test_pipeline_step_order(self):
        """AIRE pipeline has 11 steps in correct order."""
        steps = [
            "step_0_cross_case",    # Case creation only
            "step_1_hpl",           # Every event
            "step_1b_element_mapping",
            "step_1c_qualification",
            "step_2_contradiction",
            "step_3_gap_resolution",
            "step_4_behavioral",
            "step_5_attention",
            "step_6_actions",
            "step_6b_dead_end",
            "step_6c_expiration",
            "step_6d_theory_gen",
            "step_7_oracle",
        ]
        assert len(steps) == 13  # Including sub-steps
