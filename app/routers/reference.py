"""Reference data endpoints — Crime Ontology and Legal Ontology."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Case
from app.graph.driver import get_neo4j_client
from app.graph import crud
from app.graph.schemas import ClassifyCaseRequest

router = APIRouter(prefix="/reference", tags=["reference"])


# ── Crime Categories ─────────────────────────────────────────────────────

@router.get("/crime-categories")
def get_crime_categories():
    """Return the full crime category hierarchy."""
    client = get_neo4j_client()

    # Get all categories
    result = client.execute_read(
        """
        MATCH (c:CrimeCategory)
        OPTIONAL MATCH (c)-[:HAS_CHILD_CATEGORY]->(child:CrimeCategory)
        RETURN c {.*} AS category,
               c.name AS name,
               collect(child {.*}) AS children
        ORDER BY name
        """
    )

    # Build hierarchy: top-level categories (no parent)
    all_cats = {}
    for row in result:
        cat = row["category"]
        cat_id = cat["id"]
        if cat_id not in all_cats:
            all_cats[cat_id] = {**cat, "children": []}
        for child in row["children"]:
            if child.get("id"):
                all_cats[cat_id]["children"].append(child)

    # Return only top-level
    top_level = [
        cat for cat in all_cats.values()
        if cat.get("parent_category_id") is None
    ]
    return top_level


@router.get("/crime-categories/{category_id}")
def get_crime_category(category_id: str):
    """Return a single crime category with its children."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (c:CrimeCategory {id: $id})
        OPTIONAL MATCH (c)-[:HAS_CHILD_CATEGORY]->(child:CrimeCategory)
        RETURN c {.*} AS category, collect(child {.*}) AS children
        """,
        {"id": category_id},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Crime category not found")
    cat = result[0]["category"]
    cat["children"] = result[0]["children"]
    return cat


@router.get("/crime-categories/{category_id}/legal-sections")
def get_legal_sections_for_category(category_id: str):
    """Return legal sections mapped to a crime category."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (c:CrimeCategory {id: $id})-[r:MAPS_TO_LEGAL_SECTION]->(s:LegalSection)
        OPTIONAL MATCH (s)-[:HAS_ELEMENT]->(e:LegalElement)
        RETURN s {.*} AS section,
               collect(e {.*}) AS elements,
               r.typical AS typical
        """,
        {"id": category_id},
    )
    sections = []
    for row in result:
        section = row["section"]
        section["elements"] = row["elements"]
        section["typical"] = row.get("typical", True)
        sections.append(section)
    return sections


# ── Legal Sections ───────────────────────────────────────────────────────

@router.get("/legal-sections/{section_id}")
def get_legal_section(section_id: str):
    """Return a legal section with its elements."""
    client = get_neo4j_client()
    result = client.execute_read(
        """
        MATCH (s:LegalSection {id: $id})
        OPTIONAL MATCH (s)-[:HAS_ELEMENT]->(e:LegalElement)
        RETURN s {.*} AS section, collect(e {.*}) AS elements
        """,
        {"id": section_id},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Legal section not found")
    section = result[0]["section"]
    section["elements"] = result[0]["elements"]
    return section


# ── Case Classification ─────────────────────────────────────────────────

@router.post("/cases/{case_id}/classify", status_code=201, tags=["cases"])
def classify_case(
    case_id: str,
    body: ClassifyCaseRequest,
    db: Session = Depends(get_db),
):
    """Link a case to one or more CrimeCategory ids via CLASSIFIED_AS."""
    # Validate case exists in postgres
    case = db.query(Case).filter(Case.case_id == uuid.UUID(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Ensure case anchor node exists in Neo4j
    crud.ensure_case_anchor(case_id)

    client = get_neo4j_client()
    linked = []

    for cat_id in body.crime_category_ids:
        # Verify category exists
        existing = client.execute_read(
            "MATCH (c:CrimeCategory {id: $id}) RETURN c.id AS id",
            {"id": cat_id},
        )
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Crime category not found: {cat_id}",
            )

        # Create CLASSIFIED_AS edge
        client.execute_write(
            """
            MATCH (ca:CaseAnchor {id: $case_id})
            MATCH (cc:CrimeCategory {id: $cat_id})
            MERGE (ca)-[:CLASSIFIED_AS]->(cc)
            """,
            {"case_id": case_id, "cat_id": cat_id},
        )
        linked.append(cat_id)

    return {"case_id": case_id, "classified_as": linked}
