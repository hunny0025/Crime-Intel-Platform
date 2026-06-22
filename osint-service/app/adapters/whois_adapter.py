"""WHOIS lookup adapter — extracts registrant info from domain WHOIS records.

Post-GDPR many TLDs return redacted data; this adapter handles gracefully
by extracting whatever is available and noting redacted fields.
"""

import logging
from app.adapters.base import BaseOSINTAdapter, OSINTResult

logger = logging.getLogger(__name__)


class WhoisAdapter(BaseOSINTAdapter):
    source_type = "whois"

    def is_available(self) -> bool:
        # WHOIS doesn't require API keys — always available
        return True

    def execute(self, query: str) -> OSINTResult:
        try:
            import whois
            w = whois.whois(query)
            raw = {}
            if w:
                # whois returns a WhoisEntry object; convert to dict
                for key in ["domain_name", "registrar", "whois_server",
                            "creation_date", "expiration_date", "updated_date",
                            "name", "org", "address", "city", "state",
                            "zipcode", "country", "emails", "name_servers",
                            "status", "dnssec"]:
                    val = getattr(w, key, None)
                    if val is not None:
                        # Convert dates to strings
                        if isinstance(val, list):
                            raw[key] = [str(v) for v in val]
                        else:
                            raw[key] = str(val)

            entities = []
            # Extract registrant org
            if raw.get("org") and raw["org"].lower() not in ("redacted", "data protected"):
                entities.append({
                    "entity_type": "organization",
                    "value": raw["org"],
                    "confidence": 0.5,
                })
            # Extract registrant email
            emails = raw.get("emails")
            if emails:
                email_list = emails if isinstance(emails, list) else [emails]
                for email in email_list:
                    if "@" in str(email) and "redacted" not in str(email).lower():
                        entities.append({
                            "entity_type": "email",
                            "value": str(email),
                            "confidence": 0.5,
                        })
            # Extract registrar
            if raw.get("registrar"):
                entities.append({
                    "entity_type": "registrar",
                    "value": raw["registrar"],
                    "confidence": 0.8,
                })

            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result=raw,
                extracted_entities=entities,
            )
        except Exception as e:
            logger.warning("WHOIS lookup failed for %s: %s", query, e)
            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result={},
                extracted_entities=[],
                error=str(e),
            )
