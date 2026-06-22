"""Tests for Domain Intelligence adapters (Prompt 17).

Uses mocked HTTP responses — does NOT depend on live external services.
"""

import json
import uuid
from unittest.mock import patch, MagicMock

import pytest
from app.adapters.whois_adapter import WhoisAdapter
from app.adapters.dns_adapter import DNSAdapter
from app.adapters.crt_sh_adapter import CrtShAdapter


class TestWhoisAdapter:
    def test_whois_extracts_entities(self):
        """WHOIS lookup extracts registrant org and email."""
        adapter = WhoisAdapter()
        assert adapter.is_available()

        # Mock the whois library
        mock_whois_result = MagicMock()
        mock_whois_result.domain_name = "example.com"
        mock_whois_result.registrar = "Test Registrar Inc."
        mock_whois_result.org = "Example Organization"
        mock_whois_result.emails = ["admin@example.com", "tech@example.com"]
        mock_whois_result.name = "John Doe"
        mock_whois_result.creation_date = "2020-01-01"
        mock_whois_result.expiration_date = "2025-01-01"
        # Set all other attributes to None
        for attr in ["whois_server", "updated_date", "address", "city",
                      "state", "zipcode", "country", "name_servers", "status", "dnssec"]:
            setattr(mock_whois_result, attr, None)

        with patch("app.adapters.whois_adapter.whois") as mock_whois:
            mock_whois.whois.return_value = mock_whois_result
            result = adapter.execute("example.com")

        assert result.error is None
        assert result.source_type == "whois"
        assert result.raw_result.get("org") == "Example Organization"

        # Should extract org and emails
        entity_types = {e["entity_type"] for e in result.extracted_entities}
        assert "organization" in entity_types
        assert "email" in entity_types
        assert result.classification_tag == "public_osint"

    def test_whois_handles_redacted(self):
        """WHOIS with GDPR-redacted fields doesn't extract redacted data."""
        adapter = WhoisAdapter()
        mock_result = MagicMock()
        mock_result.org = "REDACTED"
        mock_result.emails = "redacted@privacy.net"
        mock_result.registrar = "Some Registrar"
        for attr in ["domain_name", "whois_server", "creation_date", "expiration_date",
                      "updated_date", "name", "address", "city", "state", "zipcode",
                      "country", "name_servers", "status", "dnssec"]:
            setattr(mock_result, attr, None)

        with patch("app.adapters.whois_adapter.whois") as mock_whois:
            mock_whois.whois.return_value = mock_result
            result = adapter.execute("redacted.com")

        # Redacted org/email should NOT appear as entities
        org_entities = [e for e in result.extracted_entities if e["entity_type"] == "organization"]
        assert len(org_entities) == 0


class TestDNSAdapter:
    def test_dns_extracts_ips(self):
        """DNS lookup extracts A record IPs."""
        adapter = DNSAdapter()
        assert adapter.is_available()

        # Mock dns.resolver
        mock_a_answer = [MagicMock(__str__=lambda s: "93.184.216.34")]
        mock_mx_answer = [MagicMock(__str__=lambda s: "10 mail.example.com", exchange=MagicMock(__str__=lambda s: "mail.example.com."))]
        mock_ns_answer = [MagicMock(__str__=lambda s: "ns1.example.com.")]

        import dns.resolver
        import dns.exception

        def mock_resolve(domain, rtype):
            if rtype == "A":
                return mock_a_answer
            if rtype == "MX":
                return mock_mx_answer
            if rtype == "NS":
                return mock_ns_answer
            raise dns.resolver.NoAnswer()

        with patch("app.adapters.dns_adapter.dns.resolver.resolve", side_effect=mock_resolve):
            result = adapter.execute("example.com")

        assert result.error is None
        assert "A" in result.raw_result
        ip_entities = [e for e in result.extracted_entities if e["entity_type"] == "ip_address"]
        assert len(ip_entities) >= 1
        assert ip_entities[0]["value"] == "93.184.216.34"


class TestCrtShAdapter:
    def test_crt_sh_extracts_sans(self):
        """Certificate transparency extracts Subject Alternative Names."""
        adapter = CrtShAdapter()
        assert adapter.is_available()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "issuer_ca_id": 1,
                "issuer_name": "Let's Encrypt",
                "common_name": "example.com",
                "name_value": "example.com\nwww.example.com\napi.example.com",
                "not_before": "2024-01-01",
                "not_after": "2025-01-01",
            },
            {
                "issuer_ca_id": 2,
                "issuer_name": "Let's Encrypt",
                "common_name": "example.com",
                "name_value": "mail.example.com\nstaging.example.com",
                "not_before": "2024-06-01",
                "not_after": "2025-06-01",
            },
        ]

        with patch("app.adapters.crt_sh_adapter.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = adapter.execute("example.com")

        assert result.error is None
        domain_entities = [e for e in result.extracted_entities if e["entity_type"] == "related_domain"]
        domain_values = {e["value"] for e in domain_entities}
        assert "www.example.com" in domain_values
        assert "api.example.com" in domain_values
        assert "mail.example.com" in domain_values
        # The queried domain itself should NOT appear as a related domain
        assert "example.com" not in domain_values


class TestOSINTRecordStorage:
    def test_raw_result_preserved(self):
        """OSINTRecords preserve raw_result for audit."""
        adapter = WhoisAdapter()
        mock_result = MagicMock()
        mock_result.domain_name = "test.com"
        mock_result.org = "Test Corp"
        mock_result.registrar = "TestReg"
        mock_result.emails = None
        for attr in ["whois_server", "creation_date", "expiration_date",
                      "updated_date", "name", "address", "city", "state",
                      "zipcode", "country", "name_servers", "status", "dnssec"]:
            setattr(mock_result, attr, None)

        with patch("app.adapters.whois_adapter.whois") as mock_whois:
            mock_whois.whois.return_value = mock_result
            result = adapter.execute("test.com")

        assert isinstance(result.raw_result, dict)
        assert result.raw_result.get("org") == "Test Corp"
        assert result.record_id  # UUID assigned
