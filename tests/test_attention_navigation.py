"""Tests for the Attention Engine and Navigation Engine.

Covers Prompt 15 (attention scoring) and Prompt 16 (action queue).
"""

import uuid


class TestAttentionEngine:
    def test_initial_score_zero(self, client, created_case):
        """Node with no contradictions/gaps/hypotheses has score 0."""
        case_id = created_case["case_id"]

        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Clean Person",
            "role": "witness", "classification_tag": "case_sensitive",
        }).json()

        # Heatmap should be empty or this person should have 0
        heatmap_resp = client.get(f"/cases/{case_id}/attention-heatmap")
        assert heatmap_resp.status_code == 200
        heatmap = heatmap_resp.json()
        person_scores = [h for h in heatmap if h["node_id"] == person["id"]]
        # Either not in heatmap (score 0) or has score 0
        if person_scores:
            assert person_scores[0]["attention_value"] == 0

    def test_contradiction_raises_score(self, client, created_case):
        """Creating a contradiction INVOLVES a node → score jumps to 0.4."""
        case_id = created_case["case_id"]

        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Contradicted Person",
            "role": "suspect", "classification_tag": "case_sensitive",
        }).json()

        # Create a contradiction involving this person
        contra = client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id,
            "description": "Test contradiction for attention scoring",
            "severity": "high",
            "contradiction_type": "logical",
            "classification_tag": "case_sensitive",
        }).json()

        # Link via INVOLVES
        client.post(
            f"/cases/{case_id}/contradictions/{contra['id']}/involves",
            json={"target_node_id": person["id"]},
        )

        # Check heatmap
        heatmap_resp = client.get(f"/cases/{case_id}/attention-heatmap")
        heatmap = heatmap_resp.json()
        person_scores = [h for h in heatmap if h["node_id"] == person["id"]]
        assert len(person_scores) >= 1
        score = person_scores[0]
        assert score["attention_value"] >= 0.4
        assert score["breakdown"]["contradiction_factor"] == 0.4

    def test_gap_adds_to_score(self, client, created_case):
        """Adding an EvidenceGap RELATES_TO a node → score increases by 0.3."""
        case_id = created_case["case_id"]

        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Gapped Person",
            "role": "suspect", "classification_tag": "case_sensitive",
        }).json()

        # Create contradiction (0.4)
        contra = client.post(f"/cases/{case_id}/contradictions", json={
            "case_id": case_id, "description": "Contradiction",
            "severity": "high", "contradiction_type": "logical",
            "classification_tag": "case_sensitive",
        }).json()
        client.post(
            f"/cases/{case_id}/contradictions/{contra['id']}/involves",
            json={"target_node_id": person["id"]},
        )

        # Create evidence gap (0.3)
        gap = client.post(f"/cases/{case_id}/evidence-gaps", json={
            "case_id": case_id, "description": "Missing evidence",
            "urgency": "high", "classification_tag": "case_sensitive",
        }).json()
        client.post(
            f"/cases/{case_id}/evidence-gaps/{gap['id']}/relates-to",
            json={"target_node_id": person["id"]},
        )

        # Check combined score: 0.4 + 0.3 = 0.7
        heatmap_resp = client.get(f"/cases/{case_id}/attention-heatmap")
        heatmap = heatmap_resp.json()
        person_scores = [h for h in heatmap if h["node_id"] == person["id"]]
        assert len(person_scores) >= 1
        assert person_scores[0]["attention_value"] >= 0.7
        assert person_scores[0]["breakdown"]["evidence_gap_factor"] == 0.3


class TestActionQueue:
    def test_contradiction_creates_action(self, client, created_case):
        """Contradiction scan creates review_contradiction actions."""
        case_id = created_case["case_id"]

        # Set up person at two incompatible locations
        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Action Target",
            "role": "suspect", "classification_tag": "case_sensitive",
        }).json()

        loc_a = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id, "location_type": "gps_point",
            "coordinates": "28.6139,77.2090",
            "classification_tag": "case_sensitive",
        }).json()

        loc_b = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id, "location_type": "gps_point",
            "coordinates": "19.0760,72.8777",
            "classification_tag": "case_sensitive",
        }).json()

        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_a["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T10:00:00",
            "valid_to": "2024-01-15T14:00:00",
            "confidence": 0.9, "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_b["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T12:00:00",
            "valid_to": "2024-01-15T16:00:00",
            "confidence": 0.8, "evidence_basis": [],
        })

        # Scan
        client.post(f"/cases/{case_id}/contradictions/scan")

        # Check action queue
        queue_resp = client.get(f"/cases/{case_id}/action-queue")
        assert queue_resp.status_code == 200
        actions = queue_resp.json()
        contradiction_actions = [a for a in actions if a["action_type"] == "review_contradiction"]
        assert len(contradiction_actions) >= 1
        assert contradiction_actions[0]["status"] == "pending"

    def test_dismiss_action_with_reason(self, client, created_case):
        """Dismissing an action requires a reason and writes a memory record."""
        case_id = created_case["case_id"]

        # Create a contradiction action by direct means
        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Dismiss Test",
            "role": "suspect", "classification_tag": "case_sensitive",
        }).json()

        loc_a = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id, "location_type": "gps_point",
            "coordinates": "28.6139,77.2090",
            "classification_tag": "case_sensitive",
        }).json()
        loc_b = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id, "location_type": "gps_point",
            "coordinates": "19.0760,72.8777",
            "classification_tag": "case_sensitive",
        }).json()

        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_a["id"],
            "relationship_type": "AT",
            "valid_from": "2024-02-15T10:00:00",
            "valid_to": "2024-02-15T14:00:00",
            "confidence": 0.9, "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_b["id"],
            "relationship_type": "AT",
            "valid_from": "2024-02-15T12:00:00",
            "valid_to": "2024-02-15T16:00:00",
            "confidence": 0.8, "evidence_basis": [],
        })

        client.post(f"/cases/{case_id}/contradictions/scan")

        # Get an action
        queue = client.get(f"/cases/{case_id}/action-queue").json()
        assert len(queue) >= 1
        action_id = queue[0]["action_id"]

        # Dismiss it
        dismiss_resp = client.post(
            f"/cases/{case_id}/action-queue/{action_id}/status",
            json={
                "new_status": "dismissed",
                "dismissal_reason": "Known travel pattern — suspect flew between cities",
            },
        )
        assert dismiss_resp.status_code == 200
        assert dismiss_resp.json()["status"] == "dismissed"

        # Verify memory record
        memory_resp = client.get(
            f"/cases/{case_id}/memory",
            params={"record_type": "lead_status_changed"},
        )
        records = memory_resp.json()["records"]
        assert any("dismissed" in r.get("description", "").lower() for r in records)

    def test_action_queue_stats(self, client, created_case):
        """Stats endpoint returns counts by type and status."""
        case_id = created_case["case_id"]
        stats_resp = client.get(f"/cases/{case_id}/action-queue/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert "by_type" in stats
        assert "by_status" in stats
        assert "total" in stats
