"""Tests for the BGPQ4 IRR client."""

import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from app.bgpq4_client import (
    BGPQ4Client,
    BGPQ4ClientError,
    BGPQ4NotFoundError,
    PrefixResult,
)


class TestBGPQ4Client:
    """Tests for BGPQ4Client."""

    def test_init_defaults(self):
        client = BGPQ4Client()
        assert client.bgpq4_cmd == ["wsl", "bgpq4"]
        assert client.timeout == 120
        assert client.source == "RADB"
        assert client.aggregate is True

    def test_init_custom(self):
        client = BGPQ4Client(
            bgpq4_cmd=["bgpq4"],
            timeout=60,
            source="RIPE",
            aggregate=False,
        )
        assert client.bgpq4_cmd == ["bgpq4"]
        assert client.timeout == 60
        assert client.source == "RIPE"
        assert client.aggregate is False

    @patch('subprocess.run')
    def test_fetch_prefixes_ipv4(self, mock_run):
        v4_output = json.dumps({
            "pl": [
                {"prefix": "8.8.8.0/24", "exact": True},
                {"prefix": "8.8.4.0/24", "exact": True},
            ]
        })
        v6_output = json.dumps({"pl": []})

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert result.ipv4_prefixes == {"8.8.8.0/24", "8.8.4.0/24"}
        assert result.ipv6_prefixes == set()
        assert result.sources_queried == ["RADB"]
        assert result.errors == []

    @patch('subprocess.run')
    def test_fetch_prefixes_ipv6(self, mock_run):
        v4_output = json.dumps({"pl": []})
        v6_output = json.dumps({
            "pl": [
                {"prefix": "2001:4860::/32", "exact": True},
                {"prefix": "2607:f8b0::/32", "exact": True},
            ]
        })

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert result.ipv4_prefixes == set()
        assert result.ipv6_prefixes == {"2001:4860::/32", "2607:f8b0::/32"}

    @patch('subprocess.run')
    def test_fetch_prefixes_mixed(self, mock_run):
        v4_output = json.dumps({
            "pl": [{"prefix": "8.8.8.0/24", "exact": True}]
        })
        v6_output = json.dumps({
            "pl": [{"prefix": "2001:4860::/32", "exact": True}]
        })

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert result.ipv4_prefixes == {"8.8.8.0/24"}
        assert result.ipv6_prefixes == {"2001:4860::/32"}

    @patch('subprocess.run')
    def test_fetch_prefixes_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="wsl", timeout=120)

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert result.ipv4_prefixes == set()
        assert result.ipv6_prefixes == set()
        assert len(result.errors) == 2  # Both IPv4 and IPv6 fail

    @patch('subprocess.run')
    def test_fetch_prefixes_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("wsl not found")

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert len(result.errors) == 2

    @patch('subprocess.run')
    def test_fetch_prefixes_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: no objects found"
        )

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert len(result.errors) == 2

    @patch('subprocess.run')
    def test_fetch_prefixes_partial_failure(self, mock_run):
        """IPv4 succeeds but IPv6 fails."""
        v4_output = json.dumps({
            "pl": [{"prefix": "8.8.8.0/24", "exact": True}]
        })

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            subprocess.TimeoutExpired(cmd="wsl", timeout=120),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS15169")

        assert result.ipv4_prefixes == {"8.8.8.0/24"}
        assert result.ipv6_prefixes == set()
        assert len(result.errors) == 1  # Only IPv6 failed

    @patch('subprocess.run')
    def test_as_set_support(self, mock_run):
        """Test that AS-SET targets work."""
        v4_output = json.dumps({
            "pl": [
                {"prefix": "10.0.0.0/8", "exact": True},
                {"prefix": "172.16.0.0/12", "exact": True},
            ]
        })
        v6_output = json.dumps({"pl": []})

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS-GOOGLE")

        assert result.ipv4_prefixes == {"10.0.0.0/8", "172.16.0.0/12"}

    @patch('subprocess.run')
    def test_command_flags_ipv4_with_aggregation(self, mock_run):
        """Verify correct flags for IPv4 with aggregation."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"pl": []}', stderr=""
        )

        client = BGPQ4Client(source="RADB", aggregate=True)
        client._run_bgpq4("AS15169", ipv6=False)

        cmd = mock_run.call_args[0][0]
        assert cmd[0:2] == ["wsl", "bgpq4"]
        assert "-4" in cmd
        assert "-j" in cmd
        assert "-A" in cmd
        assert "-S" in cmd
        idx = cmd.index("-S")
        assert cmd[idx + 1] == "RADB"
        assert "AS15169" in cmd

    @patch('subprocess.run')
    def test_command_flags_ipv6(self, mock_run):
        """Verify correct flags for IPv6."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"pl": []}', stderr=""
        )

        client = BGPQ4Client()
        client._run_bgpq4("AS-GOOGLE", ipv6=True)

        cmd = mock_run.call_args[0][0]
        assert "-6" in cmd
        assert "-4" not in cmd
        assert "AS-GOOGLE" in cmd

    @patch('subprocess.run')
    def test_command_flags_no_aggregation(self, mock_run):
        """Verify -A is not present when aggregation is disabled."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"pl": []}', stderr=""
        )

        client = BGPQ4Client(aggregate=False)
        client._run_bgpq4("AS15169", ipv6=False)

        cmd = mock_run.call_args[0][0]
        assert "-A" not in cmd

    @patch('subprocess.run')
    def test_command_custom_cmd(self, mock_run):
        """Verify custom bgpq4_cmd is used."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"pl": []}', stderr=""
        )

        client = BGPQ4Client(bgpq4_cmd=["/usr/local/bin/bgpq4"])
        client._run_bgpq4("AS15169", ipv6=False)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/local/bin/bgpq4"

    @patch('subprocess.run')
    def test_target_normalized_to_uppercase(self, mock_run):
        """Test that target is normalized to uppercase."""
        v4_output = json.dumps({"pl": [{"prefix": "8.8.8.0/24", "exact": True}]})
        v6_output = json.dumps({"pl": []})

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client()
        result = client.fetch_prefixes("as15169")

        # Check the command used uppercase target
        first_call_cmd = mock_run.call_args_list[0][0][0]
        assert "AS15169" in first_call_cmd


class TestParseJsonOutput:
    """Tests for JSON output parsing."""

    def test_parse_valid_output(self):
        client = BGPQ4Client()
        output = json.dumps({
            "pl": [
                {"prefix": "8.8.8.0/24", "exact": True},
                {"prefix": "8.8.4.0/24", "exact": True},
            ]
        })
        result = client._parse_json_output(output)
        assert result == {"8.8.8.0/24", "8.8.4.0/24"}

    def test_parse_empty_string(self):
        client = BGPQ4Client()
        result = client._parse_json_output("")
        assert result == set()

    def test_parse_whitespace_only(self):
        client = BGPQ4Client()
        result = client._parse_json_output("   \n  ")
        assert result == set()

    def test_parse_empty_list(self):
        client = BGPQ4Client()
        result = client._parse_json_output('{"pl": []}')
        assert result == set()

    def test_parse_no_pl_key(self):
        client = BGPQ4Client()
        result = client._parse_json_output('{"other_key": []}')
        assert result == set()

    def test_parse_invalid_json(self):
        client = BGPQ4Client()
        with pytest.raises(BGPQ4ClientError, match="Failed to parse"):
            client._parse_json_output("not valid json")

    def test_parse_entries_without_prefix(self):
        client = BGPQ4Client()
        output = json.dumps({
            "pl": [
                {"prefix": "8.8.8.0/24", "exact": True},
                {"no_prefix_key": True},
                {"prefix": "8.8.4.0/24", "exact": True},
            ]
        })
        result = client._parse_json_output(output)
        assert result == {"8.8.8.0/24", "8.8.4.0/24"}


class TestPrefixResult:
    """Tests for PrefixResult dataclass."""

    def test_default_values(self):
        result = PrefixResult()
        assert result.ipv4_prefixes == set()
        assert result.ipv6_prefixes == set()
        assert result.sources_queried == []
        assert result.errors == []

    def test_custom_values(self):
        result = PrefixResult(
            ipv4_prefixes={"1.0.0.0/8"},
            ipv6_prefixes={"2001::/32"},
            sources_queried=["RADB"],
            errors=["Error 1"],
        )
        assert result.ipv4_prefixes == {"1.0.0.0/8"}
        assert result.ipv6_prefixes == {"2001::/32"}
        assert result.sources_queried == ["RADB"]
        assert result.errors == ["Error 1"]


class TestClientContextManager:
    """Tests for context manager functionality."""

    def test_context_manager_enter(self):
        client = BGPQ4Client()
        with client as c:
            assert c is client

    def test_close_is_noop(self):
        client = BGPQ4Client()
        client.close()  # Should not raise
