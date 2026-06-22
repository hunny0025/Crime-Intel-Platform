"""Idempotent loader for Crime Ontology and Legal Ontology reference data.

Uses MERGE (not CREATE) so re-running never duplicates nodes.
"""

import json
import logging
from pathlib import Path

from app.graph.driver import Neo4jClient, get_neo4j_client

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).parent


def load_crime_ontology(client: Neo4jClient = None) -> int:
    """Load crime category hierarchy from crime_ontology.json. Returns node count."""
    client = client or get_neo4j_client()
    with open(SEEDS_DIR / "crime_ontology.json") as f:
        data = json.load(f)

    count = 0

    def _load_category(cat: dict, parent_id: str = None):
        nonlocal count
        client.execute_write(
            """
            MERGE (c:CrimeCategory {id: $id})
            SET c.name = $name, c.parent_category_id = $parent_id
            """,
            {"id": cat["id"], "name": cat["name"], "parent_id": parent_id},
        )
        count += 1

        # Create parent-child relationship
        if parent_id:
            client.execute_write(
                """
                MATCH (parent:CrimeCategory {id: $parent_id})
                MATCH (child:CrimeCategory {id: $child_id})
                MERGE (parent)-[:HAS_CHILD_CATEGORY]->(child)
                """,
                {"parent_id": parent_id, "child_id": cat["id"]},
            )

        for child in cat.get("children", []):
            _load_category(child, cat["id"])

    for category in data["categories"]:
        _load_category(category)

    logger.info("Loaded %d crime categories", count)
    return count


def load_legal_ontology(client: Neo4jClient = None) -> int:
    """Load legal sections, elements, statutes, chapters, definitions, exceptions, punishments, burdens, caselaws, and interpretations from legal_ontology.json. Returns node count."""
    client = client or get_neo4j_client()
    with open(SEEDS_DIR / "legal_ontology.json") as f:
        data = json.load(f)

    count = 0

    # 1. Statutes
    for stat in data.get("statutes", []):
        client.execute_write(
            """
            MERGE (s:Statute {id: $id})
            SET s.name = $name, s.year = $year, s.jurisdiction = $jurisdiction
            """,
            stat,
        )
        count += 1

    # 2. Chapters
    for chap in data.get("chapters", []):
        client.execute_write(
            """
            MERGE (c:Chapter {id: $id})
            SET c.chapter_number = $chapter_number, c.title = $title
            """,
            chap,
        )
        count += 1
        if chap.get("statute_id"):
            client.execute_write(
                """
                MATCH (c:Chapter {id: $cid})
                MATCH (s:Statute {id: $sid})
                MERGE (c)-[:BELONGS_TO_STATUTE]->(s)
                """,
                {"cid": chap["id"], "sid": chap["statute_id"]},
            )

    # 3. Sections and Elements
    for section in data.get("sections", []):
        # Create LegalSection
        client.execute_write(
            """
            MERGE (s:LegalSection {id: $id})
            SET s.statute = $statute,
                s.section_number = $section_number,
                s.title = $title,
                s.summary = $summary
            """,
            {
                "id": section["id"],
                "statute": section["statute"],
                "section_number": section["section_number"],
                "title": section["title"],
                "summary": section["summary"],
            },
        )
        count += 1

        if section.get("statute_id"):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (stat:Statute {id: $stat_id})
                MERGE (sec)-[:BELONGS_TO_STATUTE]->(stat)
                """,
                {"sec_id": section["id"], "stat_id": section["statute_id"]},
            )
        if section.get("chapter_id"):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (c:Chapter {id: $chap_id})
                MERGE (sec)-[:BELONGS_TO_CHAPTER]->(c)
                """,
                {"sec_id": section["id"], "chap_id": section["chapter_id"]},
            )

        # Create LegalElements
        for element in section.get("elements", []):
            client.execute_write(
                """
                MERGE (e:LegalElement {id: $id})
                SET e.section_id = $section_id,
                    e.element_text = $element_text,
                    e.evidence_types_typically_required = $evidence_types
                """,
                {
                    "id": element["id"],
                    "section_id": element["section_id"],
                    "element_text": element["element_text"],
                    "evidence_types": element["evidence_types_typically_required"],
                },
            )
            count += 1

            # Link element to section
            client.execute_write(
                """
                MATCH (s:LegalSection {id: $section_id})
                MATCH (e:LegalElement {id: $element_id})
                MERGE (s)-[:HAS_ELEMENT]->(e)
                """,
                {"section_id": element["section_id"], "element_id": element["id"]},
            )

        # Create MAPS_TO_LEGAL_SECTION relationships
        for cat_id in section.get("mapped_crime_categories", []):
            client.execute_write(
                """
                MATCH (c:CrimeCategory {id: $cat_id})
                MATCH (s:LegalSection {id: $section_id})
                MERGE (c)-[:MAPS_TO_LEGAL_SECTION {typical: true}]->(s)
                """,
                {"cat_id": cat_id, "section_id": section["id"]},
            )

    # 4. Definitions
    for item in data.get("definitions", []):
        client.execute_write(
            """
            MERGE (d:Definition {id: $id})
            SET d.term = $term, d.text = $text
            """,
            item,
        )
        count += 1
        if item.get("section_id"):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (d:Definition {id: $did})
                MERGE (sec)-[:HAS_DEFINITION]->(d)
                """,
                {"sec_id": item["section_id"], "did": item["id"]},
            )

    # 5. Exceptions
    for item in data.get("exceptions", []):
        client.execute_write(
            """
            MERGE (e:Exception {id: $id})
            SET e.title = $title, e.text = $text
            """,
            item,
        )
        count += 1
        for sec_id in item.get("applies_to_section_ids", []):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (e:Exception {id: $eid})
                MERGE (sec)-[:HAS_EXCEPTION]->(e)
                """,
                {"sec_id": sec_id, "eid": item["id"]},
            )

    # 6. Punishments
    for item in data.get("punishments", []):
        client.execute_write(
            """
            MERGE (p:Punishment {id: $id})
            SET p.punishment_type = $punishment_type, p.duration = $duration, p.amount = $amount
            """,
            item,
        )
        count += 1
        if item.get("section_id"):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (p:Punishment {id: $pid})
                MERGE (sec)-[:HAS_PUNISHMENT]->(p)
                """,
                {"sec_id": item["section_id"], "pid": item["id"]},
            )

    # 7. Burdens
    for item in data.get("burdens", []):
        client.execute_write(
            """
            MERGE (b:BurdenOfProof {id: $id})
            SET b.standard = $standard, b.party = $party, b.description = $description
            """,
            item,
        )
        count += 1
        if item.get("section_id"):
            client.execute_write(
                """
                MATCH (sec:LegalSection {id: $sec_id})
                MATCH (b:BurdenOfProof {id: $bid})
                MERGE (sec)-[:HAS_BURDEN]->(b)
                """,
                {"sec_id": item["section_id"], "bid": item["id"]},
            )

    # 8. CaseLaws
    for item in data.get("caselaws", []):
        client.execute_write(
            """
            MERGE (c:CaseLaw {id: $id})
            SET c.citation = $citation, c.title = $title, c.court = $court, c.year = $year, c.summary = $summary
            """,
            item,
        )
        count += 1

    # 9. JudicialInterpretations
    for item in data.get("interpretations", []):
        client.execute_write(
            """
            MERGE (ji:JudicialInterpretation {id: $id})
            SET ji.rule = $rule, ji.holding = $holding
            """,
            item,
        )
        count += 1
        if item.get("caselaw_id"):
            client.execute_write(
                """
                MATCH (ji:JudicialInterpretation {id: $ji_id})
                MATCH (c:CaseLaw {id: $cid})
                MERGE (ji)-[:DERIVED_FROM]->(c)
                """,
                {"ji_id": item["id"], "cid": item["caselaw_id"]},
            )
        if item.get("interprets_section_id"):
            client.execute_write(
                """
                MATCH (ji:JudicialInterpretation {id: $ji_id})
                MATCH (sec:LegalSection {id: $sec_id})
                MERGE (ji)-[:INTERPRETS]->(sec)
                """,
                {"ji_id": item["id"], "sec_id": item["interprets_section_id"]},
            )
        if item.get("interprets_element_id"):
            client.execute_write(
                """
                MATCH (ji:JudicialInterpretation {id: $ji_id})
                MATCH (el:LegalElement {id: $el_id})
                MERGE (ji)-[:INTERPRETS]->(el)
                """,
                {"ji_id": item["id"], "el_id": item["interprets_element_id"]},
            )

    # 10. Cross-References between sections
    for xref in data.get("cross_references", []):
        from_id = xref.get("from_section_id")
        to_id = xref.get("to_section_id")
        rel_type = xref.get("relationship", "RELATED_TO").upper()
        desc = xref.get("description", "")
        if from_id and to_id:
            client.execute_write(
                """
                MATCH (s1:LegalSection {id: $from_id})
                MATCH (s2:LegalSection {id: $to_id})
                MERGE (s1)-[r:CROSS_REFERENCES {relationship_type: $rel_type}]->(s2)
                SET r.description = $desc
                """,
                {"from_id": from_id, "to_id": to_id, "rel_type": rel_type, "desc": desc},
            )
            count += 1

    logger.info("Loaded %d legal section/element/linked nodes", count)
    return count


def load_all_reference_data(client: Neo4jClient = None) -> dict:
    """Load all reference ontology data. Returns counts."""
    client = client or get_neo4j_client()
    crime_count = load_crime_ontology(client)
    legal_count = load_legal_ontology(client)
    return {"crime_categories": crime_count, "legal_nodes": legal_count}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = load_all_reference_data()
    print(f"Loaded: {result}")
