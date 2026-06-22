"""Tests for Social Graph Intelligence (Prompt 19)."""

from unittest.mock import patch, MagicMock

from app.adapters.social_adapter import SocialAdapter


class TestSocialAdapterAvailability:
    def test_unavailable_without_credentials(self):
        """Adapter with no credentials returns unavailable result cleanly."""
        adapter = SocialAdapter(platform="twitter")

        with patch("app.adapters.social_adapter.settings") as mock_settings:
            mock_settings.TWITTER_BEARER_TOKEN = ""
            assert not adapter.is_available()
            result = adapter.execute("someuser")
            assert result.error is not None
            assert "unavailable" in result.error
            assert "credentials not configured" in result.error

    def test_available_with_credentials(self):
        """Adapter with credentials reports available."""
        adapter = SocialAdapter(platform="github")

        with patch("app.adapters.social_adapter.settings") as mock_settings:
            mock_settings.GITHUB_TOKEN = "ghp_testtoken123"
            assert adapter.is_available()


class TestSocialExpand:
    def test_expand_respects_max_connections(self):
        """expand_connections respects max_connections limit."""
        adapter = SocialAdapter(platform="github")

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Return 10 connections
        mock_response.json.return_value = [
            {"login": f"user_{i}"} for i in range(10)
        ]

        with patch("app.adapters.social_adapter.settings") as mock_settings:
            mock_settings.GITHUB_TOKEN = "ghp_test"
            with patch("app.adapters.social_adapter.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                result = adapter.expand_connections("testuser", max_connections=5)

        # Should cap at 5
        assert len(result.extracted_entities) <= 5


class TestCommunityDetection:
    def test_louvain_produces_clusters(self):
        """Louvain on a synthetic graph produces sensible communities."""
        import networkx as nx
        try:
            import community as community_louvain
        except ImportError:
            return  # Skip if not installed

        # Two clearly separate clusters
        G = nx.Graph()
        # Cluster 1: A-B-C-D (fully connected)
        for a in ["a", "b", "c", "d"]:
            for b_node in ["a", "b", "c", "d"]:
                if a < b_node:
                    G.add_edge(a, b_node)
        # Cluster 2: X-Y-Z (fully connected)
        for a in ["x", "y", "z"]:
            for b_node in ["x", "y", "z"]:
                if a < b_node:
                    G.add_edge(a, b_node)
        # Single weak link between clusters
        G.add_edge("d", "x")

        partition = community_louvain.best_partition(G)

        # Nodes in cluster 1 should share a community
        assert partition["a"] == partition["b"] == partition["c"]
        # Nodes in cluster 2 should share a community
        assert partition["x"] == partition["y"] == partition["z"]
        # The two clusters should be different communities
        assert partition["a"] != partition["x"]
