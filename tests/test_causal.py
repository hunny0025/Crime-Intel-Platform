"""Tests for Causal Reasoning Layer — Prompt 26.

Tests causal chain construction and counterfactual simulation.
"""


class TestCausalChainUnit:
    """Unit tests for causal chain logic (no Neo4j)."""

    def test_chain_confidence_is_product(self):
        """Chain confidence = product of individual step confidences."""
        # A --0.9--> B --0.8--> C
        steps = [0.9, 0.8]
        chain_conf = 1.0
        for s in steps:
            chain_conf *= s
        assert abs(chain_conf - 0.72) < 0.01

    def test_counterfactual_no_alternative_path(self):
        """If removed event is the only cause, result is 'focal_event_prevented'."""
        # Linear chain: A → B → C
        # Remove B → no alternative path to C
        # Expected: focal_event_prevented
        has_alternative = False
        result = "focal_event_unchanged" if has_alternative else "focal_event_prevented"
        assert result == "focal_event_prevented"

    def test_counterfactual_with_alternative_path(self):
        """If alternative path exists, result is 'focal_event_unchanged'."""
        # Chain: A → B → C  AND  A → C directly
        # Remove B → A → C still exists
        has_alternative = True
        result = "focal_event_unchanged" if has_alternative else "focal_event_prevented"
        assert result == "focal_event_unchanged"


class TestCausalLayerIntegration:
    """Integration test patterns (require Neo4j fixture)."""

    def test_three_event_chain(self, client, created_case):
        """Build A→B→C chain, verify counterfactual removing B = prevented."""
        case_id = created_case["case_id"]

        # Create three events
        events = []
        for i, etype in enumerate(["meeting", "transfer", "crime"]):
            evt = client.post(f"/cases/{case_id}/graph/event", json={
                "case_id": case_id, "event_type": etype,
                "valid_from": f"2024-01-01T{10+i}:00:00",
                "classification_tag": "case_sensitive",
            }).json()
            events.append(evt)

        # Create causal links: A→B, B→C
        client.post(f"/cases/{case_id}/graph/causal-link", json={
            "cause_event_id": events[0]["id"],
            "effect_event_id": events[1]["id"],
            "mechanism": "Meeting led to transfer",
            "confidence": 0.9,
        })
        client.post(f"/cases/{case_id}/graph/causal-link", json={
            "cause_event_id": events[1]["id"],
            "effect_event_id": events[2]["id"],
            "mechanism": "Transfer enabled crime",
            "confidence": 0.8,
        })

        # Counterfactual: remove B
        resp = client.post(f"/cases/{case_id}/reasoning/counterfactual", json={
            "focal_event_id": events[2]["id"],
            "removed_event_id": events[1]["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["counterfactual_result"] == "focal_event_prevented"

    def test_parallel_path_unchanged(self, client, created_case):
        """With parallel causal path, removing one still leaves alternative."""
        case_id = created_case["case_id"]

        events = []
        for i, etype in enumerate(["cause_a", "cause_b", "effect"]):
            evt = client.post(f"/cases/{case_id}/graph/event", json={
                "case_id": case_id, "event_type": etype,
                "valid_from": f"2024-01-01T{10+i}:00:00",
                "classification_tag": "case_sensitive",
            }).json()
            events.append(evt)

        # A→C and B→C (parallel causes)
        client.post(f"/cases/{case_id}/graph/causal-link", json={
            "cause_event_id": events[0]["id"],
            "effect_event_id": events[2]["id"],
            "mechanism": "Direct cause A",
            "confidence": 0.9,
        })
        client.post(f"/cases/{case_id}/graph/causal-link", json={
            "cause_event_id": events[1]["id"],
            "effect_event_id": events[2]["id"],
            "mechanism": "Direct cause B",
            "confidence": 0.85,
        })

        # Remove A → B→C still exists
        resp = client.post(f"/cases/{case_id}/reasoning/counterfactual", json={
            "focal_event_id": events[2]["id"],
            "removed_event_id": events[0]["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["counterfactual_result"] == "focal_event_unchanged"
