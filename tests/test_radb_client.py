"""Tests for the IRR API client."""

import pytest
from unittest.mock import Mock, patch, MagicMock

import requests

from app.radb_client import RADBClient, RADBAPIError, PrefixResult


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

    @patch.object(RADBClient, '_query_ripe_rest')
    def test_execute_query_other_source(self, mock_query):
        """Test execute_query routes other sources through RIPE API."""
        mock_query.return_value = ({"8.8.8.0/24"}, set())

        client = RADBClient()
        v4, v6 = client._execute_query("AS15169", "RADB")

        # Should call RIPE API with lowercase source
        mock_query.assert_called_once_with("AS15169", source_lower="radb")

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
