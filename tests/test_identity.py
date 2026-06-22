"""Tests for the Identity Ontology and entity resolution.

Covers:
- Prompt 8: IdentityFacet deduplication, person merge
"""

import uuid


class TestIdentityFacetResolution:
    def test_create_identity_facet_new(self, client, created_case):
        """Creating a new identity facet should create a Person and link it."""
        case_id = created_case["case_id"]
        response = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "+1-555-0142",
            "classification_tag": "case_sensitive",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["facet_type"] == "phone_number"
        assert data["value"] == "+15550142"  # Normalized
        assert data["is_existing"] is False
        assert len(data["linked_persons"]) == 1

    def test_duplicate_facet_returns_existing(self, client, created_case):
        """Submitting the same phone number again should return the existing facet."""
        case_id = created_case["case_id"]

        # First creation
        resp1 = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "+1 (555) 0199",
            "classification_tag": "case_sensitive",
        })
        assert resp1.status_code == 201
        facet1 = resp1.json()
        assert facet1["is_existing"] is False

        # Second submission with same number but different formatting
        resp2 = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "15550199",  # Same number, different format
            "classification_tag": "case_sensitive",
        })
        assert resp2.status_code == 201
        facet2 = resp2.json()
        assert facet2["is_existing"] is True
        assert facet2["id"] == facet1["id"]

    def test_email_normalization(self, client, created_case):
        """Email addresses should be lowercased."""
        case_id = created_case["case_id"]
        resp = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "email",
            "value": "  John.Doe@Example.COM  ",
            "classification_tag": "case_sensitive",
        })
        assert resp.status_code == 201
        assert resp.json()["value"] == "john.doe@example.com"

    def test_get_person_identifiers(self, client, created_case):
        """Person identifiers endpoint returns facets grouped by type."""
        case_id = created_case["case_id"]

        # Create facet (auto-creates person)
        resp = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "+91-9876543210",
            "classification_tag": "case_sensitive",
        })
        person_id = resp.json()["linked_persons"][0]["id"]

        # Add email to same person
        client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "email",
            "value": "suspect@example.com",
            "person_id": person_id,
            "classification_tag": "case_sensitive",
        })

        # Query identifiers
        id_resp = client.get(f"/cases/{case_id}/graph/person/{person_id}/identifiers")
        assert id_resp.status_code == 200
        grouped = id_resp.json()
        assert "phone_number" in grouped
        assert "email" in grouped


class TestPersonMerge:
    def test_merge_persons(self, client, created_case):
        """Merge two persons: surviving node should have all identifiers."""
        case_id = created_case["case_id"]

        # Create person A with phone
        resp_a = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "+1-555-1111",
            "classification_tag": "case_sensitive",
        })
        person_a_id = resp_a.json()["linked_persons"][0]["id"]

        # Create person B with different phone
        resp_b = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id,
            "facet_type": "phone_number",
            "value": "+1-555-2222",
            "classification_tag": "case_sensitive",
        })
        person_b_id = resp_b.json()["linked_persons"][0]["id"]

        # Merge B into A
        merge_resp = client.post(f"/cases/{case_id}/graph/merge-persons", json={
            "person_id_keep": person_a_id,
            "person_id_merge": person_b_id,
            "reason": "same_individual_confirmed",
        })
        assert merge_resp.status_code == 200
        merge_data = merge_resp.json()
        assert merge_data["surviving_person_id"] == person_a_id
        assert merge_data["merged_person_id"] == person_b_id

        # Verify surviving person has both phone numbers
        id_resp = client.get(f"/cases/{case_id}/graph/person/{person_a_id}/identifiers")
        assert id_resp.status_code == 200
        phones = id_resp.json().get("phone_number", [])
        phone_values = [p["value"] for p in phones]
        assert "+15551111" in phone_values
        assert "+15552222" in phone_values

        # Verify merged person is gone
        get_resp = client.get(f"/cases/{case_id}/graph/person/{person_b_id}")
        assert get_resp.status_code == 404
