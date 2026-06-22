"""Phase 10 — National Scale Deployment API endpoints.

Agency management, deconfliction, national intelligence, platform ops.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db

from app.national.agency import (
    create_agency, list_agencies, provision_investigator,
    validate_agency_access,
)
from app.national.deconfliction import (
    index_identity_facet, get_deconfliction_alerts,
    acknowledge_alert, compute_deconfliction_hash,
)
from app.national.intelligence import (
    get_national_dashboard, detect_threat_signals,
    get_threat_signals, create_threat_advisory,
)
from app.national.operations import (
    get_platform_health, get_archival_candidates, archive_case,
)

router = APIRouter(tags=["national-scale"])


# ── Prompt 51: Agency Management ─────────────────────────────────────────

class CreateAgencyRequest(BaseModel):
    agency_name: str
    agency_type: str
    jurisdiction: str
    contact_officer: str


class ProvisionInvestigatorRequest(BaseModel):
    investigator_name: str
    role: str = "investigator"


@router.post("/admin/agencies")
def create_agency_endpoint(body: CreateAgencyRequest):
    return create_agency(body.agency_name, body.agency_type,
                         body.jurisdiction, body.contact_officer)


@router.get("/admin/agencies")
def list_agencies_endpoint():
    return list_agencies()


@router.post("/admin/agencies/{agency_id}/investigators")
def provision_investigator_endpoint(agency_id: str, body: ProvisionInvestigatorRequest):
    return provision_investigator(agency_id, body.investigator_name, body.role)


# ── Prompt 52: Deconfliction ────────────────────────────────────────────

class IndexFacetRequest(BaseModel):
    agency_id: str
    case_id: str
    facet_id: str
    facet_value: str
    facet_type: str


@router.post("/national/deconfliction/index")
def index_facet(body: IndexFacetRequest):
    return index_identity_facet(body.agency_id, body.case_id, body.facet_id,
                                body.facet_value, body.facet_type)


@router.get("/cases/{case_id}/national/deconfliction-alerts")
def decon_alerts(case_id: str, agency_id: str = ""):
    return get_deconfliction_alerts(case_id, agency_id)


class AcknowledgeRequest(BaseModel):
    contacted_other_agency: bool = False


@router.post("/national/deconfliction-alerts/{alert_id}/acknowledge")
def ack_alert(alert_id: str, body: AcknowledgeRequest = AcknowledgeRequest()):
    return acknowledge_alert(alert_id, body.contacted_other_agency)


# ── Prompt 53: National Intelligence ─────────────────────────────────────

@router.get("/national/intelligence-dashboard")
def intelligence_dashboard():
    return get_national_dashboard()


@router.post("/national/threat-signals/detect")
def detect_signals():
    return detect_threat_signals()


@router.get("/national/threat-signals")
def threat_signals():
    return get_threat_signals()


class AdvisoryRequest(BaseModel):
    advisory_text: str
    recommended_steps: list[str]
    target_agencies: Optional[list[str]] = None


@router.post("/national/threat-signals/{signal_id}/advisory")
def create_advisory(signal_id: str, body: AdvisoryRequest):
    return create_threat_advisory(signal_id, body.advisory_text,
                                  body.recommended_steps, body.target_agencies)


# ── Prompt 54: Platform Operations ──────────────────────────────────────

@router.get("/admin/platform-health")
def platform_health():
    return get_platform_health()


@router.get("/admin/archival-candidates")
def archival_candidates():
    return get_archival_candidates()


@router.post("/admin/archive/{case_id}")
def archive(case_id: str):
    return archive_case(case_id)
