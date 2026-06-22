"""DNS record adapter — resolves A/AAAA/MX/TXT/NS records via public DNS."""

import logging
from app.adapters.base import BaseOSINTAdapter, OSINTResult

logger = logging.getLogger(__name__)


class DNSAdapter(BaseOSINTAdapter):
    source_type = "dns"

    def is_available(self) -> bool:
        return True  # DNS resolution requires no credentials

    def execute(self, query: str) -> OSINTResult:
        try:
            import dns.resolver

            raw = {}
            entities = []
            record_types = ["A", "AAAA", "MX", "TXT", "NS"]

            for rtype in record_types:
                try:
                    answers = dns.resolver.resolve(query, rtype)
                    records = []
                    for rdata in answers:
                        record_str = str(rdata).strip('"')
                        records.append(record_str)

                        # Extract entities from specific record types
                        if rtype == "A":
                            entities.append({
                                "entity_type": "ip_address",
                                "value": record_str,
                                "confidence": 0.8,
                            })
                        elif rtype == "AAAA":
                            entities.append({
                                "entity_type": "ip_address_v6",
                                "value": record_str,
                                "confidence": 0.8,
                            })
                        elif rtype == "MX":
                            # MX records include priority
                            mx_host = str(rdata.exchange).rstrip(".")
                            entities.append({
                                "entity_type": "mail_server",
                                "value": mx_host,
                                "confidence": 0.8,
                            })
                        elif rtype == "NS":
                            ns_host = record_str.rstrip(".")
                            entities.append({
                                "entity_type": "nameserver",
                                "value": ns_host,
                                "confidence": 0.8,
                            })

                    raw[rtype] = records
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                        dns.resolver.NoNameservers, dns.exception.Timeout):
                    raw[rtype] = []
                except Exception as e:
                    raw[rtype] = [f"error: {e}"]

            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result=raw,
                extracted_entities=entities,
            )
        except Exception as e:
            logger.warning("DNS lookup failed for %s: %s", query, e)
            return OSINTResult(
                source_type=self.source_type,
                query=query,
                raw_result={},
                extracted_entities=[],
                error=str(e),
            )
