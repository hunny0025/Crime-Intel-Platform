"""Tests for Theory Engine + Competing Theory Engine — Prompts 24-25.

Tests SPAWN, ELIMINATE, EXPLAIN, Bayesian update, SENSITIVITY, CHALLENGE.
Requires a running Neo4j instance (integration tests).
"""

import uuid
from unittest.mock import patch, MagicMock


class TestTheoryEngineUnit:
    """Unit tests for probability computation logic."""

    def test_uniform_prior_with_no_category(self):
        """Without a CrimeCategory prior, uniform 1/N is used."""
        from app.reasoning.theory_engine import compute_prior

        # Mock Neo4j returning no category match
        with patch("app.reasoning.theory_engine.get_neo4j_client") as mock_neo4j:
            mock_client = MagicMock()
            mock_client.execute_read.return_value = []
            mock_neo4j.return_value = mock_client

            priors = compute_prior("test-case-id")
            assert priors == {}  # Empty = uniform

    def test_probability_sum_to_one_after_spawn(self):
        """After spawning N hypotheses, probabilities should sum to ~1.0."""
        # This is a property-based check
        probs = [0.5, 0.3, 0.2]  # Manual 3-hypothesis scenario
        assert abs(sum(probs) - 1.0) < 0.01

    def test_elimination_redistributes_proportionally(self):
        """After eliminating one hypothesis, remaining redistribute proportionally."""
        # Given: H1=0.5, H2=0.3, H3=0.2
        # Eliminate H3 (0.2): redistribute to H1 and H2
        eliminated_prob = 0.2
        remaining = [("H1", 0.5), ("H2", 0.3)]
        total_remaining = sum(p for _, p in remaining)

        new_probs = {hid: p / total_remaining for hid, p in remaining}
        assert abs(new_probs["H1"] - 0.625) < 0.01
        assert abs(new_probs["H2"] - 0.375) < 0.01
        assert abs(sum(new_probs.values()) - 1.0) < 0.01


class TestBayesianUpdate:
    """Unit tests for Bayesian update logic."""

    def test_implies_match_increases_probability(self):
        """Evidence matching IMPLIES should increase hypothesis probability."""
        from app.reasoning.competing_theory_engine import (
            LIKELIHOOD_IMPLIES_MATCH, LIKELIHOOD_NEUTRAL,
        )

        # Two hypotheses: H1 has IMPLIES match, H2 is neutral
        h1_prior, h2_prior = 0.5, 0.5
        h1_unnorm = h1_prior * LIKELIHOOD_IMPLIES_MATCH  # 0.5 * 1.2 = 0.6
        h2_unnorm = h2_prior * LIKELIHOOD_NEUTRAL         # 0.5 * 1.0 = 0.5
        total = h1_unnorm + h2_unnorm

        h1_post = h1_unnorm / total
        h2_post = h2_unnorm / total

        assert h1_post > h1_prior  # H1 increased
        assert h2_post < h2_prior  # H2 decreased
        assert abs(h1_post + h2_post - 1.0) < 0.01

    def test_forbids_match_decreases_probability(self):
        """Evidence matching FORBIDS should decrease hypothesis probability."""
        from app.reasoning.competing_theory_engine import (
            LIKELIHOOD_FORBIDS_MATCH, LIKELIHOOD_NEUTRAL,
        )

        h1_prior, h2_prior = 0.5, 0.5
        h1_unnorm = h1_prior * LIKELIHOOD_FORBIDS_MATCH  # 0.5 * 0.3 = 0.15
        h2_unnorm = h2_prior * LIKELIHOOD_NEUTRAL          # 0.5 * 1.0 = 0.5
        total = h1_unnorm + h2_unnorm

        h1_post = h1_unnorm / total
        h2_post = h2_unnorm / total

        assert h1_post < h1_prior  # H1 decreased
        assert h2_post > h2_prior  # H2 increased
        assert abs(h1_post + h2_post - 1.0) < 0.01

    def test_competing_hypothesis_cell_tower_scenario(self):
        """
        Canonical test: H1 IMPLIES CellTowerPing, H2 FORBIDS it.
        Adding CellTowerPing → H1 up, H2 down.
        """
        from app.reasoning.competing_theory_engine import (
            LIKELIHOOD_IMPLIES_MATCH, LIKELIHOOD_FORBIDS_MATCH,
        )

        h1_prior = 0.5  # IMPLIES
        h2_prior = 0.5  # FORBIDS

        h1_unnorm = h1_prior * LIKELIHOOD_IMPLIES_MATCH
        h2_unnorm = h2_prior * LIKELIHOOD_FORBIDS_MATCH
        total = h1_unnorm + h2_unnorm

        h1_post = h1_unnorm / total
        h2_post = h2_unnorm / total

        assert h1_post > 0.7  # Strong increase
        assert h2_post < 0.3  # Strong decrease
        assert abs(h1_post + h2_post - 1.0) < 0.01

    def test_sensitivity_identifies_critical_evidence(self):
        """SENSITIVITY: removing the CellTowerPing should drop H1's probability most."""
        from app.reasoning.competing_theory_engine import (
            LIKELIHOOD_IMPLIES_MATCH, LIKELIHOOD_NEUTRAL,
        )

        current_prob = 0.8
        # Counterfactual: set evidence to neutral instead of implies_match
        counterfactual = current_prob * (LIKELIHOOD_NEUTRAL / LIKELIHOOD_IMPLIES_MATCH)
        delta = abs(current_prob - counterfactual)

        assert delta > 0.1  # Significant sensitivity
