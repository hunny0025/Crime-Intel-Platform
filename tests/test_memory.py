"""Tests for the Investigation Memory Engine.

Covers Prompt 12: memory CRUD, replay, and system-generated records.
"""

import uuid
from datetime import datetime, timezone


class TestMemoryManualRecords:
    def test_create_decision_record(self, client, created_case):
        """Human-created decision_made record."""
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/memory", json={
            "record_type": "decision_made",
            "description": "Decided to focus investigation on financial trail",
            "actor": "detective_jones",
            "reasoning": "Multiple evidence sources point to money laundering",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["record_type"] == "decision_made"
        assert data["actor"] == "detective_jones"

    def test_reject_system_actor_for_manual(self, client, created_case):
        """Manual records must not have system: actor."""
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/memory", json={
            "record_type": "decision_made",
            "description": "test",
            "actor": "system:contradiction_engine",
        })
        assert response.status_code == 400

    def test_reject_invalid_record_type(self, client, created_case):
        """Manual records can only be decision_made or lead_status_changed."""
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/memory", json={
            "record_type": "contradiction_found",
            "description": "test",
            "actor": "detective_jones",
        })
        assert response.status_code == 400


class TestMemoryListing:
    def test_list_records(self, client, created_case):
        """List memory records with pagination."""
        case_id = created_case["case_id"]

        # Create two records
        client.post(f"/cases/{case_id}/memory", json={
            "record_type": "decision_made",
            "description": "Decision A",
            "actor": "detective_a",
        })
        client.post(f"/cases/{case_id}/memory", json={
            "record_type": "lead_status_changed",
            "description": "Lead B status changed",
            "actor": "detective_b",
        })

        response = client.get(f"/cases/{case_id}/memory")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert len(data["records"]) >= 2

    def test_filter_by_type(self, client, created_case):
        """Filter by record_type."""
        case_id = created_case["case_id"]

        client.post(f"/cases/{case_id}/memory", json={
            "record_type": "decision_made",
            "description": "Decision X",
            "actor": "detective_x",
        })

        response = client.get(
            f"/cases/{case_id}/memory",
            params={"record_type": "decision_made"},
        )
        assert response.status_code == 200
        records = response.json()["records"]
        assert all(r["record_type"] == "decision_made" for r in records)


class TestMemoryReplay:
    def test_replay_empty(self, client, created_case):
        """Replay before any hypotheses returns empty."""
        case_id = created_case["case_id"]
        response = client.get(
            f"/cases/{case_id}/memory/replay",
            params={"as_of": "2020-01-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["hypothesis_probabilities"] == {}

    def test_replay_after_timestamp(self, client, created_case):
        """Replay at a future timestamp still returns empty (no probability updates yet)."""
        case_id = created_case["case_id"]
        response = client.get(
            f"/cases/{case_id}/memory/replay",
            params={"as_of": "2030-01-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        assert response.json()["hypothesis_probabilities"] == {}
