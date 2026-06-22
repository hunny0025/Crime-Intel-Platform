"""Blockchain explorer adapters — Bitcoin and Ethereum public chain queries.

Adapters require API keys via environment variables. Without keys, they
return unavailable results per the BaseOSINTAdapter contract.
"""

import logging
import httpx
from typing import Optional
from app.adapters.base import BaseOSINTAdapter, OSINTResult
from app.config import settings

logger = logging.getLogger(__name__)


class BitcoinAdapter(BaseOSINTAdapter):
    source_type = "crypto_bitcoin"

    def is_available(self) -> bool:
        return bool(settings.BLOCKCHAIN_API_KEY)

    def execute(self, query: str) -> OSINTResult:
        """Fetch Bitcoin address transaction history."""
        if not self.is_available():
            return self.unavailable_result(query)
        try:
            url = f"https://blockchain.info/rawaddr/{query}"
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, params={"limit": 50})
                resp.raise_for_status()
                data = resp.json()

            txs = data.get("txs", [])
            entities = []
            seen_addrs = set()

            for tx in txs:
                # Extract input addresses (for common-input-ownership)
                input_addrs = []
                for inp in tx.get("inputs", []):
                    prev = inp.get("prev_out", {})
                    addr = prev.get("addr")
                    if addr and addr != query:
                        input_addrs.append(addr)
                        if addr not in seen_addrs:
                            seen_addrs.add(addr)
                            entities.append({
                                "entity_type": "crypto_wallet_address",
                                "value": addr,
                                "confidence": 0.5,
                                "relationship": "input",
                                "tx_hash": tx.get("hash"),
                            })

                # Extract output addresses
                for out in tx.get("out", []):
                    addr = out.get("addr")
                    if addr and addr != query and addr not in seen_addrs:
                        seen_addrs.add(addr)
                        entities.append({
                            "entity_type": "crypto_wallet_address",
                            "value": addr,
                            "confidence": 0.5,
                            "relationship": "output",
                            "tx_hash": tx.get("hash"),
                        })

            raw = {
                "address": data.get("address"),
                "final_balance": data.get("final_balance"),
                "n_tx": data.get("n_tx"),
                "total_received": data.get("total_received"),
                "total_sent": data.get("total_sent"),
                "transactions": [
                    {
                        "hash": tx.get("hash"),
                        "time": tx.get("time"),
                        "inputs": [
                            {"addr": inp.get("prev_out", {}).get("addr"),
                             "value": inp.get("prev_out", {}).get("value")}
                            for inp in tx.get("inputs", [])
                        ],
                        "outputs": [
                            {"addr": out.get("addr"), "value": out.get("value")}
                            for out in tx.get("out", [])
                        ],
                    }
                    for tx in txs[:50]
                ],
            }

            return OSINTResult(
                source_type=self.source_type, query=query,
                raw_result=raw, extracted_entities=entities,
            )
        except Exception as e:
            return OSINTResult(
                source_type=self.source_type, query=query,
                raw_result={}, extracted_entities=[], error=str(e),
            )

    def find_common_input_clusters(self, tx_data: dict) -> list[dict]:
        """
        Common-input-ownership heuristic: addresses that appear as multiple
        inputs to the same transaction are very likely controlled by the same
        entity (spending requires private keys for all inputs).
        """
        clusters = []
        for tx in tx_data.get("transactions", []):
            input_addrs = [
                inp["addr"] for inp in tx.get("inputs", [])
                if inp.get("addr")
            ]
            if len(input_addrs) >= 2:
                clusters.append({
                    "addresses": input_addrs,
                    "tx_hash": tx.get("hash"),
                    "confidence": 0.8,
                    "evidence_basis": tx.get("hash"),
                })
        return clusters


class EthereumAdapter(BaseOSINTAdapter):
    source_type = "crypto_ethereum"

    def is_available(self) -> bool:
        return bool(settings.ETHERSCAN_API_KEY)

    def execute(self, query: str) -> OSINTResult:
        """Fetch Ethereum address transaction history via Etherscan."""
        if not self.is_available():
            return self.unavailable_result(query)
        try:
            url = "https://api.etherscan.io/api"
            params = {
                "module": "account",
                "action": "txlist",
                "address": query,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": 50,
                "sort": "desc",
                "apikey": settings.ETHERSCAN_API_KEY,
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            txs = data.get("result", []) if isinstance(data.get("result"), list) else []
            entities = []
            seen = set()

            for tx in txs:
                counterparty = tx.get("to") if tx.get("from", "").lower() == query.lower() else tx.get("from")
                if counterparty and counterparty not in seen:
                    seen.add(counterparty)
                    entities.append({
                        "entity_type": "crypto_wallet_address",
                        "value": counterparty,
                        "confidence": 0.5,
                    })

            return OSINTResult(
                source_type=self.source_type, query=query,
                raw_result={"transactions": txs[:50]},
                extracted_entities=entities,
            )
        except Exception as e:
            return OSINTResult(
                source_type=self.source_type, query=query,
                raw_result={}, extracted_entities=[], error=str(e),
            )
