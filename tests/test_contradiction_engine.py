"""Tests for the Contradiction Engine.

Covers Prompt 13: temporal/spatial co-location contradictions.
"""

import uuid


class TestContradictionEngine:
    def _setup_person_at_locations(self, client, case_id):
        """Create a Person with AT relationships to two locations."""
        # Create person
        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id,
            "display_name": "Suspect Alpha",
            "role": "suspect",
            "classification_tag": "case_sensitive",
        }).json()

        # Create two incompatible locations (>5km apart)
        loc_a = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id,
            "location_type": "gps_point",
            "coordinates": "28.6139,77.2090",  # Delhi
            "address": "New Delhi, India",
            "classification_tag": "case_sensitive",
        }).json()

        loc_b = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id,
            "location_type": "gps_point",
            "coordinates": "19.0760,72.8777",  # Mumbai
            "address": "Mumbai, India",
            "classification_tag": "case_sensitive",
        }).json()

        return person, loc_a, loc_b

    def test_detects_temporal_spatial_contradiction(self, client, created_case):
        """Overlapping time windows at incompatible locations → contradiction."""
        case_id = created_case["case_id"]
        person, loc_a, loc_b = self._setup_person_at_locations(client, case_id)

        # Create AT relationships with overlapping time windows
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"],
            "to_node_id": loc_a["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T10:00:00",
            "valid_to": "2024-01-15T14:00:00",
            "confidence": 0.9,
            "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"],
            "to_node_id": loc_b["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T12:00:00",  # 2h overlap
            "valid_to": "2024-01-15T16:00:00",
            "confidence": 0.8,
            "evidence_basis": [],
        })

        # Run contradiction scan
        scan_resp = client.post(f"/cases/{case_id}/contradictions/scan")
        assert scan_resp.status_code == 200
        data = scan_resp.json()
        assert data["contradictions_found"] >= 1

        # Check contradiction details
        detail_resp = client.get(f"/cases/{case_id}/contradictions/detail")
        assert detail_resp.status_code == 200
        details = detail_resp.json()
        assert len(details) >= 1
        # Should mention the person and locations
        first = details[0]
        assert "Delhi" in first["description"] or "Mumbai" in first["description"]
        assert first["contradiction_type"] == "temporal"

    def test_no_contradiction_for_same_location(self, client, created_case):
        """Two AT relationships to the SAME location should NOT produce contradiction."""
        case_id = created_case["case_id"]
        person = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Person B",
            "role": "witness", "classification_tag": "case_sensitive",
        }).json()

        loc = client.post(f"/cases/{case_id}/graph/location", json={
            "case_id": case_id, "location_type": "address",
            "address": "123 Main St", "classification_tag": "case_sensitive",
        }).json()

        # Two AT rels to the same location
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T10:00:00",
            "valid_to": "2024-01-15T12:00:00",
            "confidence": 1.0, "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T11:00:00",
            "valid_to": "2024-01-15T13:00:00",
            "confidence": 1.0, "evidence_basis": [],
        })

        scan_resp = client.post(f"/cases/{case_id}/contradictions/scan")
        assert scan_resp.json()["contradictions_found"] == 0

    def test_no_contradiction_for_non_overlapping_times(self, client, created_case):
        """Incompatible locations but non-overlapping times → no contradiction."""
        case_id = created_case["case_id"]
        person, loc_a, loc_b = self._setup_person_at_locations(client, case_id)

        # Non-overlapping time windows
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_a["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T08:00:00",
            "valid_to": "2024-01-15T10:00:00",
            "confidence": 0.9, "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person["id"], "to_node_id": loc_b["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-16T08:00:00",  # Next day
            "valid_to": "2024-01-16T10:00:00",
            "confidence": 0.9, "evidence_basis": [],
        })

        scan_resp = client.post(f"/cases/{case_id}/contradictions/scan")
        assert scan_resp.json()["contradictions_found"] == 0

    def test_severity_ordering(self, client, created_case):
        """Longer overlap + higher confidence = higher severity."""
        case_id = created_case["case_id"]

        # High severity case: 4h overlap, high confidence
        person1, loc_a1, loc_b1 = self._setup_person_at_locations(client, case_id)
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person1["id"], "to_node_id": loc_a1["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T08:00:00",
            "valid_to": "2024-01-15T18:00:00",
            "confidence": 0.95, "evidence_basis": [],
        })
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person1["id"], "to_node_id": loc_b1["id"],
            "relationship_type": "AT",
            "valid_from": "2024-01-15T10:00:00",
            "valid_to": "2024-01-15T20:00:00",
            "confidence": 0.90, "evidence_basis": [],
        })

        scan_resp = client.post(f"/cases/{case_id}/contradictions/scan")
        contradictions = scan_resp.json()["contradictions"]
        assert any(c.get("severity") == "high" for c in contradictions)
