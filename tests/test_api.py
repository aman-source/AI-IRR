"""Tests for the FastAPI application."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app
from app.bgpq4_client import PrefixResult
from app.store import SnapshotStore


@pytest.fixture
def client():
    """Create a test client with a mock bgpq4 client injected into app state."""
    mock = MagicMock()
    mock.fetch_prefixes.return_value = PrefixResult(
        ipv4_prefixes=set(),
        ipv6_prefixes=set(),
        sources_queried=["RADB"],
        errors=[],
    )
    app.state.bgpq4_client = mock
    return TestClient(app)


@pytest.fixture
def mock_bgpq4_client(client):
    """Return the mock BGPQ4Client already injected into app state."""
    return app.state.bgpq4_client


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_success(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "sources" in data
        assert isinstance(data["sources"], list)


class TestFetchEndpoint:
    """Tests for the /api/v1/fetch endpoint."""

    def test_fetch_success(self, client, mock_bgpq4_client):
        """Test successful fetch returns prefixes."""
        mock_bgpq4_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8", "2.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RADB"],
            errors=[]
        )

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

    def test_fetch_no_results_with_errors(self, client, mock_bgpq4_client):
        """Test fetch returns 502 when no results and errors present."""
        mock_bgpq4_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes=set(),
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=["Query failed"]
        )

        response = client.post(
            "/api/v1/fetch",
            json={"target": "AS15169"}
        )

        assert response.status_code == 502
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]

    def test_fetch_partial_results_with_errors(self, client, mock_bgpq4_client):
        """Test fetch returns 200 with partial results even if errors present."""
        mock_bgpq4_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=["IPv6 lookup failed"]
        )

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

    def test_get_prefixes_success(self, client, mock_bgpq4_client):
        """Test GET endpoint successfully retrieves prefixes."""
        mock_bgpq4_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RADB"],
            errors=[]
        )

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


@pytest.fixture
def test_client():
    """Create a TestClient that triggers the lifespan (store initialised via :memory: DB)."""
    with patch("api.main.settings") as mock_settings:
        # Provide all settings attributes used during lifespan
        mock_settings.bgpq4_cmd_list = ["echo"]
        mock_settings.bgpq4_timeout = 10
        mock_settings.bgpq4_sources_list = ["RADB"]
        mock_settings.bgpq4_aggregate = True
        mock_settings.log_level = "INFO"
        mock_settings.cors_origins = "*"
        mock_settings.db_path = ":memory:"
        with TestClient(app) as tc:
            yield tc


def test_store_available_in_app_state(test_client):
    """app.state.store is a live SnapshotStore after startup."""
    assert hasattr(test_client.app.state, "store")
    assert isinstance(test_client.app.state.store, SnapshotStore)


# ---------------------------------------------------------------------------
# Target management endpoint tests
# ---------------------------------------------------------------------------

def test_list_targets_empty(test_client):
    """GET /api/v1/targets returns an empty list when no snapshots exist."""
    response = test_client.get("/api/v1/targets")
    assert response.status_code == 200
    assert response.json() == []



def test_get_overview_empty(test_client):
    """GET /api/v1/overview returns correct schema on an empty store."""
    response = test_client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_targets" in data
    assert "last_run_at" in data
    assert "recent_diffs" in data
    assert "open_tickets" in data
    assert data["total_targets"] == 0
    assert data["last_run_at"] is None
    assert data["recent_diffs"] == 0
    assert data["open_tickets"] == 0


def test_get_overview_schema_types(test_client):
    """GET /api/v1/overview returns correct field types even on an empty store."""
    response = test_client.get("/api/v1/overview")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["total_targets"], int)
    assert data["last_run_at"] is None or isinstance(data["last_run_at"], int)
    assert isinstance(data["recent_diffs"], int)
    assert isinstance(data["open_tickets"], int)


# ---------------------------------------------------------------------------
# Paginated history endpoint tests
# ---------------------------------------------------------------------------

def test_list_snapshots_empty(test_client):
    response = test_client.get("/api/v1/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["page_size"] == 25
    assert data["pages"] == 0


def test_list_diffs_empty(test_client):
    response = test_client.get("/api/v1/diffs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_tickets_empty(test_client):
    response = test_client.get("/api/v1/tickets")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_snapshots_pagination_params(test_client):
    """Verify pagination query params are accepted."""
    response = test_client.get("/api/v1/snapshots?page=2&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["page_size"] == 10


def test_list_snapshots_invalid_page(test_client):
    """page must be >= 1."""
    response = test_client.get("/api/v1/snapshots?page=0")
    assert response.status_code == 422
