"""Graph entity CRUD endpoints — Person, Device, Account, Location, Organization, Event.

Also handles relationship creation with evidence_basis validation and neighbor queries.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.graph import crud
from app.graph.relationships import ALL_RELATIONSHIP_TYPES, EVIDENCE_BACKED_RELATIONSHIP_TYPES
from app.graph.schemas import (
    PersonCreate, PersonResponse,
    DeviceCreate, DeviceResponse,
    AccountCreate, AccountResponse,
    LocationCreate, LocationResponse,
    OrganizationCreate, OrganizationResponse,
    EventCreate, EventResponse,
    CreateRelationshipRequest, RelationshipResponse,
    GraphSummary,
)

router = APIRouter(prefix="/cases/{case_id}/graph", tags=["graph"])

# ── Helper ───────────────────────────────────────────────────────────────

def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


# ── Person ───────────────────────────────────────────────────────────────

@router.post("/person", status_code=201)
def create_person(case_id: str, body: PersonCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Person", body.model_dump())

@router.get("/person/{node_id}")
def get_person(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Person", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Person not found")
    return node


# ── Device ───────────────────────────────────────────────────────────────

@router.post("/device", status_code=201)
def create_device(case_id: str, body: DeviceCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Device", body.model_dump())

@router.get("/device/{node_id}")
def get_device(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Device", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Device not found")
    return node


# ── Account ──────────────────────────────────────────────────────────────

@router.post("/account", status_code=201)
def create_account(case_id: str, body: AccountCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Account", body.model_dump())

@router.get("/account/{node_id}")
def get_account(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Account", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Account not found")
    return node


# ── Location ─────────────────────────────────────────────────────────────

@router.post("/location", status_code=201)
def create_location(case_id: str, body: LocationCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Location", body.model_dump())

@router.get("/location/{node_id}")
def get_location(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Location", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Location not found")
    return node


# ── Organization ─────────────────────────────────────────────────────────

@router.post("/organization", status_code=201)
def create_organization(case_id: str, body: OrganizationCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Organization", body.model_dump())

@router.get("/organization/{node_id}")
def get_organization(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Organization", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Organization not found")
    return node


# ── Event ────────────────────────────────────────────────────────────────

@router.post("/event", status_code=201)
def create_event(case_id: str, body: EventCreate, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    body.case_id = case_id
    return crud.create_node("Event", body.model_dump())

@router.get("/event/{node_id}")
def get_event(case_id: str, node_id: str, db: Session = Depends(get_db)):
    _validate_case(case_id, db)
    node = crud.get_node("Event", node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Event not found")
    return node


# ── Relationships ────────────────────────────────────────────────────────

@router.post("/relationships", status_code=201)
def create_relationship(
    case_id: str,
    body: CreateRelationshipRequest,
    db: Session = Depends(get_db),
):
    """Create a relationship between two nodes. Validates evidence_basis artifact_ids."""
    _validate_case(case_id, db)

    if body.relationship_type not in ALL_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown relationship type: {body.relationship_type}. "
                   f"Valid types: {sorted(ALL_RELATIONSHIP_TYPES)}",
        )

    # Validate evidence_basis for evidence-backed relationships
    if body.relationship_type in EVIDENCE_BACKED_RELATIONSHIP_TYPES and body.evidence_basis:
        invalid = crud.validate_evidence_basis(db, body.evidence_basis)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid artifact_ids in evidence_basis: {invalid}",
            )

    props = {}
    if body.valid_from:
        props["valid_from"] = body.valid_from.isoformat()
    if body.valid_to:
        props["valid_to"] = body.valid_to.isoformat()
    if body.confidence is not None:
        props["confidence"] = body.confidence
    if body.evidence_basis:
        props["evidence_basis"] = body.evidence_basis

    result = crud.create_relationship(
        body.from_node_id, body.to_node_id, body.relationship_type, props
    )
    if not result:
        raise HTTPException(status_code=404, detail="One or both nodes not found")
    return result


# ── Neighbors ────────────────────────────────────────────────────────────

@router.get("/entity/{node_id}/neighbors")
def get_neighbors(case_id: str, node_id: str, db: Session = Depends(get_db)):
    """Return all directly connected nodes and relationships for a node."""
    _validate_case(case_id, db)
    return crud.get_neighbors(case_id, node_id)


# ── Summary ──────────────────────────────────────────────────────────────

@router.get("/summary", response_model=GraphSummary)
def get_summary(case_id: str, db: Session = Depends(get_db)):
    """Return counts of nodes by label and relationships by type for the case."""
    _validate_case(case_id, db)
    return crud.get_graph_summary(case_id)
