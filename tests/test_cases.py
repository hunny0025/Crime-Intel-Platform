"""Integration tests for Case Management endpoints."""

import uuid


class TestCreateCase:
    def test_create_case_success(self, client, sample_case_data):
        response = client.post("/cases", json=sample_case_data)
        assert response.status_code == 201
        data = response.json()
        assert data["case_type"] == "homicide"
        assert data["status"] == "open"
        assert data["classification_tag"] == "case_sensitive"
        assert data["created_by"] == "detective_smith"
        assert "case_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_case_default_status(self, client):
        response = client.post("/cases", json={
            "case_type": "fraud",
            "classification_tag": "public_osint",
            "created_by": "analyst_jones",
        })
        assert response.status_code == 201
        assert response.json()["status"] == "open"


class TestGetCase:
    def test_get_case_success(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.get(f"/cases/{case_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["case_id"] == case_id
        assert data["case_type"] == "homicide"

    def test_get_case_not_found(self, client):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/cases/{fake_id}")
        assert response.status_code == 404


class TestCaseEntities:
    def test_link_entity(self, client, created_case):
        case_id = created_case["case_id"]
        entity_data = {
            "entity_id": str(uuid.uuid4()),
            "entity_type": "person",
            "role": "suspect",
        }
        response = client.post(f"/cases/{case_id}/entities", json=entity_data)
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "person"
        assert data["role"] == "suspect"
        assert data["case_id"] == case_id

    def test_list_entities(self, client, created_case):
        case_id = created_case["case_id"]

        # Link two entities
        for role in ["suspect", "victim"]:
            client.post(f"/cases/{case_id}/entities", json={
                "entity_id": str(uuid.uuid4()),
                "entity_type": "person",
                "role": role,
            })

        response = client.get(f"/cases/{case_id}/entities")
        assert response.status_code == 200
        entities = response.json()
        assert len(entities) == 2
        roles = {e["role"] for e in entities}
        assert roles == {"suspect", "victim"}

    def test_list_entities_empty(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.get(f"/cases/{case_id}/entities")
        assert response.status_code == 200
        assert response.json() == []

    def test_link_entity_case_not_found(self, client):
        fake_id = str(uuid.uuid4())
        response = client.post(f"/cases/{fake_id}/entities", json={
            "entity_id": str(uuid.uuid4()),
            "entity_type": "device",
            "role": "evidence_source",
        })
        assert response.status_code == 404
