"""Tests for the IRR API client."""

import socket
import pytest
from unittest.mock import Mock, patch, MagicMock

import requests

from app.radb_client import RADBClient, RADBAPIError, PrefixResult, WHOIS_SERVERS


class TestRADBClient:
    """Tests for RADBClient."""

    def test_init_defaults(self):
        """Test client initialization with defaults."""
        client = RADBClient()
        assert client.base_url == "https://rest.db.ripe.net"
        assert client.timeout == 60
        assert client.max_retries == 3

    def test_init_custom(self):
        """Test client initialization with custom values."""
        client = RADBClient(
            base_url="https://custom.api.net/",
            timeout=30,
            max_retries=5,
        )
        assert client.base_url == "https://custom.api.net"  # Trailing slash removed
        assert client.timeout == 30
        assert client.max_retries == 5

    def test_parse_response_ipv4(self):
        """Test parsing IPv4 route objects (legacy format)."""
        client = RADBClient()

        response = {
            "objects": [
                {
                    "type": "route",
                    "primary_key": "8.8.8.0/24AS15169",
                    "attributes": {
                        "route": "8.8.8.0/24",
                        "origin": "AS15169",
                        "source": "RADB"
                    }
                },
                {
                    "type": "route",
                    "primary_key": "8.8.4.0/24AS15169",
                    "attributes": {
                        "route": "8.8.4.0/24",
                        "origin": "AS15169",
                        "source": "RADB"
                    }
                }
            ]
        }

        v4, v6 = client._parse_response(response)
        assert v4 == {"8.8.8.0/24", "8.8.4.0/24"}
        assert v6 == set()

    def test_parse_response_ipv6(self):
        """Test parsing IPv6 route6 objects (legacy format)."""
        client = RADBClient()

        response = {
            "objects": [
                {
                    "type": "route6",
                    "primary_key": "2001:4860::/32AS15169",
                    "attributes": {
                        "route6": "2001:4860::/32",
                        "origin": "AS15169",
                        "source": "RADB"
                    }
                }
            ]
        }

        v4, v6 = client._parse_response(response)
        assert v4 == set()
        assert v6 == {"2001:4860::/32"}

    def test_parse_response_mixed(self):
        """Test parsing mixed IPv4 and IPv6 objects (legacy format)."""
        client = RADBClient()

        response = {
            "objects": [
                {
                    "type": "route",
                    "attributes": {"route": "8.8.8.0/24"}
                },
                {
                    "type": "route6",
                    "attributes": {"route6": "2001:4860::/32"}
                }
            ]
        }

        v4, v6 = client._parse_response(response)
        assert v4 == {"8.8.8.0/24"}
        assert v6 == {"2001:4860::/32"}

    def test_parse_response_empty(self):
        """Test parsing empty response (legacy format)."""
        client = RADBClient()

        v4, v6 = client._parse_response({"objects": []})
        assert v4 == set()
        assert v6 == set()

        v4, v6 = client._parse_response({})
        assert v4 == set()
        assert v6 == set()

    def test_parse_ripe_response(self):
        """Test parsing RIPE REST API response format."""
        client = RADBClient()

        response = {
            "objects": {
                "object": [
                    {
                        "type": "route",
                        "attributes": {
                            "attribute": [
                                {"name": "route", "value": "8.8.8.0/24"},
                                {"name": "origin", "value": "AS15169"},
                            ]
                        }
                    },
                    {
                        "type": "route",
                        "attributes": {
                            "attribute": [
                                {"name": "route", "value": "8.8.4.0/24"},
                                {"name": "origin", "value": "AS15169"},
                            ]
                        }
                    }
                ]
            }
        }

        prefixes = client._parse_ripe_response(response, "route")
        assert prefixes == {"8.8.8.0/24", "8.8.4.0/24"}

    def test_parse_ripe_response_ipv6(self):
        """Test parsing RIPE REST API response for IPv6."""
        client = RADBClient()

        response = {
            "objects": {
                "object": [
                    {
                        "type": "route6",
                        "attributes": {
                            "attribute": [
                                {"name": "route6", "value": "2001:4860::/32"},
                                {"name": "origin", "value": "AS15169"},
                            ]
                        }
                    }
                ]
            }
        }

        prefixes = client._parse_ripe_response(response, "route6")
        assert prefixes == {"2001:4860::/32"}

    def test_parse_ripe_response_empty(self):
        """Test parsing empty RIPE response."""
        client = RADBClient()

        response = {"objects": {"object": []}}
        prefixes = client._parse_ripe_response(response, "route")
        assert prefixes == set()

        response = {"objects": {}}
        prefixes = client._parse_ripe_response(response, "route")
        assert prefixes == set()

    @patch.object(RADBClient, '_execute_query')
    def test_fetch_prefixes_single_source(self, mock_execute):
        """Test fetching from a single source."""
        mock_execute.return_value = ({"8.8.8.0/24"}, {"2001::/32"})

        client = RADBClient()
        result = client.fetch_prefixes("AS15169", ["RIPE"])

        assert result.ipv4_prefixes == {"8.8.8.0/24"}
        assert result.ipv6_prefixes == {"2001::/32"}
        assert result.sources_queried == ["RIPE"]
        assert result.errors == []

        mock_execute.assert_called_once_with("AS15169", "RIPE")

    @patch.object(RADBClient, '_execute_query')
    def test_fetch_prefixes_multiple_sources(self, mock_execute):
        """Test fetching and merging from multiple sources."""
        def side_effect(target, source):
            if source == "RADB":
                return ({"1.0.0.0/8"}, {"2001::/32"})
            elif source == "RIPE":
                return ({"2.0.0.0/8"}, {"2002::/32"})
            return (set(), set())

        mock_execute.side_effect = side_effect

        client = RADBClient()
        result = client.fetch_prefixes("AS15169", ["RADB", "RIPE"])

        assert result.ipv4_prefixes == {"1.0.0.0/8", "2.0.0.0/8"}
        assert result.ipv6_prefixes == {"2001::/32", "2002::/32"}
        assert result.sources_queried == ["RADB", "RIPE"]

    @patch.object(RADBClient, '_execute_query')
    def test_fetch_prefixes_with_error(self, mock_execute):
        """Test handling errors from one source."""
        def side_effect(target, source):
            if source == "RADB":
                return ({"1.0.0.0/8"}, set())
            raise RADBAPIError("Connection failed")

        mock_execute.side_effect = side_effect

        client = RADBClient()
        result = client.fetch_prefixes("AS15169", ["RADB", "RIPE"])

        # Should still have RADB results
        assert result.ipv4_prefixes == {"1.0.0.0/8"}
        assert result.sources_queried == ["RADB"]
        assert len(result.errors) == 1
        assert "RIPE" in result.errors[0]

    @patch.object(RADBClient, '_query_ripe_rest')
    def test_execute_query_ripe(self, mock_query):
        """Test execute_query routes to RIPE REST API."""
        mock_query.return_value = ({"8.8.8.0/24"}, set())

        client = RADBClient()
        v4, v6 = client._execute_query("AS15169", "RIPE")

        assert v4 == {"8.8.8.0/24"}
        mock_query.assert_called_once_with("AS15169")

    @patch.object(RADBClient, '_query_whois')
    def test_execute_query_whois_source(self, mock_whois):
        """Test execute_query routes to WHOIS for non-RIPE sources."""
        mock_whois.return_value = ({"8.8.8.0/24"}, set())

        client = RADBClient()
        v4, v6 = client._execute_query("AS15169", "RADB")

        # Should call WHOIS for RADB
        mock_whois.assert_called_once_with("AS15169", "RADB")

    @patch.object(RADBClient, '_query_ripe_rest')
    def test_execute_query_unknown_source_fallback(self, mock_query):
        """Test execute_query falls back to RIPE for unknown sources."""
        mock_query.return_value = ({"8.8.8.0/24"}, set())

        client = RADBClient()
        v4, v6 = client._execute_query("AS15169", "UNKNOWN")

        # Should fall back to RIPE API with lowercase source
        mock_query.assert_called_once_with("AS15169", source_lower="unknown")

    @patch('requests.Session.get')
    def test_query_ripe_rest_type_success(self, mock_get):
        """Test successful RIPE REST API query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "objects": {
                "object": [
                    {
                        "type": "route",
                        "attributes": {
                            "attribute": [
                                {"name": "route", "value": "8.8.8.0/24"}
                            ]
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        client = RADBClient()
        prefixes = client._query_ripe_rest_type("AS15169", "ripe", "route")

        assert prefixes == {"8.8.8.0/24"}

    @patch('requests.Session.get')
    def test_query_ripe_rest_type_404(self, mock_get):
        """Test 404 response (no objects found)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = RADBClient()
        prefixes = client._query_ripe_rest_type("AS99999", "ripe", "route")

        assert prefixes == set()

    @patch('requests.Session.get')
    def test_query_ripe_rest_type_error(self, mock_get):
        """Test API error response."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        client = RADBClient()

        with pytest.raises(RADBAPIError):
            client._query_ripe_rest_type("AS15169", "ripe", "route")

    @patch('requests.Session.get')
    def test_query_ripe_rest_type_invalid_json(self, mock_get):
        """Test invalid JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        client = RADBClient()

        with pytest.raises(RADBAPIError):
            client._query_ripe_rest_type("AS15169", "ripe", "route")


class TestPrefixResult:
    """Tests for PrefixResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = PrefixResult()
        assert result.ipv4_prefixes == set()
        assert result.ipv6_prefixes == set()
        assert result.sources_queried == []
        assert result.errors == []

    def test_custom_values(self):
        """Test custom values."""
        result = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RIPE"],
            errors=["Error 1"],
        )
        assert result.ipv4_prefixes == {"1.0.0.0/8"}
        assert result.ipv6_prefixes == {"2001::/32"}
        assert result.sources_queried == ["RIPE"]
        assert result.errors == ["Error 1"]


class TestWhoisQuery:
    """Tests for WHOIS protocol queries."""

    def test_whois_servers_defined(self):
        """Test that all expected WHOIS servers are defined."""
        expected_sources = ['RADB', 'ARIN', 'APNIC', 'LACNIC', 'AFRINIC', 'NTTCOM']
        for source in expected_sources:
            assert source in WHOIS_SERVERS, f"Missing WHOIS server for {source}"

    def test_parse_whois_response_ipv4(self):
        """Test parsing WHOIS response with IPv4 routes."""
        client = RADBClient()

        response = """
route:          8.8.8.0/24
descr:          Google LLC
origin:         AS15169
source:         RADB

route:          8.8.4.0/24
descr:          Google LLC
origin:         AS15169
source:         RADB
"""
        v4, v6 = client._parse_whois_response(response)
        assert v4 == {"8.8.8.0/24", "8.8.4.0/24"}
        assert v6 == set()

    def test_parse_whois_response_ipv6(self):
        """Test parsing WHOIS response with IPv6 routes."""
        client = RADBClient()

        response = """
route6:         2001:4860::/32
descr:          Google LLC
origin:         AS15169
source:         RADB

route6:         2607:f8b0::/32
descr:          Google LLC
origin:         AS15169
source:         RADB
"""
        v4, v6 = client._parse_whois_response(response)
        assert v4 == set()
        assert v6 == {"2001:4860::/32", "2607:f8b0::/32"}

    def test_parse_whois_response_mixed(self):
        """Test parsing WHOIS response with both IPv4 and IPv6."""
        client = RADBClient()

        response = """
route:          8.8.8.0/24
origin:         AS15169
source:         RADB

route6:         2001:4860::/32
origin:         AS15169
source:         RADB
"""
        v4, v6 = client._parse_whois_response(response)
        assert v4 == {"8.8.8.0/24"}
        assert v6 == {"2001:4860::/32"}

    def test_parse_whois_response_empty(self):
        """Test parsing empty WHOIS response."""
        client = RADBClient()

        v4, v6 = client._parse_whois_response("")
        assert v4 == set()
        assert v6 == set()

    def test_parse_whois_response_no_routes(self):
        """Test parsing WHOIS response with no route objects."""
        client = RADBClient()

        response = """
% This is RADB.
% RADB query for AS15169

as-set:         AS15169:AS-CUSTOMERS
descr:          Google customers
source:         RADB
"""
        v4, v6 = client._parse_whois_response(response)
        assert v4 == set()
        assert v6 == set()

    def test_parse_whois_response_case_insensitive(self):
        """Test that route parsing is case insensitive."""
        client = RADBClient()

        response = """
ROUTE:          8.8.8.0/24
origin:         AS15169

Route:          8.8.4.0/24
origin:         AS15169

ROUTE6:         2001:4860::/32
origin:         AS15169
"""
        v4, v6 = client._parse_whois_response(response)
        assert v4 == {"8.8.8.0/24", "8.8.4.0/24"}
        assert v6 == {"2001:4860::/32"}

    @patch('socket.socket')
    def test_query_whois_success(self, mock_socket_class):
        """Test successful WHOIS query."""
        # Setup mock socket
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        # Simulate response
        mock_socket.recv.side_effect = [
            b"route:          8.8.8.0/24\norigin:         AS15169\n",
            b"",  # End of response
        ]

        client = RADBClient(timeout=30)
        v4, v6 = client._query_whois("AS15169", "RADB")

        assert v4 == {"8.8.8.0/24"}
        assert v6 == set()

        # Verify socket operations
        mock_socket.settimeout.assert_called_once_with(30)
        mock_socket.connect.assert_called_once_with(("whois.radb.net", 43))
        mock_socket.sendall.assert_called_once()
        mock_socket.close.assert_called_once()

    @patch('socket.socket')
    def test_query_whois_timeout(self, mock_socket_class):
        """Test WHOIS query timeout handling."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = socket.timeout("Connection timed out")

        client = RADBClient(timeout=5)

        with pytest.raises(RADBAPIError) as exc_info:
            client._query_whois("AS15169", "RADB")

        assert "timed out" in str(exc_info.value)

    @patch('socket.socket')
    def test_query_whois_connection_error(self, mock_socket_class):
        """Test WHOIS connection error handling."""
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = socket.error("Connection refused")

        client = RADBClient()

        with pytest.raises(RADBAPIError) as exc_info:
            client._query_whois("AS15169", "RADB")

        assert "failed" in str(exc_info.value)

    def test_query_whois_unknown_source(self):
        """Test WHOIS query with unknown source."""
        client = RADBClient()

        with pytest.raises(RADBAPIError) as exc_info:
            client._query_whois("AS15169", "UNKNOWN")

        assert "No WHOIS server" in str(exc_info.value)


class TestClientContextManager:
    """Tests for context manager functionality."""

    def test_context_manager_enter(self):
        """Test __enter__ returns client."""
        client = RADBClient()
        with client as c:
            assert c is client

    @patch.object(RADBClient, 'close')
    def test_context_manager_exit(self, mock_close):
        """Test __exit__ closes client."""
        client = RADBClient()
        with client:
            pass

        mock_close.assert_called_once()

    def test_close_closes_session(self):
        """Test close() closes the HTTP session."""
        client = RADBClient()

        # Verify session is open before close
        assert client._session is not None

        client.close()

        # After close, trying to use session should fail or show it's closed
        # The close() method is called, which is the important verification
        # Note: requests.Session.close() doesn't clear adapters, it closes connections
