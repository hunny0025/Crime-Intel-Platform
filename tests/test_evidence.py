"""Integration tests for the Immutable Evidence Store.

Tests:
1. Ingest three artifacts in sequence, verify chain passes
2. Corrupt a record's content_hash, confirm verify detects the break
"""

import io
import uuid
from datetime import datetime


class TestEvidenceUpload:
    def test_upload_single_artifact(self, client, created_case):
        case_id = created_case["case_id"]
        response = client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": "manual_upload",
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("evidence.bin", b"test evidence content", "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["case_id"] == case_id
        assert data["source_tool"] == "manual_upload"
        assert data["content_hash"] is not None
        assert data["record_hash"] is not None
        assert data["previous_record_hash"] is None  # First in chain

    def test_upload_case_not_found(self, client):
        fake_id = str(uuid.uuid4())
        response = client.post(
            f"/cases/{fake_id}/evidence",
            data={
                "source_tool": "manual_upload",
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("test.bin", b"data", "application/octet-stream")},
        )
        assert response.status_code == 404


class TestEvidenceChain:
    def _upload_artifact(self, client, case_id, content, tool="manual_upload"):
        return client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": tool,
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("evidence.bin", content, "application/octet-stream")},
        )

    def test_three_artifacts_chain_valid(self, client, created_case):
        """Ingest three artifacts in sequence and verify the chain passes."""
        case_id = created_case["case_id"]

        # Upload three artifacts
        r1 = self._upload_artifact(client, case_id, b"evidence file 1")
        assert r1.status_code == 201
        a1 = r1.json()
        assert a1["previous_record_hash"] is None

        r2 = self._upload_artifact(client, case_id, b"evidence file 2")
        assert r2.status_code == 201
        a2 = r2.json()
        assert a2["previous_record_hash"] == a1["record_hash"]

        r3 = self._upload_artifact(client, case_id, b"evidence file 3")
        assert r3.status_code == 201
        a3 = r3.json()
        assert a3["previous_record_hash"] == a2["record_hash"]

        # Verify chain
        verify_resp = client.get(f"/cases/{case_id}/chain-of-custody/verify")
        assert verify_resp.status_code == 200
        report = verify_resp.json()
        assert report["valid"] is True
        assert report["artifacts_checked"] == 3
        assert report["breaks"] == []

    def test_chain_detects_corruption(self, client, created_case, db_session):
        """Corrupt a record's content_hash and confirm verification detects the break."""
        case_id = created_case["case_id"]

        # Upload three artifacts
        r1 = self._upload_artifact(client, case_id, b"secure data 1")
        r2 = self._upload_artifact(client, case_id, b"secure data 2")
        r3 = self._upload_artifact(client, case_id, b"secure data 3")
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r3.status_code == 201

        a2_id = r2.json()["artifact_id"]

        # Directly corrupt the second artifact's content_hash in the database
        from app.db.models import EvidenceArtifact
        artifact = db_session.query(EvidenceArtifact).filter(
            EvidenceArtifact.artifact_id == uuid.UUID(a2_id)
        ).first()
        assert artifact is not None
        artifact.content_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        db_session.commit()

        # Verify chain — should detect the break
        verify_resp = client.get(f"/cases/{case_id}/chain-of-custody/verify")
        assert verify_resp.status_code == 200
        report = verify_resp.json()
        assert report["valid"] is False
        assert len(report["breaks"]) > 0

        # Confirm the break is at the corrupted artifact
        break_ids = [b["artifact_id"] for b in report["breaks"]]
        assert a2_id in break_ids


class TestEvidenceRetrieval:
    def test_get_evidence_metadata(self, client, created_case):
        case_id = created_case["case_id"]

        # Upload an artifact
        upload_resp = client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": "autopsy",
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "America/New_York",
                "classification_tag": "evidentiary",
            },
            files={"file": ("report.pdf", b"pdf content here", "application/pdf")},
        )
        assert upload_resp.status_code == 201
        artifact_id = upload_resp.json()["artifact_id"]

        # Retrieve it
        get_resp = client.get(f"/evidence/{artifact_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["artifact_id"] == artifact_id
        assert data["source_tool"] == "autopsy"
        assert data["presigned_url"] is not None
        # Chain of custody should have 'created' and 'read' entries
        log = data["chain_of_custody_log"]
        actions = [entry["action"] for entry in log]
        assert "created" in actions
        assert "read" in actions

    def test_list_evidence_in_order(self, client, created_case):
        case_id = created_case["case_id"]

        # Upload two artifacts
        client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": "tool_a",
                "collection_timestamp_utc": "2024-01-15T10:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("a.bin", b"first", "application/octet-stream")},
        )
        client.post(
            f"/cases/{case_id}/evidence",
            data={
                "source_tool": "tool_b",
                "collection_timestamp_utc": "2024-01-15T11:00:00Z",
                "original_timezone": "UTC",
                "classification_tag": "evidentiary",
            },
            files={"file": ("b.bin", b"second", "application/octet-stream")},
        )

        # List
        list_resp = client.get(f"/cases/{case_id}/evidence")
        assert list_resp.status_code == 200
        artifacts = list_resp.json()
        assert len(artifacts) == 2
        assert artifacts[0]["source_tool"] == "tool_a"
        assert artifacts[1]["source_tool"] == "tool_b"
        # Second artifact should reference first
        assert artifacts[1]["previous_record_hash"] == artifacts[0]["record_hash"]

    def test_get_evidence_not_found(self, client):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/evidence/{fake_id}")
        assert response.status_code == 404
