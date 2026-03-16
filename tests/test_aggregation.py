"""Tests for Python-side prefix aggregation using ipaddress.collapse_addresses().

AS-BYTEDANCE scenario:
  IPv4: 237 raw prefixes (10 /16 supernets + 227 covered /24 subnets)
        → 10 aggregated  (covered subnets removed)
  IPv6: 126 raw prefixes (3 /32 supernets + 123 covered /48 subnets)
        → 3 aggregated   (covered subnets removed)
"""

import ipaddress
import json
import pytest
from unittest.mock import MagicMock, patch

from app.bgpq4_client import BGPQ4Client, PrefixResult, collapse_prefixes


# ---------------------------------------------------------------------------
# Helpers to build mock AS-BYTEDANCE prefix data
# ---------------------------------------------------------------------------

def _build_ipv4_bytedance() -> set:
    """Build 237 IPv4 prefixes that collapse to 10.

    Structure: 10 /16 supernets from distinct /8 blocks + 227 covered /24 subnets.
      - Supernets 0-8: each contributes 23 /24 subnets  (9 × 23 = 207)
      - Supernet  9:  contributes 20 /24 subnets        (1 × 20 =  20)
    Total subnets: 207 + 20 = 227
    Total prefixes: 10 supernets + 227 subnets = 237
    After collapse_prefixes(): 10  (subnets are subsumed by supernets;
      supernets are in separate /8 blocks so they never merge with each other)
    """
    # Each supernet lives in its own /8 (1.x, 2.x, ..., 10.x) so they
    # are never adjacent and will not be merged by collapse_addresses().
    prefixes = set()
    for i in range(10):
        octet = i + 1  # 1 through 10
        supernet = ipaddress.ip_network(f"{octet}.0.0.0/16")
        prefixes.add(str(supernet))
        subnets = list(supernet.subnets(prefixlen_diff=8))  # /24s
        count = 23 if i < 9 else 20
        for subnet in subnets[:count]:
            prefixes.add(str(subnet))
    return prefixes  # 10 + 23*9 + 20 = 237


def _build_ipv6_bytedance() -> set:
    """Build 126 IPv6 prefixes that collapse to 3.

    Structure: 3 /32 supernets + 123 /48 subnets covered by those supernets.
      - Each supernet: 41 /48 subnets  (3 × 41 = 123)
    Total prefixes: 3 supernets + 123 subnets = 126
    After collapse_prefixes(): 3  (subnets are subsumed by supernets)
    """
    prefixes = set()
    for i in range(1, 4):
        supernet = ipaddress.ip_network(f"2001:{i:x}00::/32")
        prefixes.add(str(supernet))
        subnets = list(supernet.subnets(prefixlen_diff=16))  # /48s
        for subnet in subnets[:41]:
            prefixes.add(str(subnet))
    return prefixes  # 3 + 3*41 = 126


# ---------------------------------------------------------------------------
# Unit tests for collapse_prefixes()
# ---------------------------------------------------------------------------

class TestCollapsePrefixes:

    def test_covered_subnet_removed(self):
        """A subnet covered by a supernet is removed."""
        prefixes = {"10.0.0.0/16", "10.0.1.0/24", "10.0.2.0/24"}
        result = collapse_prefixes(prefixes)
        assert result == {"10.0.0.0/16"}

    def test_adjacent_networks_merged(self):
        """Two adjacent same-size networks merge into one supernet."""
        prefixes = {"192.168.0.0/24", "192.168.1.0/24"}
        result = collapse_prefixes(prefixes)
        assert result == {"192.168.0.0/23"}

    def test_non_adjacent_networks_unchanged(self):
        """Non-adjacent, non-overlapping networks are left as-is."""
        prefixes = {"10.0.0.0/24", "10.0.2.0/24"}
        result = collapse_prefixes(prefixes)
        assert result == {"10.0.0.0/24", "10.0.2.0/24"}

    def test_empty_input(self):
        assert collapse_prefixes(set()) == set()

    def test_single_prefix(self):
        assert collapse_prefixes({"10.0.0.0/8"}) == {"10.0.0.0/8"}

    def test_duplicate_prefixes_deduplicated(self):
        prefixes = {"10.0.0.0/24", "10.0.0.0/24"}
        assert collapse_prefixes(prefixes) == {"10.0.0.0/24"}

    def test_invalid_prefix_skipped(self):
        prefixes = {"10.0.0.0/24", "not-a-prefix", "192.168.1.0/24"}
        result = collapse_prefixes(prefixes)
        assert result == {"10.0.0.0/24", "192.168.1.0/24"}

    def test_host_route_not_strict(self):
        """Host bits set are accepted with strict=False."""
        prefixes = {"10.0.0.1/24"}  # host bit set
        result = collapse_prefixes(prefixes)
        assert result == {"10.0.0.0/24"}

    def test_ipv6_adjacent_merged(self):
        prefixes = {"2001:db8::/33", "2001:db8:8000::/33"}
        result = collapse_prefixes(prefixes)
        assert result == {"2001:db8::/32"}

    def test_ipv6_covered_subnet_removed(self):
        prefixes = {"2001:db8::/32", "2001:db8:1::/48", "2001:db8:2::/48"}
        result = collapse_prefixes(prefixes)
        assert result == {"2001:db8::/32"}

    def test_mixed_ipv4_ipv6_does_not_crash(self):
        """Mixed IPv4+IPv6 input must not raise — each family collapses independently."""
        prefixes = {
            "10.0.0.0/24", "10.0.1.0/24",   # adjacent IPv4 → 10.0.0.0/23
            "2001:db8::/33", "2001:db8:8000::/33",  # adjacent IPv6 → 2001:db8::/32
        }
        result = collapse_prefixes(prefixes)
        assert "10.0.0.0/23" in result
        assert "2001:db8::/32" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# AS-BYTEDANCE scenario
# ---------------------------------------------------------------------------

class TestASBytedanceAggregation:
    """Validates the AS-BYTEDANCE aggregation scenario end-to-end."""

    def test_ipv4_raw_count(self):
        """AS-BYTEDANCE IPv4 mock data contains 237 raw prefixes."""
        data = _build_ipv4_bytedance()
        assert len(data) == 237

    def test_ipv4_aggregated_count(self):
        """237 IPv4 prefixes collapse to 10 after aggregation."""
        data = _build_ipv4_bytedance()
        result = collapse_prefixes(data)
        assert len(result) == 10

    def test_ipv6_raw_count(self):
        """AS-BYTEDANCE IPv6 mock data contains 126 raw prefixes."""
        data = _build_ipv6_bytedance()
        assert len(data) == 126

    def test_ipv6_aggregated_count(self):
        """126 IPv6 prefixes collapse to 3 after aggregation."""
        data = _build_ipv6_bytedance()
        result = collapse_prefixes(data)
        assert len(result) == 3

    @patch('subprocess.run')
    def test_bgpq4_client_applies_aggregation(self, mock_run):
        """BGPQ4Client.fetch_prefixes() applies collapse_prefixes() and records raw counts."""
        ipv4_data = _build_ipv4_bytedance()
        ipv6_data = _build_ipv6_bytedance()

        v4_output = json.dumps({"pl": [{"prefix": p} for p in ipv4_data]})
        v6_output = json.dumps({"pl": [{"prefix": p} for p in ipv6_data]})

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=v4_output, stderr=""),
            MagicMock(returncode=0, stdout=v6_output, stderr=""),
        ]

        client = BGPQ4Client(sources=["RADB"], aggregate=False)
        result = client.fetch_prefixes("AS-BYTEDANCE")

        # Raw counts preserved
        assert result.ipv4_raw_count == 237
        assert result.ipv6_raw_count == 126

        # Python aggregation applied
        assert len(result.ipv4_prefixes) == 10
        assert len(result.ipv6_prefixes) == 3

    @patch('subprocess.run')
    def test_prefix_result_raw_counts_default_zero(self, mock_run):
        """When queries fail, raw counts remain 0."""
        mock_run.side_effect = FileNotFoundError("bgpq4 not found")

        client = BGPQ4Client()
        result = client.fetch_prefixes("AS-BYTEDANCE")

        assert result.ipv4_raw_count == 0
        assert result.ipv6_raw_count == 0
