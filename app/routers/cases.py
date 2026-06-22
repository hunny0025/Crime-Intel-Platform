"""Case management endpoints — CRUD for cases and entity links."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case, CaseEntity, CaseStatus
from app.schemas import (
    CreateCaseRequest,
    CaseResponse,
    CreateEntityRequest,
    EntityResponse,
)
from pydantic import BaseModel

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=201)
def create_case(req: CreateCaseRequest, db: Session = Depends(get_db)):
    """Create a new case."""
    case = Case(
        case_id=uuid.uuid4(),
        case_type=req.case_type,
        status=req.status,
        classification_tag=req.classification_tag,
        created_by=req.created_by,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # Automatically trigger AIRE Step 0 (cross-case matching)
    try:
        from app.reasoning.aire import run_pipeline
        run_pipeline(str(case.case_id), "case.created", {"event_type": "case.created"}, db)
    except Exception as e:
        # Prevent AIRE pipeline failures from blocking case creation
        import logging
        logging.getLogger(__name__).warning("Failed to trigger AIRE step 0 on case creation: %s", e)

    return case


@router.get("", response_model=list[CaseResponse])
def list_cases(db: Session = Depends(get_db)):
    """List all cases."""
    return db.query(Case).order_by(Case.created_at.desc()).all()


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retrieve case metadata by ID."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}/entities", response_model=list[EntityResponse])
def list_entities(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """List all entities linked to a case."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(CaseEntity).filter(CaseEntity.case_id == case_id).all()


@router.post("/{case_id}/entities", response_model=EntityResponse, status_code=201)
def link_entity(case_id: uuid.UUID, req: CreateEntityRequest, db: Session = Depends(get_db)):
    """Link an entity to a case."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    entity = CaseEntity(
        id=uuid.uuid4(),
        case_id=case_id,
        entity_id=req.entity_id,
        entity_type=req.entity_type,
        role=req.role,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


class UpdateCaseStatusRequest(BaseModel):
    status: CaseStatus


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case_status(
    case_id: uuid.UUID,
    req: UpdateCaseStatusRequest,
    db: Session = Depends(get_db),
):
    """Update case status and trigger Kafka case.closed event if transitioning to closed."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    new_status = req.status
    case.status = new_status
    db.commit()
    db.refresh(case)

    # If the new status is a closed state, publish case.closed event to Kafka
    status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
    if status_val.startswith("closed"):
        try:
            from app.events.producer import get_kafka_producer
            producer = get_kafka_producer()
            producer.publish(
                topic="cases",
                case_id=case_id,
                event_type="case.closed",
                payload={
                    "case_id": str(case_id),
                    "status": status_val,
                },
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to publish case.closed event to Kafka: %s", e)

    return case
