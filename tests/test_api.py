"""Tests for the FastAPI application."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app
from app.bgpq4_client import PrefixResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_bgpq4_client():
    """Create a mock BGPQ4Client."""
    mock = MagicMock()
    return mock


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_success(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "source" in data


class TestFetchEndpoint:
    """Tests for the /api/v1/fetch endpoint."""

    @patch('api.main.BGPQ4Client')
    def test_fetch_success(self, mock_bgpq4_class, client):
        """Test successful fetch returns prefixes."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8", "2.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RADB"],
            errors=[]
        )
        mock_bgpq4_class.return_value = mock_client

        response = client.post(
            "/api/v1/fetch",
            json={"target": "AS15169"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "AS15169"
        assert len(data["ipv4_prefixes"]) == 2
        assert len(data["ipv6_prefixes"]) == 1
        assert data["ipv4_count"] == 2
        assert data["ipv6_count"] == 1

    def test_fetch_invalid_target(self, client):
        """Test fetch with invalid target format."""
        response = client.post(
            "/api/v1/fetch",
            json={"target": "INVALID_TARGET"}
        )
        assert response.status_code == 422

    @patch('api.main.BGPQ4Client')
    def test_fetch_no_results_with_errors(self, mock_bgpq4_class, client):
        """Test fetch returns 502 when no results and errors present."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes=set(),
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=["Query failed"]
        )
        mock_bgpq4_class.return_value = mock_client

        response = client.post(
            "/api/v1/fetch",
            json={"target": "AS15169"}
        )

        assert response.status_code == 502
        data = response.json()
        assert "error" in data
        assert "detail" in data

    @patch('api.main.BGPQ4Client')
    def test_fetch_partial_results_with_errors(self, mock_bgpq4_class, client):
        """Test fetch returns 200 with partial results even if errors present."""
        # Setup mock - IPv4 succeeded but IPv6 had errors
        mock_client = MagicMock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=["IPv6 lookup failed"]
        )
        mock_bgpq4_class.return_value = mock_client

        response = client.post(
            "/api/v1/fetch",
            json={"target": "AS15169"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ipv4_count"] == 1
        assert data["ipv6_count"] == 0
        assert len(data["errors"]) > 0


class TestPrefixesGetEndpoint:
    """Tests for the /api/v1/prefixes/{target} GET endpoint."""

    @patch('api.main.BGPQ4Client')
    def test_get_prefixes_success(self, mock_bgpq4_class, client):
        """Test GET endpoint successfully retrieves prefixes."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RADB"],
            errors=[]
        )
        mock_bgpq4_class.return_value = mock_client

        response = client.get("/api/v1/prefixes/AS15169")

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "AS15169"
        assert data["ipv4_count"] == 1
        assert data["ipv6_count"] == 1

    def test_get_prefixes_invalid_target(self, client):
        """Test GET endpoint with invalid target."""
        response = client.get("/api/v1/prefixes/INVALID_TARGET")
        assert response.status_code == 422

    def test_get_prefixes_as_set(self, client):
        """Test GET endpoint with AS-SET target."""
        # AS-SETs should be accepted
        response = client.get("/api/v1/prefixes/AS-GOOGLE")
        # Will return 502 because we don't have bgpq4 running, but validation should pass
        # Just checking that the route accepts the format
        assert response.status_code in [200, 502, 500]


class TestTargetValidation:
    """Tests for target validation in request models."""

    def test_valid_asn_formats(self, client):
        """Test that valid ASN formats are accepted."""
        valid_targets = [
            "AS15169",
            "as15169",  # Should be normalized to uppercase
            "AS65000",
        ]

        for target in valid_targets:
            response = client.post(
                "/api/v1/fetch",
                json={"target": target}
            )
            # We don't care about the response status, just that validation passed
            # (it won't be 422 which is validation error)
            assert response.status_code != 422, f"Target {target} failed validation"

    def test_valid_asset_formats(self, client):
        """Test that valid AS-SET formats are accepted."""
        valid_targets = [
            "AS-GOOGLE",
            "as-google",  # Should be normalized to uppercase
            "AS-COGENT-EUROPE",
            "AS-GOOGLE:EXTERN",
        ]

        for target in valid_targets:
            response = client.post(
                "/api/v1/fetch",
                json={"target": target}
            )
            # We don't care about the response status, just that validation passed
            assert response.status_code != 422, f"Target {target} failed validation"

    def test_invalid_target_formats(self, client):
        """Test that invalid target formats are rejected."""
        invalid_targets = [
            "INVALID",
            "AS_GOOGLE",  # Underscore not allowed
            "AS",  # Just AS
            "15169",  # Just number
            "",  # Empty
            "AS-",  # Incomplete AS-SET
        ]

        for target in invalid_targets:
            response = client.post(
                "/api/v1/fetch",
                json={"target": target}
            )
            assert response.status_code == 422, f"Target {target} should have been rejected"
