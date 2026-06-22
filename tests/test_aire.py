"""Tests for AIRE Foundation — Prompt 30.

Tests the 7-step pipeline, dead-end prediction, and status tracking.
"""

import json
from unittest.mock import patch, MagicMock

from app.reasoning.aire import (
    get_aire_state, dead_end_predict, AIREState,
)


class TestAIREState:
    def test_initial_state(self):
        """Fresh AIRE state has zero events processed."""
        state = AIREState("test-case-123")
        assert state.events_processed == 0
        assert state.last_event_processed is None
        assert all(v is None for v in state.step_timestamps.values())
        assert state.stale_report is False

    def test_state_persistence(self):
        """get_aire_state returns the same instance for the same case."""
        s1 = get_aire_state("case-abc")
        s1.events_processed = 5
        s2 = get_aire_state("case-abc")
        assert s2.events_processed == 5


class TestDeadEndPredict:
    def test_irrelevant_action_flagged(self):
        """Action irrelevant to all hypotheses → low_discriminating_value."""
        with patch("app.reasoning.aire.get_neo4j_client") as mock_neo4j:
            mock_client = MagicMock()
            # 5 hypotheses, none reference "FingerPrint" in IMPLIES/FORBIDS
            mock_client.execute_read.return_value = [
                {"id": f"h{i}", "implied": "[]", "forbidden": "[]"}
                for i in range(5)
            ]
            mock_neo4j.return_value = mock_client

            result = dead_end_predict("case-1", "FingerPrint", "target-xyz")

        assert result["low_discriminating_value"] is True
        assert result["irrelevance_ratio"] == 1.0

    def test_relevant_action_not_flagged(self):
        """Action matching IMPLIES of most hypotheses → not low value."""
        with patch("app.reasoning.aire.get_neo4j_client") as mock_neo4j:
            mock_client = MagicMock()
            # 3 hypotheses, 2 reference "CellTowerPing"
            mock_client.execute_read.return_value = [
                {"id": "h1", "implied": json.dumps([{"evidence_type": "CellTowerPing"}]),
                 "forbidden": "[]"},
                {"id": "h2", "implied": json.dumps([{"evidence_type": "CellTowerPing"}]),
                 "forbidden": "[]"},
                {"id": "h3", "implied": "[]", "forbidden": "[]"},
            ]
            mock_neo4j.return_value = mock_client

            result = dead_end_predict("case-1", "CellTowerPing", "target-xyz")

        assert result["low_discriminating_value"] is False
        assert result["irrelevance_ratio"] < 0.8

    def test_no_hypotheses_always_low_value(self):
        """No active hypotheses → always low discriminating value."""
        with patch("app.reasoning.aire.get_neo4j_client") as mock_neo4j:
            mock_client = MagicMock()
            mock_client.execute_read.return_value = []
            mock_neo4j.return_value = mock_client

            result = dead_end_predict("case-1", "CellTowerPing", "target-xyz")

        assert result["low_discriminating_value"] is True


class TestAIREPipelineIntegration:
    def test_full_pipeline_fires_all_steps(self, client, created_case):
        """Run AIRE pipeline and confirm all 7 steps execute."""
        case_id = created_case["case_id"]

        resp = client.post(f"/cases/{case_id}/aire/process", json={
            "event_type": "graph.updated",
            "node_id": "test-node-1",
            "node_type": "Event",
            "touched_entities": ["test-node-1"],
        })
        assert resp.status_code == 200
        data = resp.json()

        # All 7 steps should be present in results
        assert "hpl_check" in data["pipeline_steps"]
        assert "contradiction_scan" in data["pipeline_steps"]
        assert "gap_rescan" in data["pipeline_steps"]
        assert "behavioral_check" in data["pipeline_steps"]
        assert "attention_recompute" in data["pipeline_steps"]
        assert "action_queue_update" in data["pipeline_steps"]
        assert "oracle_invalidation" in data["pipeline_steps"]
        assert data["events_total"] >= 1

    def test_aire_status_reflects_run(self, client, created_case):
        """After pipeline run, status endpoint shows updated timestamps."""
        case_id = created_case["case_id"]

        # Run pipeline
        client.post(f"/cases/{case_id}/aire/process", json={
            "event_type": "graph.updated",
            "node_id": "test-node-2",
            "node_type": "Event",
            "touched_entities": ["test-node-2"],
        })

        # Check status
        resp = client.get(f"/cases/{case_id}/aire/status")
        assert resp.status_code == 200
        data = resp.json()

        assert data["events_processed"] >= 1
        assert data["stale_report"] is True
        # Step timestamps should be populated
        assert data["step_timestamps"]["hpl_check"] is not None
