"""Tests for Attribution Engine — fuzzy matching (Prompt 18)."""

from app.resolution.fuzzy_match import (
    username_similarity, email_similarity, fuzzy_match_identifiers,
    SUGGEST_THRESHOLD,
)


class TestUsernameSimilarity:
    def test_identical_handles(self):
        """Identical handles score 1.0."""
        result = username_similarity("john_doe_92", "john_doe_92")
        assert result["combined_score"] >= 0.99

    def test_similar_handles_above_threshold(self):
        """'john_doe_92' vs 'johndoe92' — removing underscores, very similar."""
        result = username_similarity("john_doe_92", "johndoe92")
        assert result["combined_score"] >= SUGGEST_THRESHOLD

    def test_dissimilar_handles(self):
        """Completely different handles score low."""
        result = username_similarity("john_doe_92", "alice_wonderland")
        assert result["combined_score"] < SUGGEST_THRESHOLD

    def test_phonetic_match(self):
        """Handles with same phonetic representation get bonus."""
        # "john" and "jon" should have phonetic similarity
        result = username_similarity("john", "jon")
        assert result["phonetic_match"] is True


class TestEmailSimilarity:
    def test_same_local_different_domain(self):
        """Same local part across domains scores high."""
        result = email_similarity("john.doe@gmail.com", "john.doe@yahoo.com")
        assert result["combined_score"] >= SUGGEST_THRESHOLD

    def test_different_emails(self):
        """Different local parts score low."""
        result = email_similarity("john@gmail.com", "alice@gmail.com")
        assert result["combined_score"] < SUGGEST_THRESHOLD


class TestFuzzyMatchIdentifiers:
    def test_match_above_threshold(self):
        """Candidate matching existing facet above threshold returns match."""
        existing = [
            {"facet_id": "f1", "facet_type": "social_handle",
             "value": "john_doe_92", "person_id": "p1"},
        ]
        matches = fuzzy_match_identifiers(
            candidate_value="johndoe92",
            candidate_type="social_handle",
            existing_facets=existing,
        )
        assert len(matches) >= 1
        assert matches[0]["similarity_score"] >= SUGGEST_THRESHOLD

    def test_rejected_pair_excluded(self):
        """Previously rejected pairs don't reappear."""
        existing = [
            {"facet_id": "f1", "facet_type": "social_handle",
             "value": "john_doe_92", "person_id": "p1"},
        ]
        matches = fuzzy_match_identifiers(
            candidate_value="johndoe92",
            candidate_type="social_handle",
            existing_facets=existing,
            rejected_pairs={("johndoe92", "john_doe_92")},
        )
        assert len(matches) == 0

    def test_no_match_below_threshold(self):
        """Dissimilar values return no matches."""
        existing = [
            {"facet_id": "f1", "facet_type": "email",
             "value": "alice@example.com", "person_id": "p1"},
        ]
        matches = fuzzy_match_identifiers(
            candidate_value="bob@different.com",
            candidate_type="email",
            existing_facets=existing,
        )
        assert len(matches) == 0
