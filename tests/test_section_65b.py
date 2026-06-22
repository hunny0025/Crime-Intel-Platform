import uuid
import pytest
from app.db.models import Case, EvidenceArtifact, PostgresAgency
from datetime import datetime, timezone

def test_section_65b_endpoints(client, created_case, db_session):
    case_id = created_case["case_id"]

    # 1. Upload an evidence artifact
    response = client.post(
        f"/cases/{case_id}/evidence",
        data={
            "source_tool": "test_tool",
            "collection_timestamp_utc": "2026-06-22T10:00:00Z",
            "original_timezone": "UTC",
            "classification_tag": "evidentiary",
            "acquisition_method": "Logical Extractions"
        },
        files={"file": ("evidence.bin", b"test content", "application/octet-stream")},
    )
    assert response.status_code == 201
    artifact_id = response.json()["artifact_id"]

    # 2. Test draft endpoint
    draft_resp = client.get(
        f"/cases/{case_id}/legal/section-65b/draft",
        params={"artifact_id": artifact_id, "investigator_name": "Detective Smith"}
    )
    assert draft_resp.status_code == 200
    draft_data = draft_resp.json()
    assert draft_data["case_id"] == case_id
    assert draft_data["artifact_id"] == artifact_id
    assert draft_data["investigator_name"] == "Detective Smith"
    assert "BSA" in draft_data["statute"] or "Section" in draft_data["statute"]
    assert draft_data["device_info"]["acquisition_method"] == "Logical Extractions"

    # 3. Test PDF endpoint
    pdf_resp = client.get(
        f"/cases/{case_id}/legal/section-65b/pdf",
        params={"artifact_id": artifact_id, "investigator_name": "Detective Smith"}
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 0

    # 4. Test submit/sign endpoint
    submit_resp = client.post(
        f"/cases/{case_id}/legal/section-65b/submit",
        json={
            "artifact_id": artifact_id,
            "investigator_id": "inv_smith_123",
            "signature_metadata": "SHA256withRSA signature details",
            "date": "2026-06-22T22:15:00Z",
            "hash": "test_signature_hash_value"
        }
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "certified"

    # 5. Verify the memory diary has a record of it
    diary_resp = client.get(f"/cases/{case_id}/diary")
    assert diary_resp.status_code == 200
    diary_data = diary_resp.json()
    found = False
    for rec in diary_data["diary"]:
        if "Section 65B" in rec["description"] or "verified for artifact" in rec["description"]:
            found = True
            assert rec["actor"] == "inv_smith_123"
            break
    assert found is True


def test_autonomy_audit_agency_filtering(client, created_case, db_session):
    case_id = created_case["case_id"]

    # Retrieve Case and set agency_id to test Postgres filtering
    case = db_session.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    assert case is not None

    # Create an agency
    agency_id = uuid.uuid4()
    agency = PostgresAgency(agency_id=agency_id, agency_name="Cyber Crime Unit A")
    db_session.add(agency)
    case.agency_id = agency_id
    db_session.commit()

    # Run the pipeline to generate autonomy logs
    run_pipeline_resp = client.post(f"/cases/{case_id}/aire/run-pipeline")
    assert run_pipeline_resp.status_code == 200

    # Check autonomy-audit with case's agency
    audit_resp = client.get(f"/cases/{case_id}/aire/autonomy-audit")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert len(audit_data) > 0
    # Every record should carry the agency_id
    for rec in audit_data:
        assert rec["agency_id"] == str(agency_id)
