"""Fuzzy entity resolution — username/email similarity matching.

Uses normalized Levenshtein distance (via rapidfuzz) and phonetic similarity
to suggest identity links between OSINT-derived entities and existing graph facets.
"""

import re
import logging
from typing import Optional

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

logger = logging.getLogger(__name__)

# Thresholds
SUGGEST_THRESHOLD = 0.75    # Above this → create SUGGESTED_IDENTIFIER
EXACT_THRESHOLD = 1.0       # Above this → auto-link (already handled by Phase 2)


def _normalize_handle(handle: str) -> str:
    """Strip common prefixes (@), lowercase, remove underscores/dots/dashes."""
    h = handle.lower().strip().lstrip("@")
    return re.sub(r"[._\-]", "", h)


def _extract_email_local(email: str) -> str:
    """Extract the local part before @."""
    parts = email.split("@")
    return _normalize_handle(parts[0]) if parts else _normalize_handle(email)


def _soundex(s: str) -> str:
    """Simple Soundex phonetic hash."""
    if not s:
        return ""
    s = s.upper()
    result = s[0]
    codes = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }
    prev = codes.get(s[0], "0")
    for ch in s[1:]:
        code = codes.get(ch, "0")
        if code != "0" and code != prev:
            result += code
        prev = code if code != "0" else prev
        if len(result) == 4:
            break
    return result.ljust(4, "0")


def username_similarity(handle_a: str, handle_b: str) -> dict:
    """
    Compute similarity between two usernames/handles.

    Returns dict with:
        - normalized_edit_distance: 0-1 (1 = identical)
        - phonetic_match: bool (Soundex codes match)
        - combined_score: weighted average
        - match_basis: explanation
    """
    norm_a = _normalize_handle(handle_a)
    norm_b = _normalize_handle(handle_b)

    if not norm_a or not norm_b:
        return {"combined_score": 0.0, "match_basis": "empty input"}

    # Normalized edit distance (1 = identical)
    ratio = fuzz.ratio(norm_a, norm_b) / 100.0

    # Phonetic similarity
    phonetic_match = _soundex(norm_a) == _soundex(norm_b)
    phonetic_score = 0.15 if phonetic_match else 0.0

    combined = min(1.0, ratio * 0.85 + phonetic_score)
    match_basis_parts = [f"edit_distance={ratio:.2f}"]
    if phonetic_match:
        match_basis_parts.append("phonetic_match")

    return {
        "normalized_edit_distance": ratio,
        "phonetic_match": phonetic_match,
        "combined_score": combined,
        "match_basis": f"username similarity ({', '.join(match_basis_parts)}): "
                       f"'{handle_a}' ↔ '{handle_b}'",
    }


def email_similarity(email_a: str, email_b: str) -> dict:
    """
    Compute similarity between two email addresses, comparing local parts
    across potentially different domains.
    """
    local_a = _extract_email_local(email_a)
    local_b = _extract_email_local(email_b)

    result = username_similarity(local_a, local_b)
    result["match_basis"] = (
        f"email local-part similarity: '{email_a}' ↔ '{email_b}' "
        f"(local parts: '{local_a}' ↔ '{local_b}', score={result['combined_score']:.2f})"
    )
    return result


def fuzzy_match_identifiers(
    candidate_value: str,
    candidate_type: str,
    existing_facets: list[dict],
    rejected_pairs: Optional[set] = None,
) -> list[dict]:
    """
    Match a candidate identifier against existing identity facets.

    Args:
        candidate_value: the value to match (e.g., "johndoe92")
        candidate_type: type of the candidate (e.g., "social_handle")
        existing_facets: list of {facet_type, value, facet_id, person_id}
        rejected_pairs: set of (candidate_value, facet_value) tuples to skip

    Returns:
        List of matches above SUGGEST_THRESHOLD, sorted by score descending.
    """
    rejected = rejected_pairs or set()
    matches = []

    for facet in existing_facets:
        facet_value = facet.get("value", "")
        facet_type = facet.get("facet_type", "")

        # Skip if this pair was previously rejected
        pair_key = (candidate_value.lower(), facet_value.lower())
        if pair_key in rejected or tuple(reversed(pair_key)) in rejected:
            continue

        # Choose comparison function based on type
        if "email" in candidate_type or "email" in facet_type:
            sim = email_similarity(candidate_value, facet_value)
        elif any(t in candidate_type for t in ["social_handle", "username"]) or \
             any(t in facet_type for t in ["social_handle", "username"]):
            sim = username_similarity(candidate_value, facet_value)
        else:
            # Generic string similarity
            sim = username_similarity(candidate_value, facet_value)

        if sim["combined_score"] >= SUGGEST_THRESHOLD:
            matches.append({
                "facet_id": facet.get("facet_id"),
                "facet_value": facet_value,
                "facet_type": facet_type,
                "person_id": facet.get("person_id"),
                "similarity_score": sim["combined_score"],
                "match_basis": sim["match_basis"],
            })

    matches.sort(key=lambda m: m["similarity_score"], reverse=True)
    return matches
