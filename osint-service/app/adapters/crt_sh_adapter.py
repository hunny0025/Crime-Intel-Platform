"""Certificate Transparency adapter — queries crt.sh for a domain.

Extracts Subject Alternative Names (SANs) from certificates, useful for
discovering related subdomains and domains registered under the same cert.
"""

import logging
import httpx
from app.adapters.base import BaseOSINTAdapter, OSINTResult
from app.config import settings

logger = logging.getLogger(__name__)


class CrtShAdapter(BaseOSINTAdapter):
    source_type = "crt_sh"

    def __init__(self):
        self.base_url = settings.CRT_SH_URL

    def is_available(self) -> bool:
        return True  # crt.sh is public, no auth required

    def execute(self, query: str) -> OSINTResult:
        try:
            url = f"{self.base_url}/?q=%.{query}&output=json"
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                response.raise_for_status()
                certs = response.json()

            # Deduplicate SANs
            seen_domains = set()
            entities = []
            raw_entries = []

            for cert in certs[:200]:  # Cap to avoid huge result sets
                raw_entries.append({
                    "issuer_ca_id": cert.get("issuer_ca_id"),
                    "issuer_name": cert.get("issuer_name"),
                    "common_name": cert.get("common_name"),
                    "name_value": cert.get("name_value"),
                    "not_before": cert.get("not_before"),
                    "not_after": cert.get("not_after"),
                })

                # Extract SANs from name_value (newline-separated)
                name_value = cert.get("name_value", "")
                for san in name_value.split("\n"):
                    san = san.strip().lower()
                    if san and san not in seen_domains and san != query.lower():
                        seen_domains.add(san)
                        entities.append({
                            "entity_type": "related_domain",
                            "value": san,
                            "confidence": 0.5,
                        })

            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result={"certificates": raw_entries, "total_certs": len(certs)},
                extracted_entities=entities,
            )
        except Exception as e:
            logger.warning("crt.sh lookup failed for %s: %s", query, e)
            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result={},
                extracted_entities=[],
                error=str(e),
            )
