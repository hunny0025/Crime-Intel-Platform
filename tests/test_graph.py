"""Tests for Neo4j schema constraints and graph entity CRUD.

Covers:
- Prompt 6: Constraint idempotency
- Prompt 7: Person/Device CRUD, OWNS relationship, neighbors query
"""

import uuid
import pytest


class TestSchemaConstraints:
    def test_constraints_applied_idempotently(self, client):
        """Apply constraints twice — should succeed both times without error."""
        from app.graph.driver import get_neo4j_client
        from app.graph.constraints import apply_constraints

        try:
            neo4j = get_neo4j_client()
        except Exception:
            pytest.skip("Neo4j not available")

        # First application
        result1 = apply_constraints(neo4j)
        assert len(result1) > 0

        # Second application — should be idempotent
        result2 = apply_constraints(neo4j)
        assert len(result2) == len(result1)

    def test_constraints_exist(self, client):
        """Verify uniqueness constraints exist for all node labels."""
        from app.graph.driver import get_neo4j_client
        from app.graph.constraints import (
            get_existing_constraints,
            ALL_NODE_LABELS,
            apply_constraints,
        )

        try:
            neo4j = get_neo4j_client()
        except Exception:
            pytest.skip("Neo4j not available")

        apply_constraints(neo4j)
        constraints = get_existing_constraints(neo4j)
        constraint_names = [c.get("name", "") for c in constraints]

        for label in ALL_NODE_LABELS:
            expected = f"constraint_{label.lower()}_id_unique"
            assert expected in constraint_names, f"Missing constraint: {expected}"


class TestGraphEntityCRUD:
    def test_create_person(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id,
            "display_name": "John Doe",
            "role": "suspect",
            "classification_tag": "case_sensitive",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["display_name"] == "John Doe"
        assert data["role"] == "suspect"

    def test_get_person(self, client, created_case):
        case_id = created_case["case_id"]
        # Create
        create_resp = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id,
            "display_name": "Jane Smith",
            "role": "victim",
            "classification_tag": "case_sensitive",
        })
        person_id = create_resp.json()["id"]

        # Get
        get_resp = client.get(f"/cases/{case_id}/graph/person/{person_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["display_name"] == "Jane Smith"

    def test_create_device(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/graph/device", json={
            "case_id": case_id,
            "device_type": "mobile_phone",
            "identifiers": ["IMEI:123456789012345", "SN:ABC123"],
            "classification_tag": "evidentiary",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["device_type"] == "mobile_phone"
        assert len(data["identifiers"]) == 2

    def test_create_relationship_owns(self, client, created_case):
        """Create Person → OWNS → Device with real artifact evidence_basis."""
        case_id = created_case["case_id"]

        # Create a person
        person_resp = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id,
            "display_name": "Suspect Alpha",
            "role": "suspect",
            "classification_tag": "case_sensitive",
        })
        person_id = person_resp.json()["id"]

        # Create a device
        device_resp = client.post(f"/cases/{case_id}/graph/device", json={
            "case_id": case_id,
            "device_type": "laptop",
            "identifiers": ["SN:XYZ789"],
            "classification_tag": "evidentiary",
        })
        device_id = device_resp.json()["id"]

        # Upload an evidence artifact to use as evidence_basis
        evidence_resp = client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": "manual_upload",
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("device_report.pdf", b"device ownership report", "application/octet-stream")},
        )
        artifact_id = evidence_resp.json()["artifact_id"]

        # Create OWNS relationship with evidence_basis
        rel_resp = client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person_id,
            "to_node_id": device_id,
            "relationship_type": "OWNS",
            "confidence": 0.95,
            "evidence_basis": [artifact_id],
        })
        assert rel_resp.status_code == 201
        rel_data = rel_resp.json()
        assert rel_data["relationship_type"] == "OWNS"

    def test_relationship_rejects_invalid_artifact(self, client, created_case):
        """Creating a relationship with a nonexistent artifact_id should fail."""
        case_id = created_case["case_id"]

        # Create two nodes
        p1 = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "A", "role": "unknown",
            "classification_tag": "case_sensitive",
        }).json()
        p2 = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "B", "role": "unknown",
            "classification_tag": "case_sensitive",
        }).json()

        # Try with a fake artifact_id
        rel_resp = client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": p1["id"],
            "to_node_id": p2["id"],
            "relationship_type": "COMMUNICATED_WITH",
            "evidence_basis": [str(uuid.uuid4())],
        })
        assert rel_resp.status_code == 400
        assert "Invalid artifact_ids" in rel_resp.json()["detail"]

    def test_neighbors_query(self, client, created_case):
        """Create a Person-OWNS->Device and verify neighbors query."""
        case_id = created_case["case_id"]

        person_resp = client.post(f"/cases/{case_id}/graph/person", json={
            "case_id": case_id, "display_name": "Owner",
            "role": "suspect", "classification_tag": "case_sensitive",
        })
        person_id = person_resp.json()["id"]

        device_resp = client.post(f"/cases/{case_id}/graph/device", json={
            "case_id": case_id, "device_type": "phone",
            "identifiers": ["IMEI:999"], "classification_tag": "evidentiary",
        })
        device_id = device_resp.json()["id"]

        # Create relationship (no evidence_basis for simplicity)
        client.post(f"/cases/{case_id}/graph/relationships", json={
            "from_node_id": person_id,
            "to_node_id": device_id,
            "relationship_type": "OWNS",
            "evidence_basis": [],
        })

        # Query neighbors
        neighbors_resp = client.get(f"/cases/{case_id}/graph/entity/{person_id}/neighbors")
        assert neighbors_resp.status_code == 200
        neighbors = neighbors_resp.json()
        assert len(neighbors) >= 1
        device_ids = [n["node"]["id"] for n in neighbors if n["node"].get("device_type")]
        assert device_id in device_ids
