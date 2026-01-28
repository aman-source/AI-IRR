"""Tests for the ticketing client."""

import pytest
from unittest.mock import Mock, patch

import requests

from app.ticketing import TicketingClient, TicketingError, TicketingAPIError, TicketResponse
from app.diff import DiffResult


@pytest.fixture
def diff_result():
    """Create a sample diff result for testing."""
    return DiffResult(
        target="AS15169",
        added_v4=["1.0.0.0/8", "2.0.0.0/8"],
        removed_v4=["3.0.0.0/8"],
        added_v6=["2001::/32"],
        removed_v6=[],
        has_changes=True,
        diff_hash="abc123def456",
    )


class TestTicketingClient:
    """Tests for TicketingClient."""

    def test_init(self):
        """Test client initialization."""
        client = TicketingClient(
            base_url="https://api.example.com/",
            api_token="test-token",
            timeout=45,
            max_retries=5,
        )

        assert client.base_url == "https://api.example.com"  # Trailing slash removed
        assert client.api_token == "test-token"
        assert client.timeout == 45
        assert client.max_retries == 5

    def test_build_payload(self, diff_result):
        """Test payload building."""
        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        payload = client._build_payload(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB", "RIPE"],
        )

        assert payload['type'] == 'irr_prefix_change'
        assert payload['target'] == 'AS15169'
        assert payload['changes']['added_ipv4'] == ["1.0.0.0/8", "2.0.0.0/8"]
        assert payload['changes']['removed_ipv4'] == ["3.0.0.0/8"]
        assert payload['changes']['added_ipv6'] == ["2001::/32"]
        assert payload['changes']['removed_ipv6'] == []
        assert payload['irr_sources'] == ["RADB", "RIPE"]
        assert payload['diff_hash'] == "abc123def456"
        assert 'timestamp' in payload
        assert 'summary' in payload

    def test_dry_run(self, diff_result):
        """Test dry run mode."""
        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        response = client.create_ticket(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
            dry_run=True,
        )

        assert response.status == 'dry_run'
        assert response.ticket_id is None

    @patch('requests.Session.post')
    def test_create_ticket_success(self, mock_post, diff_result):
        """Test successful ticket creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'ticket_id': 'TKT-2025-001234',
            'status': 'created',
        }
        mock_post.return_value = mock_response

        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        response = client.create_ticket(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
        )

        assert response.status == 'created'
        assert response.ticket_id == 'TKT-2025-001234'
        assert response.is_duplicate is False

        # Check headers
        call_kwargs = mock_post.call_args[1]
        assert 'Authorization' in call_kwargs['headers']
        assert call_kwargs['headers']['Authorization'] == 'Bearer token'
        assert call_kwargs['headers']['X-Idempotency-Key'] == 'abc123def456'

    @patch('requests.Session.post')
    def test_create_ticket_duplicate(self, mock_post, diff_result):
        """Test handling duplicate ticket (409)."""
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            'error': 'duplicate',
            'message': 'Ticket already exists',
            'existing_ticket_id': 'TKT-2025-001234',
        }
        mock_post.return_value = mock_response

        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        response = client.create_ticket(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
        )

        assert response.status == 'duplicate'
        assert response.ticket_id == 'TKT-2025-001234'
        assert response.is_duplicate is True

    @patch('requests.Session.post')
    def test_create_ticket_client_error(self, mock_post, diff_result):
        """Test handling client error (4xx)."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        response = client.create_ticket(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
        )

        assert response.status == 'failed'
        assert response.ticket_id is None
        assert response.error_message is not None
        assert "400" in response.error_message

    @patch('requests.Session.post')
    def test_create_ticket_network_error(self, mock_post, diff_result):
        """Test handling network errors."""
        mock_post.side_effect = requests.RequestException("Connection failed")

        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
            max_retries=1,  # Reduce retries for faster test
        )

        response = client.create_ticket(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
        )

        assert response.status == 'failed'
        assert "Connection failed" in response.error_message

    def test_get_payload(self, diff_result):
        """Test getting payload without submitting."""
        client = TicketingClient(
            base_url="https://api.example.com",
            api_token="token",
        )

        payload = client.get_payload(
            target="AS15169",
            diff=diff_result,
            irr_sources=["RADB"],
        )

        assert payload['target'] == 'AS15169'
        assert payload['type'] == 'irr_prefix_change'


class TestTicketResponse:
    """Tests for TicketResponse dataclass."""

    def test_success_response(self):
        """Test successful response."""
        response = TicketResponse(
            ticket_id='TKT-123',
            status='created',
        )
        assert response.ticket_id == 'TKT-123'
        assert response.status == 'created'
        assert response.is_duplicate is False
        assert response.error_message is None

    def test_duplicate_response(self):
        """Test duplicate response."""
        response = TicketResponse(
            ticket_id='TKT-123',
            status='duplicate',
            is_duplicate=True,
        )
        assert response.is_duplicate is True

    def test_failed_response(self):
        """Test failed response."""
        response = TicketResponse(
            ticket_id=None,
            status='failed',
            error_message='Connection timeout',
        )
        assert response.ticket_id is None
        assert response.status == 'failed'
        assert response.error_message == 'Connection timeout'
