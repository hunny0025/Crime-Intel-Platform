"""Identity resolution endpoints — IdentityFacet, person identifiers, person merge."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.graph.identity import resolve_identity_facet, get_person_identifiers, merge_persons
from app.graph.schemas import (
    IdentityFacetCreate,
    IdentityFacetResponse,
    MergePersonsRequest,
    MergePersonsResponse,
)

router = APIRouter(tags=["identity"])


def _validate_case(case_id: str, db: Session):
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")


@router.post("/cases/{case_id}/graph/identity-facet", status_code=201)
def create_identity_facet(
    case_id: str,
    body: IdentityFacetCreate,
    db: Session = Depends(get_db),
):
    """
    Get-or-create an IdentityFacet:
    - Normalizes the value by facet_type rules
    - If this exact facet exists for this case, returns the existing one + linked persons
    - If new, creates the facet and links it to the specified person (or creates a new one)
    """
    _validate_case(case_id, db)
    result = resolve_identity_facet(
        case_id=case_id,
        facet_type=body.facet_type,
        value=body.value,
        person_id=body.person_id,
        classification_tag=body.classification_tag.value
        if hasattr(body.classification_tag, "value")
        else body.classification_tag,
    )
    return result


@router.get("/cases/{case_id}/graph/person/{person_id}/identifiers")
def get_identifiers(case_id: str, person_id: str, db: Session = Depends(get_db)):
    """Return all IdentityFacets linked to a person, grouped by facet_type."""
    _validate_case(case_id, db)
    return get_person_identifiers(case_id, person_id)


@router.post("/cases/{case_id}/graph/merge-persons", response_model=MergePersonsResponse)
def merge_persons_endpoint(
    case_id: str,
    body: MergePersonsRequest,
    db: Session = Depends(get_db),
):
    """
    Merge two persons: re-point all relationships and IdentityFacets from
    person_id_merge to person_id_keep. Deletes the merged person.
    """
    _validate_case(case_id, db)
    result = merge_persons(
        case_id=case_id,
        keep_id=body.person_id_keep,
        merge_id=body.person_id_merge,
        reason=body.reason,
    )
    return result
