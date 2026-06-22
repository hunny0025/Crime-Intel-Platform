"""Tests for the reasoning layer — Hypothesis, Contradiction, EvidenceGap, Timeline.

Covers Prompt 11: CRUD for reasoning primitives, PREDICTED_BY/INVOLVES links,
timeline query with time window filtering.
"""

import uuid
from datetime import datetime, timezone


class TestHypothesis:
    def test_create_hypothesis(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/hypotheses", json={
            "case_id": case_id,
            "narrative": "Suspect A orchestrated a phishing campaign targeting victims via SMS",
            "probability": 0.7,
            "confidence_in_probability": 0.3,
            "status": "active",
            "provenance": "initial_analysis",
            "classification_tag": "case_sensitive",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["narrative"].startswith("Suspect A")
        assert data["probability"] == 0.7

    def test_list_hypotheses_sorted(self, client, created_case):
        """Hypotheses should be sorted by probability descending."""
        case_id = created_case["case_id"]

        # Create low probability
        client.post(f"/cases/{case_id}/hypotheses", json={
            "case_id": case_id,
            "narrative": "Low probability theory",
            "probability": 0.2,
            "classification_tag": "case_sensitive",
        })
        # Create high probability
        client.post(f"/cases/{case_id}/hypotheses", json={
            "case_id": case_id,
            "narrative": "High probability theory",
            "probability": 0.9,
            "classification_tag": "case_sensitive",
        })

        resp = client.get(f"/cases/{case_id}/hypotheses")
        assert resp.status_code == 200
        hypotheses = resp.json()
        assert len(hypotheses) >= 2
        assert hypotheses[0]["probability"] >= hypotheses[-1]["probability"]

    def test_predicted_by_link(self, client, created_case):
        """Link a hypothesis to a predicted Event via PREDICTED_BY."""
        case_id = created_case["case_id"]

        # Create an event
        event_resp = client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id,
            "event_type": "communication",
            "valid_from": "2024-01-15T10:00:00",
            "valid_to": "2024-01-15T10:05:00",
            "classification_tag": "case_sensitive",
        })
        event_id = event_resp.json()["id"]

        # Create hypothesis
        hyp_resp = client.post(f"/cases/{case_id}/hypotheses", json={
            "case_id": case_id,
            "narrative": "Suspect communicated with handler before the incident",
            "probability": 0.6,
            "classification_tag": "case_sensitive",
        })
        hyp_id = hyp_resp.json()["id"]

        # Link via PREDICTED_BY
        link_resp = client.post(
            f"/cases/{case_id}/graph/hypothesis/{hyp_id}/predicted-by",
            json={"target_node_id": event_id},
        )
        assert link_resp.status_code == 201


class TestContradiction:
    def test_create_contradiction(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id,
            "description": "Phone records show suspect at location A but camera shows them at location B",
            "severity": "high",
            "contradiction_type": "temporal",
            "classification_tag": "case_sensitive",
        })
        assert response.status_code == 201
        assert response.json()["severity"] == "high"

    def test_list_contradictions_sorted(self, client, created_case):
        """Contradictions should be sorted by severity."""
        case_id = created_case["case_id"]
        client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id, "description": "Minor issue",
            "severity": "low", "contradiction_type": "logical",
            "classification_tag": "case_sensitive",
        })
        client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id, "description": "Critical issue",
            "severity": "high", "contradiction_type": "behavioral",
            "classification_tag": "case_sensitive",
        })
        resp = client.get(f"/cases/{case_id}/contradictions")
        assert resp.status_code == 200
        contras = resp.json()
        assert contras[0]["severity"] == "high"

    def test_involves_link(self, client, created_case):
        """Link a contradiction to two involved nodes via INVOLVES."""
        case_id = created_case["case_id"]

        # Create two events
        e1 = client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id, "event_type": "location_ping",
            "classification_tag": "case_sensitive",
        }).json()
        e2 = client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id, "event_type": "camera_sighting",
            "classification_tag": "case_sensitive",
        }).json()

        # Create contradiction
        contra = client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id,
            "description": "Location data conflicts with camera footage",
            "severity": "high",
            "contradiction_type": "temporal",
            "classification_tag": "case_sensitive",
        }).json()

        # Link both events
        r1 = client.post(
            f"/cases/{case_id}/contradictions/{contra['id']}/involves",
            json={"target_node_id": e1["id"]},
        )
        r2 = client.post(
            f"/cases/{case_id}/contradictions/{contra['id']}/involves",
            json={"target_node_id": e2["id"]},
        )
        assert r1.status_code == 201
        assert r2.status_code == 201


class TestEvidenceGap:
    def test_create_evidence_gap(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/evidence-gaps", json={
            "case_id": case_id,
            "description": "Bank records for suspect's secondary account not yet obtained",
            "expected_value": "high",
            "urgency": "high",
            "status": "open",
            "classification_tag": "case_sensitive",
        })
        assert response.status_code == 201
        assert response.json()["urgency"] == "high"

    def test_list_evidence_gaps_sorted(self, client, created_case):
        """Evidence gaps should be sorted by urgency."""
        case_id = created_case["case_id"]
        client.post(f"/cases/{case_id}/evidence-gaps", json={
            "case_id": case_id, "description": "Low priority gap",
            "urgency": "low", "classification_tag": "case_sensitive",
        })
        client.post(f"/cases/{case_id}/evidence-gaps", json={
            "case_id": case_id, "description": "Urgent gap",
            "urgency": "high", "classification_tag": "case_sensitive",
        })
        resp = client.get(f"/cases/{case_id}/evidence-gaps")
        assert resp.status_code == 200
        gaps = resp.json()
        assert gaps[0]["urgency"] == "high"


class TestTimeline:
    def test_timeline_query_with_events(self, client, created_case):
        """Create events and query timeline with matching window."""
        case_id = created_case["case_id"]

        # Create events in a known time range
        client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id,
            "event_type": "communication",
            "valid_from": "2024-01-15T09:00:00",
            "valid_to": "2024-01-15T09:30:00",
            "confidence": 0.95,
            "classification_tag": "case_sensitive",
        })
        client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id,
            "event_type": "communication",
            "valid_from": "2024-01-15T14:00:00",
            "valid_to": "2024-01-15T14:30:00",
            "confidence": 0.8,
            "classification_tag": "case_sensitive",
        })

        # Query overlapping the first event only
        resp = client.get(
            f"/cases/{case_id}/graph/timeline",
            params={"from": "2024-01-15T08:00:00", "to": "2024-01-15T10:00:00"},
        )
        assert resp.status_code == 200
        timeline = resp.json()
        assert len(timeline) >= 1
        event_types = [e["event"]["event_type"] for e in timeline]
        assert "communication" in event_types

    def test_timeline_query_empty_window(self, client, created_case):
        """Query a window with no events should return empty."""
        case_id = created_case["case_id"]
        resp = client.get(
            f"/cases/{case_id}/graph/timeline",
            params={"from": "2020-01-01T00:00:00", "to": "2020-01-01T01:00:00"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0
