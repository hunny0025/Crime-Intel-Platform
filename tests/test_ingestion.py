"""Integration tests for the ingestion adapter framework.

Tests:
- Ingest the synthetic Autopsy fixture end to end
- Confirm artifacts land in the chain correctly
- Confirm Kafka event is published
"""

import os
import sys

# Generate the test fixture before tests run
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fixtures.generate_autopsy_fixture import generate_autopsy_fixture


class TestIngestionAdapter:
    def _get_fixture_bytes(self, tmp_path) -> bytes:
        """Generate and read the Autopsy test fixture."""
        fixture_path = str(tmp_path / "autopsy_test.db")
        generate_autopsy_fixture(fixture_path)
        with open(fixture_path, "rb") as f:
            return f.read()

    def test_ingest_autopsy_sqlite(self, client, created_case, tmp_path):
        """End-to-end: ingest the Autopsy fixture and verify artifacts are created."""
        case_id = created_case["case_id"]
        fixture_bytes = self._get_fixture_bytes(tmp_path)

        response = client.post(
            f"/cases/{case_id}/ingest",
            data={
                "source_format": "autopsy_sqlite",
                "actor": "test_analyst",
            },
            files={"file": ("autopsy_case.db", fixture_bytes, "application/octet-stream")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["case_id"] == case_id
        assert data["source_format"] == "autopsy_sqlite"
        # Should have 5 tsk_files + 3 blackboard_artifacts = 8 records
        assert data["artifacts_created"] == 8
        assert len(data["artifact_ids"]) == 8
        assert data["kafka_event_id"] is not None

    def test_ingested_artifacts_in_chain(self, client, created_case, tmp_path):
        """After ingestion, verify all artifacts are in the evidence chain."""
        case_id = created_case["case_id"]
        fixture_bytes = self._get_fixture_bytes(tmp_path)

        # Ingest
        ingest_resp = client.post(
            f"/cases/{case_id}/ingest",
            data={"source_format": "autopsy_sqlite", "actor": "test_analyst"},
            files={"file": ("autopsy_case.db", fixture_bytes, "application/octet-stream")},
        )
        assert ingest_resp.status_code == 201

        # List evidence
        list_resp = client.get(f"/cases/{case_id}/evidence")
        assert list_resp.status_code == 200
        artifacts = list_resp.json()
        assert len(artifacts) == 8

        # Verify chain integrity
        verify_resp = client.get(f"/cases/{case_id}/chain-of-custody/verify")
        assert verify_resp.status_code == 200
        report = verify_resp.json()
        assert report["valid"] is True
        assert report["artifacts_checked"] == 8

    def test_ingest_unknown_format(self, client, created_case):
        """Attempting to ingest with an unknown format should fail."""
        case_id = created_case["case_id"]
        response = client.post(
            f"/cases/{case_id}/ingest",
            data={"source_format": "nonexistent_format", "actor": "test"},
            files={"file": ("test.bin", b"some data", "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_ingest_case_not_found(self, client, tmp_path):
        """Ingesting to a nonexistent case should 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        fixture_bytes = self._get_fixture_bytes(tmp_path)
        response = client.post(
            f"/cases/{fake_id}/ingest",
            data={"source_format": "autopsy_sqlite", "actor": "test"},
            files={"file": ("autopsy_case.db", fixture_bytes, "application/octet-stream")},
        )
        assert response.status_code == 404
