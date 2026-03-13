"""Tests for the Teams notifier."""

import pytest
from unittest.mock import Mock, patch

import requests

from app.teams import TeamsNotifier
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


class TestTeamsNotifier:
    """Tests for TeamsNotifier."""

    def test_init_valid(self):
        """Test notifier initialization with valid URL."""
        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        assert notifier.webhook_url == "https://example.com/webhook"
        assert notifier.timeout == 15

    def test_init_with_custom_timeout(self):
        """Test notifier initialization with custom timeout."""
        notifier = TeamsNotifier(
            webhook_url="https://example.com/webhook",
            timeout=30
        )
        assert notifier.timeout == 30

    def test_init_empty_url(self):
        """Test that empty URL raises ValueError."""
        with pytest.raises(ValueError, match="webhook_url must not be empty"):
            TeamsNotifier(webhook_url="")

    def test_init_whitespace_url(self):
        """Test that whitespace-only URL raises ValueError."""
        with pytest.raises(ValueError, match="webhook_url must not be empty"):
            TeamsNotifier(webhook_url="   ")

    def test_init_invalid_url(self):
        """Test that non-HTTP URL raises ValueError."""
        with pytest.raises(ValueError, match="must be a valid HTTP"):
            TeamsNotifier(webhook_url="ftp://example.com/webhook")

    def test_notify_no_webhook_configured(self, diff_result):
        """Test notify returns False when webhook URL is not configured."""
        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        notifier.webhook_url = ""  # Clear the URL

        result = notifier.notify("AS15169", diff_result)
        assert result is False

    def test_notify_dry_run(self, diff_result):
        """Test notify in dry-run mode."""
        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")

        result = notifier.notify("AS15169", diff_result, dry_run=True)
        assert result is True

    @patch('requests.post')
    def test_notify_success(self, mock_post, diff_result):
        """Test successful notification."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        result = notifier.notify("AS15169", diff_result)

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://example.com/webhook"
        assert "json" in call_args[1]

    @patch('requests.post')
    def test_notify_http_error(self, mock_post, diff_result):
        """Test notification handles HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.HTTPError("400 Bad Request")
        mock_post.return_value = mock_response

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        result = notifier.notify("AS15169", diff_result)

        assert result is False

    @patch('requests.post')
    def test_notify_timeout(self, mock_post, diff_result):
        """Test notification handles timeout."""
        mock_post.side_effect = requests.Timeout("Connection timed out")

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        result = notifier.notify("AS15169", diff_result)

        assert result is False

    @patch('requests.post')
    def test_notify_connection_error(self, mock_post, diff_result):
        """Test notification handles connection errors."""
        mock_post.side_effect = requests.ConnectionError("Connection failed")

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        result = notifier.notify("AS15169", diff_result)

        assert result is False

    @patch('requests.post')
    def test_notify_generic_error(self, mock_post, diff_result):
        """Test notification handles generic request errors."""
        mock_post.side_effect = requests.RequestException("Unknown error")

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        result = notifier.notify("AS15169", diff_result)

        assert result is False

    def test_build_payload_with_changes(self, diff_result):
        """Test payload building with prefix changes."""
        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        payload = notifier._build_payload("AS15169", diff_result, "TICKET-123")

        assert payload["type"] == "message"
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1

        card = payload["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"
        assert len(card["body"]) > 0

    def test_build_payload_no_changes(self, diff_result):
        """Test payload building with no changes."""
        diff_result.added_v4 = []
        diff_result.removed_v4 = []
        diff_result.added_v6 = []
        diff_result.removed_v6 = []

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        payload = notifier._build_payload("AS15169", diff_result, None)

        assert payload["type"] == "message"
        card = payload["attachments"][0]["content"]
        # Should still have body with basic info
        assert len(card["body"]) > 0

    def test_build_payload_with_ticket_id(self, diff_result):
        """Test payload includes ticket ID when provided."""
        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        payload = notifier._build_payload("AS15169", diff_result, "TICKET-999")

        card = payload["attachments"][0]["content"]
        # Find the FactSet block
        fact_blocks = [b for b in card["body"] if b.get("type") == "FactSet"]
        assert len(fact_blocks) > 0

        facts = fact_blocks[0]["facts"]
        ticket_fact = next((f for f in facts if f["title"] == "Ticket ID"), None)
        assert ticket_fact is not None
        assert ticket_fact["value"] == "TICKET-999"

    def test_build_payload_truncates_prefix_list(self, diff_result):
        """Test that long prefix lists are truncated with ellipsis."""
        # Add many prefixes to exceed the MAX_SHOW limit
        diff_result.added_v4 = [f"10.{i}.0.0/16" for i in range(20)]

        notifier = TeamsNotifier(webhook_url="https://example.com/webhook")
        payload = notifier._build_payload("AS15169", diff_result, None)

        card = payload["attachments"][0]["content"]
        # Check for "and N more" text
        text_blocks = [b["text"] for b in card["body"] if b.get("type") == "TextBlock"]
        text_content = "\n".join(text_blocks)
        assert "more" in text_content

    @patch('requests.post')
    def test_notify_with_all_parameters(self, mock_post, diff_result):
        """Test notify with all optional parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        notifier = TeamsNotifier(
            webhook_url="https://example.com/webhook",
            timeout=30
        )
        result = notifier.notify(
            "AS15169",
            diff_result,
            ticket_id="TICKET-123",
            dry_run=False
        )

        assert result is True
        call_args = mock_post.call_args
        assert call_args[1]["timeout"] == 30
