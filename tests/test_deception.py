"""Tests for Deception Detection integration (Prompt 21).

Uses the placeholder/mock model for deterministic scoring.
"""

from unittest.mock import patch, MagicMock


class TestDeceptionDetectionService:
    """Tests for the standalone deception-detection-service."""

    def test_placeholder_model_deterministic(self):
        """Placeholder model returns deterministic score from content hash."""
        from importlib.machinery import SourceFileLoader
        main_module = SourceFileLoader("deception_main", "deception-detection-service/app/main.py").load_module()
        PlaceholderDetector = main_module.PlaceholderDetector

        detector = PlaceholderDetector()
        content = b"test content for deception detection"

        result1 = detector.detect(content, "image/jpeg")
        result2 = detector.detect(content, "image/jpeg")

        # Same content → same score (deterministic)
        assert result1.deception_score == result2.deception_score
        assert result1.model_name == "placeholder_detector"
        assert result1.confidence == 0.5  # Placeholder has fixed low confidence

    def test_stylometric_heuristic_low_confidence(self):
        """Stylometric heuristic is clearly labeled as low-confidence."""
        from importlib.machinery import SourceFileLoader
        main_module = SourceFileLoader("deception_main", "deception-detection-service/app/main.py").load_module()
        StylometricHeuristic = main_module.StylometricHeuristic

        heuristic = StylometricHeuristic()
        result = heuristic.analyze(
            message="This is a test message that differs from the reference pattern.",
            reference_messages=[
                "Short msg.",
                "Another short one.",
                "Brief text here.",
            ],
        )

        assert result.model_name == "stylometric_heuristic_v1"
        assert result.confidence <= 0.3  # Explicitly capped
        assert "heuristic" in result.explanation.lower()

    def test_stylometric_insufficient_references(self):
        """Stylometric with <3 references returns low score."""
        from importlib.machinery import SourceFileLoader
        main_module = SourceFileLoader("deception_main", "deception-detection-service/app/main.py").load_module()
        StylometricHeuristic = main_module.StylometricHeuristic

        heuristic = StylometricHeuristic()
        result = heuristic.analyze(
            message="Test message",
            reference_messages=["Only one ref"],
        )
        assert result.deception_score == 0.0
        assert "Insufficient" in result.explanation


class TestDeceptionIntegration:
    def test_assess_endpoint(self, client, created_case):
        """Deception assessment endpoint stores result."""
        case_id = created_case["case_id"]

        # Mock the httpx call to deception service
        mock_detection = {
            "deception_score": 0.35,
            "confidence": 0.5,
            "model_name": "placeholder_detector",
            "model_version": "0.1.0",
            "explanation": "Placeholder model assessment",
            "content_hash": "abc123",
        }

        with patch("app.routers.deception.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_detection
            mock_resp.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_class.return_value = mock_client

            resp = client.post(f"/cases/{case_id}/deception/assess", json={
                "artifact_id": str(uuid.uuid4()),
                "content_type": "image",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["deception_score"] == 0.35
        assert data["model_name"] == "placeholder_detector"
        assert data["assessment_id"]  # UUID assigned


import uuid
