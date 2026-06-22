"""Tests for Crime/Legal Ontology reference data and case classification.

Covers Prompt 9: seed loading, hierarchy queries, legal section lookups,
case classification via CLASSIFIED_AS.
"""


class TestReferenceDataLoading:
    def test_crime_categories_loaded(self, client):
        """Seed data should be loaded on startup — verify hierarchy exists."""
        response = client.get("/reference/crime-categories")
        assert response.status_code == 200
        categories = response.json()
        assert len(categories) >= 5  # 5 top-level categories

        # Check hierarchy depth
        names = [c["name"] for c in categories]
        assert "Financial Fraud" in names

        # Check children exist
        financial = next(c for c in categories if c["name"] == "Financial Fraud")
        child_names = [ch["name"] for ch in financial.get("children", [])]
        assert "Phishing / Vishing / Smishing" in child_names

    def test_legal_sections_for_category(self, client):
        """Query legal sections mapped to a crime category."""
        response = client.get("/reference/crime-categories/cc-identity-theft/legal-sections")
        assert response.status_code == 200
        sections = response.json()
        assert len(sections) >= 1
        # IT Act 66C should be mapped to identity theft
        section_ids = [s["id"] for s in sections]
        assert "ls-it-66c" in section_ids

    def test_legal_section_with_elements(self, client):
        """Query a legal section and verify elements are returned."""
        response = client.get("/reference/legal-sections/ls-it-66c")
        assert response.status_code == 200
        section = response.json()
        assert section["statute"] == "IT_Act_2000"
        assert section["section_number"] == "66C"
        assert len(section["elements"]) >= 2
        element_texts = [e["element_text"] for e in section["elements"]]
        assert any("electronic signature" in t.lower() or "password" in t.lower() for t in element_texts)

    def test_legal_section_not_found(self, client):
        response = client.get("/reference/legal-sections/nonexistent")
        assert response.status_code == 404


class TestCaseClassification:
    def test_classify_case(self, client, created_case):
        """Classify a case under crime categories."""
        case_id = created_case["case_id"]
        response = client.post(f"/reference/cases/{case_id}/classify", json={
            "crime_category_ids": ["cc-phishing", "cc-identity-theft"],
        })
        assert response.status_code == 201
        data = response.json()
        assert case_id in data["case_id"]
        assert "cc-phishing" in data["classified_as"]
        assert "cc-identity-theft" in data["classified_as"]

    def test_classify_nonexistent_category(self, client, created_case):
        """Classifying with a nonexistent category should fail."""
        case_id = created_case["case_id"]
        response = client.post(f"/reference/cases/{case_id}/classify", json={
            "crime_category_ids": ["cc-nonexistent"],
        })
        assert response.status_code == 404
