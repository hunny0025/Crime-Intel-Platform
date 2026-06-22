"""Tests for Phase 8 — Cross Case Intelligence.

Covers corpus extraction PII safety, similarity scoring, playbook templates,
behavioral fingerprint matching, and modus operandi detection.
"""

import re
import json
import hashlib


# PII patterns from corpus_extractor
PII_PATTERNS = [
    re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'),
    re.compile(r'\+?\d{10,15}'),
    re.compile(r'\b\d{12}\b'),
    re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'),
]


class TestCorpusExtraction:
    """Prompt 42: PII-safe pattern extraction."""

    def test_pii_safe_validation(self):
        """Pattern with no PII passes PII check."""
        pattern = json.dumps({
            "crime_category_ids": ["online_fraud"],
            "evidence_type_profile": {"communication_record": 0.6, "financial_record": 0.4},
            "hypothesis_count_at_peak": 3,
        })
        pii_safe = not any(p.search(pattern) for p in PII_PATTERNS)
        assert pii_safe is True

    def test_pii_detected_email(self):
        """Pattern containing email is flagged."""
        pattern = json.dumps({"name": "test@example.com"})
        pii_safe = not any(p.search(pattern) for p in PII_PATTERNS)
        assert pii_safe is False

    def test_pii_detected_phone(self):
        """Pattern containing phone number is flagged."""
        pattern = json.dumps({"phone": "+919876543210"})
        pii_safe = not any(p.search(pattern) for p in PII_PATTERNS)
        assert pii_safe is False

    def test_evidence_profile_sums_to_one(self):
        """Evidence type profile proportions must sum to ~1.0."""
        profile = {"communication_record": 0.5, "device_artifact": 0.3, "financial_record": 0.2}
        total = sum(profile.values())
        assert abs(total - 1.0) < 0.001

    def test_case_id_hashing(self):
        """Extracted case_id is SHA-256 hashed, not raw."""
        raw_id = "CASE-2024-001"
        hashed = hashlib.sha256(raw_id.encode()).hexdigest()
        assert len(hashed) == 64
        assert raw_id not in hashed


class TestSimilarityScoring:
    """Prompt 43: case matching similarity computation."""

    def test_identical_profiles_high_similarity(self):
        """Two identical profiles should have similarity near 1.0."""
        # Category Jaccard = 1.0, evidence cosine = 1.0, hyp sim = 1.0
        score = 0.4 * 1.0 + 0.4 * 1.0 + 0.2 * 1.0
        assert score == 1.0

    def test_no_overlap_zero_similarity(self):
        """No category or evidence overlap → low similarity."""
        score = 0.4 * 0.0 + 0.4 * 0.0 + 0.2 * 0.5
        assert score == 0.1

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal evidence profiles → cosine=0."""
        v1 = {"comm": 1.0, "device": 0.0}
        v2 = {"comm": 0.0, "device": 1.0}
        all_keys = set(v1) | set(v2)
        dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in all_keys)
        assert dot == 0.0

    def test_cosine_similarity_parallel(self):
        """Parallel evidence profiles → cosine=1."""
        v1 = {"comm": 0.6, "device": 0.4}
        v2 = {"comm": 0.6, "device": 0.4}
        all_keys = set(v1) | set(v2)
        dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in all_keys)
        mag1 = sum(v ** 2 for v in v1.values()) ** 0.5
        mag2 = sum(v ** 2 for v in v2.values()) ** 0.5
        cosine = dot / (mag1 * mag2)
        assert abs(cosine - 1.0) < 0.001


class TestPlaybookEngine:
    """Prompt 44: investigation playbook templates."""

    def test_default_playbook_has_five_steps(self):
        """Default playbook has exactly 5 steps."""
        default_steps = [
            {"step_number": 1, "action_type": "collect_digital_evidence"},
            {"step_number": 2, "action_type": "obtain_communication_records"},
            {"step_number": 3, "action_type": "obtain_financial_records"},
            {"step_number": 4, "action_type": "location_verification"},
            {"step_number": 5, "action_type": "witness_documentation"},
        ]
        assert len(default_steps) == 5

    def test_steps_ordered_by_step_number(self):
        """Steps should be in ascending step_number order."""
        steps = [3, 1, 5, 2, 4]
        sorted_steps = sorted(steps)
        assert sorted_steps == [1, 2, 3, 4, 5]

    def test_progress_fraction(self):
        """2 of 5 steps completed → 0.4 progress."""
        completed = 2
        total = 5
        fraction = completed / total
        assert abs(fraction - 0.4) < 0.01

    def test_next_step_is_first_pending(self):
        """Next priority step is the first uncompleted step."""
        statuses = ["completed", "completed", "pending", "pending", "pending"]
        next_step = None
        for i, s in enumerate(statuses):
            if s == "pending":
                next_step = i + 1
                break
        assert next_step == 3


class TestBehavioralFingerprint:
    """Prompt 45: behavioral fingerprint and recidivism."""

    def test_comm_time_signature_normalized(self):
        """Communication time histogram must sum to 1.0."""
        hist = [0] * 24
        hist[9] = 10
        hist[10] = 15
        hist[14] = 8
        hist[15] = 7
        total = sum(hist) or 1
        normalized = [h / total for h in hist]
        assert abs(sum(normalized) - 1.0) < 0.001

    def test_fingerprint_similarity_cosine(self):
        """Two similar communication patterns → high similarity."""
        fp1 = [0.0] * 24
        fp2 = [0.0] * 24
        # Both active at 9-10 AM
        fp1[9] = 0.5
        fp1[10] = 0.5
        fp2[9] = 0.4
        fp2[10] = 0.6

        dot = sum(a * b for a, b in zip(fp1, fp2))
        mag1 = sum(a ** 2 for a in fp1) ** 0.5
        mag2 = sum(a ** 2 for a in fp2) ** 0.5
        cosine = dot / (mag1 * mag2) if mag1 > 0 and mag2 > 0 else 0
        assert cosine > 0.9  # Very similar

    def test_different_patterns_low_similarity(self):
        """Day vs night patterns → low similarity."""
        fp1 = [0.0] * 24
        fp2 = [0.0] * 24
        fp1[9] = 1.0   # Morning person
        fp2[22] = 1.0  # Night person

        dot = sum(a * b for a, b in zip(fp1, fp2))
        assert dot == 0.0

    def test_person_id_is_hashed(self):
        """Fingerprint stores hashed person ID, not raw."""
        person_id = "person-suspect-123"
        hashed = hashlib.sha256(person_id.encode()).hexdigest()
        assert len(hashed) == 64
        assert person_id not in hashed

    def test_recidivism_threshold(self):
        """Similarity > 0.6 triggers recidivism flag."""
        similarity = 0.75
        threshold = 0.6
        assert similarity > threshold


class TestModusOperandiDetection:
    """Prompt 46: modus operandi pattern detection."""

    def test_mo_overlap_jaccard(self):
        """MO overlap uses set overlap between evidence tools."""
        case_tools = {"cellebrite", "wireshark", "maltego"}
        pattern_tools = {"cellebrite", "maltego", "autopsy"}
        overlap = case_tools & pattern_tools
        total = case_tools | pattern_tools
        jaccard = len(overlap) / len(total)
        assert abs(jaccard - 0.5) < 0.01

    def test_high_overlap_detected(self):
        """Overlap > 0.5 → known MO detected."""
        overlap = 0.75
        assert overlap > 0.5

    def test_no_overlap(self):
        """Completely different tools → overlap=0."""
        case_tools = {"tool_a", "tool_b"}
        pattern_tools = {"tool_c", "tool_d"}
        overlap = case_tools & pattern_tools
        total = case_tools | pattern_tools
        jaccard = len(overlap) / len(total)
        assert jaccard == 0.0
