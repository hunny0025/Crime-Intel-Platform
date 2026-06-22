"""Tests for HPL Grammar — Prompt 23.

Tests parsing, serialization, entity validation, and evidence status checking.
"""

import pytest
from app.reasoning.hpl.grammar import (
    parse_hpl, serialize_hpl, validate_hpl_entities,
    extract_evidence_lists, check_implied_evidence_status,
    HypothesisPredicate, EntityRef, TimeInterval, EvidenceItem,
)


class TestHPLParsing:
    def test_full_predicate_parse(self):
        """Parse a complete HPL predicate with DURING/IMPLIES/FORBIDS."""
        hpl = (
            'PREDICATE: Person[suspect_a] AT Location[site_x] '
            'DURING TimeInterval[2024-01-01T10:00Z, 2024-01-01T12:00Z, confidence:0.7] '
            'IMPLIES [CellTowerPing(location_area: site_x, window: 2024-01-01T10:00Z/12:00Z)] '
            'FORBIDS [CellTowerPing(location_area: site_y, window: 2024-01-01T10:00Z/12:00Z)]'
        )
        pred = parse_hpl(hpl)

        assert isinstance(pred, HypothesisPredicate)
        assert pred.subject.entity_type == "Person"
        assert pred.subject.entity_id == "suspect_a"
        assert pred.relationship == "AT"
        assert pred.obj.entity_type == "Location"
        assert pred.obj.entity_id == "site_x"

        assert pred.during is not None
        assert pred.during.confidence == 0.7
        assert "2024-01-01T10:00Z" in pred.during.from_ts

        assert len(pred.implies) == 1
        assert pred.implies[0].evidence_type == "CellTowerPing"
        assert pred.implies[0].params["location_area"] == "site_x"

        assert len(pred.forbids) == 1
        assert pred.forbids[0].evidence_type == "CellTowerPing"
        assert pred.forbids[0].params["location_area"] == "site_y"

    def test_predicate_without_during(self):
        """Parse predicate with IMPLIES but no DURING clause."""
        hpl = (
            'PREDICATE: Person[suspect_b] COMMUNICATED_WITH Person[victim_a] '
            'IMPLIES [CommunicationRecord(window: 2024-01-01T00:00Z/23:59Z)]'
        )
        pred = parse_hpl(hpl)

        assert pred.subject.entity_id == "suspect_b"
        assert pred.relationship == "COMMUNICATED_WITH"
        assert pred.obj.entity_id == "victim_a"
        assert pred.during is None
        assert len(pred.implies) == 1
        assert len(pred.forbids) == 0

    def test_predicate_implies_only(self):
        """Parse predicate with only IMPLIES (no DURING, no FORBIDS)."""
        hpl = (
            'PREDICATE: Person[p1] OWNS Device[d1] '
            'IMPLIES [GPSRecord(person: p1)]'
        )
        pred = parse_hpl(hpl)
        assert pred.subject.entity_id == "p1"
        assert pred.relationship == "OWNS"
        assert len(pred.implies) == 1
        assert pred.implies[0].evidence_type == "GPSRecord"

    def test_invalid_hpl_raises(self):
        """Malformed HPL raises an exception."""
        with pytest.raises(Exception):
            parse_hpl("NOT_A_VALID HPL STRING")


class TestHPLSerialization:
    def test_roundtrip(self):
        """Parse → serialize → parse produces equivalent structure."""
        hpl = (
            'PREDICATE: Person[s1] AT Location[l1] '
            'DURING TimeInterval[2024-01-01T10:00Z, 2024-01-01T12:00Z, confidence:0.8] '
            'IMPLIES [CellTowerPing(location_area: l1)] '
            'FORBIDS [GPSRecord(person: s1)]'
        )
        pred1 = parse_hpl(hpl)
        serialized = serialize_hpl(pred1)
        pred2 = parse_hpl(serialized)

        assert pred2.subject.entity_id == pred1.subject.entity_id
        assert pred2.relationship == pred1.relationship
        assert pred2.obj.entity_id == pred1.obj.entity_id
        assert len(pred2.implies) == len(pred1.implies)
        assert len(pred2.forbids) == len(pred1.forbids)


class TestEvidenceExtraction:
    def test_extract_from_multiple_predicates(self):
        """extract_evidence_lists combines IMPLIES/FORBIDS from multiple predicates."""
        preds = [
            'PREDICATE: Person[p1] AT Location[l1] IMPLIES [CellTowerPing(location_area: l1)]',
            'PREDICATE: Person[p1] COMMUNICATED_WITH Person[p2] '
            'IMPLIES [CommunicationRecord(window: 2024-01-01T00:00Z/23:59Z)] '
            'FORBIDS [GPSRecord(person: p1)]',
        ]
        implied, forbidden = extract_evidence_lists(preds)

        assert len(implied) == 2
        assert len(forbidden) == 1
        types = {i["evidence_type"] for i in implied}
        assert "CellTowerPing" in types
        assert "CommunicationRecord" in types
        assert forbidden[0]["evidence_type"] == "GPSRecord"
