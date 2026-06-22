"""Tests for Cryptocurrency Intelligence (Prompt 22).

Uses mocked blockchain API responses.
"""

from unittest.mock import patch, MagicMock

from app.adapters.crypto_adapter import BitcoinAdapter, EthereumAdapter


class TestBitcoinAdapter:
    def test_unavailable_without_key(self):
        """Bitcoin adapter without API key returns unavailable."""
        adapter = BitcoinAdapter()
        with patch("app.adapters.crypto_adapter.settings") as mock_settings:
            mock_settings.BLOCKCHAIN_API_KEY = ""
            assert not adapter.is_available()
            result = adapter.execute("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
            assert result.error is not None
            assert "unavailable" in result.error

    def test_extracts_counterparty_addresses(self):
        """Bitcoin adapter extracts counterparty wallet addresses."""
        adapter = BitcoinAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "address": "1TestAddr",
            "final_balance": 100000,
            "n_tx": 3,
            "total_received": 500000,
            "total_sent": 400000,
            "txs": [
                {
                    "hash": "tx_hash_1",
                    "time": 1700000000,
                    "inputs": [
                        {"prev_out": {"addr": "1InputAddr1", "value": 50000}},
                        {"prev_out": {"addr": "1InputAddr2", "value": 30000}},
                    ],
                    "out": [
                        {"addr": "1OutputAddr1", "value": 70000},
                        {"addr": "1TestAddr", "value": 10000},
                    ],
                },
                {
                    "hash": "tx_hash_2",
                    "time": 1700001000,
                    "inputs": [
                        {"prev_out": {"addr": "1TestAddr", "value": 10000}},
                    ],
                    "out": [
                        {"addr": "1OutputAddr2", "value": 9000},
                    ],
                },
            ],
        }

        with patch("app.adapters.crypto_adapter.settings") as mock_settings:
            mock_settings.BLOCKCHAIN_API_KEY = "test_key"
            with patch("app.adapters.crypto_adapter.httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_client.__enter__ = MagicMock(return_value=mock_client)
                mock_client.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value = mock_response
                mock_client_class.return_value = mock_client

                result = adapter.execute("1TestAddr")

        assert result.error is None
        addr_values = {e["value"] for e in result.extracted_entities}
        assert "1InputAddr1" in addr_values
        assert "1OutputAddr1" in addr_values
        assert "1OutputAddr2" in addr_values


class TestCommonInputOwnership:
    def test_multi_input_clustering(self):
        """Multi-input transaction creates cluster with correct evidence_basis."""
        adapter = BitcoinAdapter()

        tx_data = {
            "transactions": [
                {
                    "hash": "cluster_tx_hash",
                    "time": 1700000000,
                    "inputs": [
                        {"addr": "1Addr_A"},
                        {"addr": "1Addr_B"},
                        {"addr": "1Addr_C"},
                    ],
                    "outputs": [
                        {"addr": "1Addr_D", "value": 100000},
                    ],
                },
                {
                    "hash": "single_tx",
                    "time": 1700001000,
                    "inputs": [
                        {"addr": "1Addr_E"},
                    ],
                    "outputs": [
                        {"addr": "1Addr_F", "value": 50000},
                    ],
                },
            ],
        }

        clusters = adapter.find_common_input_clusters(tx_data)

        # Should find one cluster from the multi-input tx
        assert len(clusters) == 1
        cluster = clusters[0]
        assert set(cluster["addresses"]) == {"1Addr_A", "1Addr_B", "1Addr_C"}
        assert cluster["tx_hash"] == "cluster_tx_hash"
        assert cluster["confidence"] == 0.8

    def test_single_input_no_cluster(self):
        """Single-input transaction does NOT create a cluster."""
        adapter = BitcoinAdapter()

        tx_data = {
            "transactions": [
                {
                    "hash": "single_tx",
                    "inputs": [{"addr": "1SingleAddr"}],
                    "outputs": [{"addr": "1Output", "value": 1000}],
                },
            ],
        }

        clusters = adapter.find_common_input_clusters(tx_data)
        assert len(clusters) == 0


class TestEthereumAdapter:
    def test_unavailable_without_key(self):
        """Ethereum adapter without API key returns unavailable."""
        adapter = EthereumAdapter()
        with patch("app.adapters.crypto_adapter.settings") as mock_settings:
            mock_settings.ETHERSCAN_API_KEY = ""
            assert not adapter.is_available()
