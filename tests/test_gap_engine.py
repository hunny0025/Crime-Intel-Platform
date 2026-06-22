"""Tests for the Evidence Gap Engine.

Covers Prompt 14: communication silence gap + single-source identifier gap.
"""

import uuid


class TestCommunicationSilenceGap:
    def test_detects_silence_with_significant_event(self, client, created_case):
        """
        Regular communication pair with a large gap overlapping a significant event
        → EvidenceGap created.
        """
        case_id = created_case["case_id"]

        # Create two persons via identity facets
        resp_a = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-3001", "classification_tag": "case_sensitive",
        })
        person_a_id = resp_a.json()["linked_persons"][0]["id"]

        resp_b = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-3002", "classification_tag": "case_sensitive",
        })
        person_b_id = resp_b.json()["linked_persons"][0]["id"]

        # Create 4 regular communications (every ~1 day)
        timestamps = [
            ("2024-01-10T10:00:00", "2024-01-10T10:05:00"),
            ("2024-01-11T10:00:00", "2024-01-11T10:05:00"),
            ("2024-01-12T10:00:00", "2024-01-12T10:05:00"),
            # GAP: Jan 12 to Jan 25 (13 days, 13x median of ~1day)
            ("2024-01-25T10:00:00", "2024-01-25T10:05:00"),
        ]
        for vf, vt in timestamps:
            client.post(f"/cases/{case_id}/graph/relationships", json={
                "from_node_id": person_a_id,
                "to_node_id": person_b_id,
                "relationship_type": "COMMUNICATED_WITH",
                "valid_from": vf, "valid_to": vt,
                "confidence": 1.0, "evidence_basis": [],
            })

        # Create a significant event during the gap
        client.post(f"/cases/{case_id}/graph/event", json={
            "case_id": case_id,
            "event_type": "bank_transaction",
            "valid_from": "2024-01-18T10:00:00",
            "valid_to": "2024-01-18T11:00:00",
            "classification_tag": "case_sensitive",
        })

        # Run gap scan
        scan_resp = client.post(f"/cases/{case_id}/evidence-gaps/scan")
        assert scan_resp.status_code == 200
        data = scan_resp.json()
        assert data["gaps_found"] >= 1

    def test_no_gap_without_significant_event(self, client, created_case):
        """Large gap but NO overlapping significant event → no gap created."""
        case_id = created_case["case_id"]

        resp_a = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-4001", "classification_tag": "case_sensitive",
        })
        person_a_id = resp_a.json()["linked_persons"][0]["id"]

        resp_b = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-4002", "classification_tag": "case_sensitive",
        })
        person_b_id = resp_b.json()["linked_persons"][0]["id"]

        # Regular communications with a gap but no significant events
        for day in [10, 11, 12, 25]:
            client.post(f"/cases/{case_id}/graph/relationships", json={
                "from_node_id": person_a_id,
                "to_node_id": person_b_id,
                "relationship_type": "COMMUNICATED_WITH",
                "valid_from": f"2024-02-{day:02d}T10:00:00",
                "valid_to": f"2024-02-{day:02d}T10:05:00",
                "confidence": 1.0, "evidence_basis": [],
            })

        # No significant events — only communication/file_artifact types exist
        scan_resp = client.post(f"/cases/{case_id}/evidence-gaps/scan")
        data = scan_resp.json()
        # Communication silence rule should not fire without significant events
        comm_gaps = [g for g in data.get("gaps", []) if "communicate" in g.get("description", "").lower()]
        assert len(comm_gaps) == 0


class TestSingleSourceIdentifierGap:
    def test_detects_identifier_imbalance(self, client, created_case):
        """Person with 4 phone identifiers and 1 email → gap detected."""
        case_id = created_case["case_id"]

        # Create person with first phone
        resp = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-5001", "classification_tag": "case_sensitive",
        })
        person_id = resp.json()["linked_persons"][0]["id"]

        # Add more phones
        for phone in ["+1-555-5002", "+1-555-5003", "+1-555-5004"]:
            client.post(f"/cases/{case_id}/graph/identity-facet", json={
                "case_id": case_id, "facet_type": "phone_number",
                "value": phone, "person_id": person_id,
                "classification_tag": "case_sensitive",
            })

        # Add just 1 email
        client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "email",
            "value": "suspect@example.com", "person_id": person_id,
            "classification_tag": "case_sensitive",
        })

        # Run scan
        scan_resp = client.post(f"/cases/{case_id}/evidence-gaps/scan")
        data = scan_resp.json()
        # Should detect the imbalance
        id_gaps = [g for g in data.get("gaps", []) if "identifier" in g.get("description", "").lower()]
        assert len(id_gaps) >= 1

    def test_no_gap_for_balanced_identifiers(self, client, created_case):
        """Person with balanced phone/email counts → no gap."""
        case_id = created_case["case_id"]

        resp = client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-6001", "classification_tag": "case_sensitive",
        })
        person_id = resp.json()["linked_persons"][0]["id"]

        # Add 1 more phone + 2 emails (balanced)
        client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "phone_number",
            "value": "+1-555-6002", "person_id": person_id,
            "classification_tag": "case_sensitive",
        })
        client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "email",
            "value": "a@example.com", "person_id": person_id,
            "classification_tag": "case_sensitive",
        })
        client.post(f"/cases/{case_id}/graph/identity-facet", json={
            "case_id": case_id, "facet_type": "email",
            "value": "b@example.com", "person_id": person_id,
            "classification_tag": "case_sensitive",
        })

        scan_resp = client.post(f"/cases/{case_id}/evidence-gaps/scan")
        data = scan_resp.json()
        id_gaps = [g for g in data.get("gaps", []) if "identifier" in g.get("description", "").lower()]
        assert len(id_gaps) == 0


class TestGapResolution:
    def test_resolve_gap(self, client, created_case):
        """Resolving a gap updates status and writes memory record."""
        case_id = created_case["case_id"]

        # Create an evidence gap directly
        gap_resp = client.post(f"/cases/{case_id}/evidence-gaps", json={
            "case_id": case_id,
            "description": "Test gap for resolution",
            "expected_value": "medium",
            "urgency": "medium",
            "classification_tag": "case_sensitive",
        })
        gap_id = gap_resp.json()["id"]

        # Resolve it
        resolve_resp = client.post(
            f"/cases/{case_id}/evidence-gaps/{gap_id}/resolve",
            json={"resolution_note": "Bank records obtained via production order"},
        )
        assert resolve_resp.status_code == 200
        assert resolve_resp.json()["status"] == "resolved"

        # Check memory record was created
        memory_resp = client.get(
            f"/cases/{case_id}/memory",
            params={"record_type": "lead_status_changed"},
        )
        records = memory_resp.json()["records"]
        assert any(gap_id in (r.get("graph_refs") or []) for r in records)
