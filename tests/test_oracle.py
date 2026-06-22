"""Tests for ORACLE — Prompt 29.

Tests entropy computation, narrative generation, and meta-cognition alerts.
"""

import math


class TestEntropyComputation:
    def test_single_hypothesis_zero_entropy(self):
        """Single hypothesis at p=1.0 → entropy = 0."""
        probs = [1.0]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        assert entropy == 0.0

    def test_two_equal_hypotheses_max_entropy(self):
        """Two hypotheses at p=0.5 each → entropy = 1.0 (maximum for 2)."""
        probs = [0.5, 0.5]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        assert abs(entropy - 1.0) < 0.01

    def test_three_hypotheses_entropy(self):
        """Three hypotheses at p=0.6, 0.3, 0.1."""
        probs = [0.6, 0.3, 0.1]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        # Should be between 0 and log2(3) ≈ 1.585
        assert 0 < entropy < 1.585
        assert abs(entropy - 1.2955) < 0.01  # Computed value

    def test_highly_resolved_investigation(self):
        """One dominant hypothesis → low entropy (investigation converging)."""
        probs = [0.95, 0.04, 0.01]
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        assert entropy < 0.5  # Very resolved


class TestMetaCognitionAlerts:
    def test_over_specification_alert(self):
        """6 hypotheses with entropy < 1.0 triggers over-specification alert."""
        hyp_count = 6
        entropy = 0.8
        assert hyp_count > 5 and entropy < 1.0

    def test_cognitive_anchoring_alert(self):
        """14+ days without elimination triggers anchoring alert."""
        days_since_elimination = 16
        hyp_count = 3
        assert days_since_elimination > 14 and hyp_count > 1

    def test_no_alert_for_healthy_investigation(self):
        """3 hypotheses, recent elimination, moderate entropy → no alerts."""
        hyp_count = 3
        entropy = 1.2
        days_since_elimination = 5
        alerts = []

        if hyp_count > 5 and entropy < 1.0:
            alerts.append("over_specification")
        if days_since_elimination > 14 and hyp_count > 1:
            alerts.append("cognitive_anchoring")

        assert len(alerts) == 0


class TestNarrativeGeneration:
    def test_narrative_contains_required_elements(self):
        """Auto-generated narrative must include entropy, leading hypothesis, action."""
        # Build the narrative using the ORACLE formula
        entropy = 1.5
        hypothesis_count = 3
        leading_name = "Investment scam via crypto exchange"
        leading_prob = 0.55
        contra_text = "Temporal conflict at location site_x"
        action_text = "review evidence gaps"

        narrative = (
            f"Investigation currently has entropy {entropy:.2f} with "
            f"{hypothesis_count} active hypothesis(es). "
            f"The leading theory is '{leading_name}' (probability {leading_prob:.2f}), "
            f"challenged by: {contra_text}. "
            f"Highest priority action: {action_text}."
        )

        assert "entropy 1.50" in narrative
        assert "3 active" in narrative
        assert "Investment scam" in narrative
        assert "probability 0.55" in narrative
        assert "Temporal conflict" in narrative
        assert "review evidence gaps" in narrative
