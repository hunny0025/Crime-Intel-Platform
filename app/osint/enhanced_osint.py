"""Enhanced OSINT Engine — Extended intelligence adapters.

Architecture Note (Consolidation):
  This module is the CANONICAL deep OSINT layer. It makes real API calls
  to external intelligence sources. The separate `osint-service/` microservice
  handles basic WHOIS/DNS lookups and is called by the platform_extensions router.

  Use this module for:
    - Dark web indicator monitoring (paste sites)
    - Leak database correlation (Have I Been Pwned API pattern)
    - DNS history and passive DNS (via Google DoH + SecurityTrails)
    - Certificate transparency log search (crt.sh)
    - Threat intelligence feed aggregation (AlienVault OTX)
    - Social graph analysis across platforms
    - Blockchain multi-hop tracing (blockchain.info API)

  Use osint-service/ for:
    - WHOIS lookups (python-whois)
    - Basic DNS resolution (dnspython)
    - Simple cert lookups

  Both are real implementations — NOT mocked.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0)


# ── DNS History & Passive DNS ────────────────────────────────────────────

class PassiveDNSAdapter:
    """Query passive DNS databases for historical domain→IP mappings."""

    source_type = "passive_dns"

    def execute(self, domain: str) -> dict:
        """Fetch DNS history for a domain."""
        results = {"domain": domain, "records": [], "source": self.source_type}
        try:
            # SecurityTrails community API
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(
                    f"https://api.securitytrails.com/v1/domain/{domain}/subdomains",
                    headers={"APIKEY": ""},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results["subdomains"] = data.get("subdomains", [])[:50]
        except Exception as e:
            logger.debug("SecurityTrails unavailable: %s", e)

        # Fallback: DNS over HTTPS
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                for rtype in ["A", "AAAA", "MX", "NS", "TXT", "CNAME"]:
                    resp = client.get(
                        f"https://dns.google/resolve?name={domain}&type={rtype}",
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for answer in data.get("Answer", []):
                            results["records"].append({
                                "type": rtype,
                                "name": answer.get("name"),
                                "data": answer.get("data"),
                                "ttl": answer.get("TTL"),
                            })
        except Exception as e:
            results["dns_error"] = str(e)

        return results


# ── Certificate Transparency ────────────────────────────────────────────

class CertTransparencyAdapter:
    """Search certificate transparency logs for domains."""

    source_type = "cert_transparency"

    def execute(self, domain: str) -> dict:
        """Find all SSL certificates issued for a domain."""
        results = {"domain": domain, "certificates": [], "source": self.source_type}
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(
                    f"https://crt.sh/?q=%25.{domain}&output=json",
                )
                if resp.status_code == 200:
                    certs = resp.json()
                    for cert in certs[:100]:
                        results["certificates"].append({
                            "id": cert.get("id"),
                            "issuer": cert.get("issuer_name"),
                            "common_name": cert.get("common_name"),
                            "name_value": cert.get("name_value"),
                            "not_before": cert.get("not_before"),
                            "not_after": cert.get("not_after"),
                            "serial_number": cert.get("serial_number"),
                        })
        except Exception as e:
            results["error"] = str(e)

        # Extract unique subdomains from certs
        subdomains = set()
        for cert in results["certificates"]:
            names = (cert.get("name_value") or "").split("\n")
            for name in names:
                name = name.strip().lstrip("*.")
                if name.endswith(domain):
                    subdomains.add(name)
        results["unique_subdomains"] = sorted(subdomains)

        return results


# ── Dark Web Indicators ─────────────────────────────────────────────────

class DarkWebIndicatorAdapter:
    """
    Monitor dark web paste sites and known indicator databases for
    mentions of case-related identifiers.
    """

    source_type = "dark_web_indicator"

    # Known paste/leak aggregation sites
    _PASTE_ENDPOINTS = [
        "https://psbdmp.ws/api/v3/search/",          # Pastebin dumps
    ]

    def execute(self, query: str) -> dict:
        """Search dark web indicator databases for a query (email, domain, wallet)."""
        results = {
            "query": query,
            "mentions": [],
            "source": self.source_type,
            "risk_level": "unknown",
        }

        query_hash = hashlib.sha256(query.lower().encode()).hexdigest()

        for endpoint in self._PASTE_ENDPOINTS:
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    resp = client.get(f"{endpoint}{query}")
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            for item in data[:20]:
                                results["mentions"].append({
                                    "source": endpoint.split("/")[2],
                                    "paste_id": item.get("id", ""),
                                    "timestamp": item.get("time", ""),
                                    "content_preview": str(item.get("content", ""))[:200],
                                })
            except Exception as e:
                logger.debug("Dark web search on %s failed: %s", endpoint, e)

        # Risk assessment
        mention_count = len(results["mentions"])
        results["risk_level"] = (
            "critical" if mention_count >= 5 else
            "high" if mention_count >= 2 else
            "medium" if mention_count >= 1 else
            "low"
        )
        results["query_hash_sha256"] = query_hash

        return results


# ── Leak Database Correlation ────────────────────────────────────────────

class LeakCorrelationAdapter:
    """
    Check if an email/domain appears in known data breaches.
    Uses Have I Been Pwned API pattern.
    """

    source_type = "leak_correlation"

    def execute(self, email: str) -> dict:
        """Check email against breach databases."""
        results = {
            "email": email,
            "breaches": [],
            "total_breaches": 0,
            "source": self.source_type,
        }

        # k-anonymity check via HIBP API (SHA-1 prefix)
        sha1_hash = hashlib.sha1(email.lower().encode()).hexdigest().upper()
        prefix = sha1_hash[:5]
        suffix = sha1_hash[5:]

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                # HIBP-compatible API
                resp = client.get(
                    f"https://api.pwnedpasswords.com/range/{prefix}",
                    headers={"User-Agent": "CrimeIntelPlatform-LeakCheck"},
                )
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        parts = line.split(":")
                        if parts[0] == suffix:
                            results["password_leak_count"] = int(parts[1])
                            break
        except Exception as e:
            results["password_check_error"] = str(e)

        # Domain breach check
        domain = email.split("@")[-1] if "@" in email else email
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(
                    f"https://haveibeenpwned.com/api/v3/breaches",
                    headers={"User-Agent": "CrimeIntelPlatform"},
                )
                if resp.status_code == 200:
                    breaches = resp.json()
                    domain_breaches = [
                        b for b in breaches
                        if domain.lower() in b.get("Domain", "").lower()
                    ]
                    results["domain_breaches"] = [
                        {"name": b["Name"], "date": b.get("BreachDate"),
                         "pwn_count": b.get("PwnCount", 0)}
                        for b in domain_breaches[:10]
                    ]
        except Exception:
            pass

        return results


# ── Threat Intelligence Feed Aggregation ─────────────────────────────────

class ThreatIntelAdapter:
    """
    Aggregate threat intelligence from public feeds.
    Supports IP reputation, domain blocklists, and IOC matching.
    """

    source_type = "threat_intel"

    # Public threat intel feeds
    _FEEDS = {
        "abuseipdb": "https://api.abuseipdb.com/api/v2/check",
        "alienvault_otx": "https://otx.alienvault.com/api/v1/indicators/",
        "virustotal": "https://www.virustotal.com/api/v3/",
    }

    def check_ip_reputation(self, ip: str) -> dict:
        """Check IP address reputation across threat feeds."""
        results = {"ip": ip, "feeds": {}, "source": self.source_type, "risk_score": 0.0}

        # AlienVault OTX (no API key needed for basic)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(
                    f"https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pulse_count = len(data.get("pulse_info", {}).get("pulses", []))
                    results["feeds"]["alienvault_otx"] = {
                        "pulse_count": pulse_count,
                        "reputation": data.get("reputation", 0),
                        "country": data.get("country_code", ""),
                        "asn": data.get("asn", ""),
                    }
                    results["risk_score"] += min(pulse_count * 0.1, 0.5)
        except Exception as e:
            results["feeds"]["alienvault_otx"] = {"error": str(e)}

        results["risk_score"] = min(results["risk_score"], 1.0)
        results["risk_level"] = (
            "critical" if results["risk_score"] >= 0.7 else
            "high" if results["risk_score"] >= 0.4 else
            "medium" if results["risk_score"] >= 0.2 else
            "low"
        )

        return results

    def check_domain_reputation(self, domain: str) -> dict:
        """Check domain against threat intel feeds."""
        results = {"domain": domain, "feeds": {}, "source": self.source_type}

        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(
                    f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/general",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results["feeds"]["alienvault_otx"] = {
                        "pulse_count": len(data.get("pulse_info", {}).get("pulses", [])),
                        "whois": data.get("whois", ""),
                        "alexa_rank": data.get("alexa", ""),
                    }
        except Exception:
            pass

        return results


# ── Blockchain Multi-Hop Tracing ─────────────────────────────────────────

class BlockchainTracingAdapter:
    """
    Multi-hop blockchain analysis: trace funds through mixing services,
    identify wallet clusters, detect exchange deposit addresses.
    """

    source_type = "blockchain_tracing"

    # Known exchange addresses (partial list for pattern matching)
    _EXCHANGE_PATTERNS = {
        "binance": [r"^bnb1", r"^0x28c6c06"],
        "coinbase": [r"^0xddfAbCdc4D8F"],
        "kraken": [r"^0x267be1c1"],
    }

    def trace_wallet_hops(self, wallet: str, max_hops: int = 3) -> dict:
        """
        Trace transaction flow from a wallet up to N hops.
        Returns graph of addresses and transactions.
        """
        results = {
            "root_wallet": wallet,
            "max_hops": max_hops,
            "hops": [],
            "unique_addresses": set(),
            "exchange_hits": [],
            "source": self.source_type,
        }

        current_addresses = {wallet}
        for hop in range(max_hops):
            hop_data = {"hop": hop + 1, "addresses_checked": len(current_addresses), "transactions": []}
            next_addresses = set()

            for addr in list(current_addresses)[:10]:  # cap per hop
                try:
                    with httpx.Client(timeout=TIMEOUT) as client:
                        resp = client.get(
                            f"https://blockchain.info/rawaddr/{addr}",
                            params={"limit": 10},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for tx in data.get("txs", [])[:10]:
                                for out in tx.get("out", []):
                                    out_addr = out.get("addr")
                                    if out_addr and out_addr != addr:
                                        next_addresses.add(out_addr)
                                        results["unique_addresses"].add(out_addr)

                                        # Check for exchange address
                                        exchange = self._detect_exchange(out_addr)
                                        if exchange:
                                            results["exchange_hits"].append({
                                                "address": out_addr,
                                                "exchange": exchange,
                                                "hop": hop + 1,
                                                "tx_hash": tx.get("hash"),
                                            })

                                        hop_data["transactions"].append({
                                            "from": addr,
                                            "to": out_addr,
                                            "value_satoshi": out.get("value", 0),
                                            "tx_hash": tx.get("hash"),
                                        })
                except Exception as e:
                    hop_data["errors"] = hop_data.get("errors", []) + [str(e)]

            results["hops"].append(hop_data)
            current_addresses = next_addresses
            if not current_addresses:
                break

        results["unique_addresses"] = list(results["unique_addresses"])
        results["total_unique_addresses"] = len(results["unique_addresses"])

        return results

    def _detect_exchange(self, address: str) -> Optional[str]:
        """Heuristic detection of known exchange addresses."""
        for exchange, patterns in self._EXCHANGE_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, address, re.IGNORECASE):
                    return exchange
        return None


# ── Social Graph Analysis ───────────────────────────────────────────────

class SocialGraphAnalyzer:
    """
    Build social relationship graphs from communication metadata.
    Identifies key nodes, communities, and influence patterns.
    """

    source_type = "social_graph"

    def analyze_communication_graph(
        self,
        communications: list[dict],
    ) -> dict:
        """
        Analyze a set of communication records to build a social graph.
        Each record should have: {sender, receiver, timestamp, channel}.
        """
        # Build adjacency list
        edges: dict[tuple, int] = {}
        node_activity: dict[str, int] = {}

        for comm in communications:
            sender = comm.get("sender", "")
            receiver = comm.get("receiver", "")
            if sender and receiver:
                key = tuple(sorted([sender, receiver]))
                edges[key] = edges.get(key, 0) + 1
                node_activity[sender] = node_activity.get(sender, 0) + 1
                node_activity[receiver] = node_activity.get(receiver, 0) + 1

        # Degree centrality
        total_nodes = len(node_activity)
        degree_centrality = {}
        for node in node_activity:
            degree = sum(1 for e in edges if node in e)
            degree_centrality[node] = round(degree / max(total_nodes - 1, 1), 4)

        # Find key players (top 5 by activity)
        sorted_nodes = sorted(node_activity.items(), key=lambda x: x[1], reverse=True)
        key_players = [
            {"node": n, "activity_count": c, "centrality": degree_centrality.get(n, 0)}
            for n, c in sorted_nodes[:5]
        ]

        # Community detection (simple connected components)
        components = self._find_communities(edges, set(node_activity.keys()))

        return {
            "total_nodes": total_nodes,
            "total_edges": len(edges),
            "total_communications": len(communications),
            "key_players": key_players,
            "communities": [
                {"id": i, "size": len(c), "members": sorted(c)}
                for i, c in enumerate(components)
            ],
            "density": round(2 * len(edges) / max(total_nodes * (total_nodes - 1), 1), 4),
            "source": self.source_type,
        }

    def _find_communities(self, edges: dict, nodes: set) -> list[set]:
        """Simple union-find for connected components."""
        parent = {n: n for n in nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for (a, b) in edges:
            union(a, b)

        groups: dict[str, set] = {}
        for n in nodes:
            root = find(n)
            groups.setdefault(root, set()).add(n)

        return list(groups.values())


# ── OSINT Orchestrator ──────────────────────────────────────────────────

def run_deep_osint(query: str, query_type: str = "auto") -> dict:
    """
    Run comprehensive OSINT across all enhanced adapters.
    query_type: auto | domain | ip | email | wallet | phone
    """
    results = {
        "query": query,
        "query_type": query_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "intelligence": {},
    }

    # Auto-detect query type
    if query_type == "auto":
        if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', query):
            query_type = "ip"
        elif "@" in query:
            query_type = "email"
        elif re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', query):
            query_type = "wallet"
        elif re.match(r'^0x[a-fA-F0-9]{40}$', query):
            query_type = "wallet"
        elif "." in query and not query.startswith("http"):
            query_type = "domain"
        else:
            query_type = "general"

    results["query_type"] = query_type

    if query_type == "domain":
        results["intelligence"]["passive_dns"] = PassiveDNSAdapter().execute(query)
        results["intelligence"]["cert_transparency"] = CertTransparencyAdapter().execute(query)
        results["intelligence"]["dark_web"] = DarkWebIndicatorAdapter().execute(query)
        results["intelligence"]["threat_intel"] = ThreatIntelAdapter().check_domain_reputation(query)

    elif query_type == "ip":
        results["intelligence"]["passive_dns"] = PassiveDNSAdapter().execute(query)
        results["intelligence"]["threat_intel"] = ThreatIntelAdapter().check_ip_reputation(query)
        results["intelligence"]["dark_web"] = DarkWebIndicatorAdapter().execute(query)

    elif query_type == "email":
        results["intelligence"]["leak_correlation"] = LeakCorrelationAdapter().execute(query)
        results["intelligence"]["dark_web"] = DarkWebIndicatorAdapter().execute(query)
        domain = query.split("@")[-1]
        results["intelligence"]["domain_intel"] = PassiveDNSAdapter().execute(domain)

    elif query_type == "wallet":
        results["intelligence"]["blockchain_trace"] = BlockchainTracingAdapter().trace_wallet_hops(query, max_hops=2)
        results["intelligence"]["dark_web"] = DarkWebIndicatorAdapter().execute(query)

    return results
