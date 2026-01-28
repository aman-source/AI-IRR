"""Tests for the diff computation module."""

import pytest

from app.diff import (
    compute_diff,
    compute_diff_hash,
    format_diff_human,
    format_diff_json,
    DiffResult,
)
from app.store import Snapshot


def create_snapshot(
    id: int,
    target: str = "AS15169",
    ipv4: list = None,
    ipv6: list = None,
) -> Snapshot:
    """Helper to create a snapshot for testing."""
    return Snapshot(
        id=id,
        target=target,
        target_type="asn",
        timestamp=1000000 + id,
        irr_sources=["RADB"],
        ipv4_prefixes=ipv4 or [],
        ipv6_prefixes=ipv6 or [],
        content_hash="hash",
        created_at=1000000 + id,
    )


class TestComputeDiffHash:
    """Tests for diff hash computation."""

    def test_same_inputs_same_hash(self):
        """Same inputs should produce same hash."""
        hash1 = compute_diff_hash(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        hash2 = compute_diff_hash(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        assert hash1 == hash2

    def test_order_independent(self):
        """Hash should be independent of input order."""
        hash1 = compute_diff_hash(
            target="AS15169",
            added_v4=["2.0.0.0/8", "1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        hash2 = compute_diff_hash(
            target="AS15169",
            added_v4=["1.0.0.0/8", "2.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        assert hash1 == hash2

    def test_different_targets_different_hash(self):
        """Different targets should produce different hashes."""
        hash1 = compute_diff_hash(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        hash2 = compute_diff_hash(
            target="AS16509",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        assert hash1 != hash2

    def test_different_changes_different_hash(self):
        """Different changes should produce different hashes."""
        hash1 = compute_diff_hash(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
        )
        hash2 = compute_diff_hash(
            target="AS15169",
            added_v4=[],
            removed_v4=["1.0.0.0/8"],
            added_v6=[],
            removed_v6=[],
        )
        assert hash1 != hash2


class TestComputeDiff:
    """Tests for diff computation."""

    def test_no_changes(self):
        """Test when there are no changes."""
        old = create_snapshot(1, ipv4=["1.0.0.0/8"], ipv6=["2001::/32"])
        new = create_snapshot(2, ipv4=["1.0.0.0/8"], ipv6=["2001::/32"])

        diff = compute_diff(new, old)

        assert diff.added_v4 == []
        assert diff.removed_v4 == []
        assert diff.added_v6 == []
        assert diff.removed_v6 == []
        assert diff.has_changes is False

    def test_additions_only(self):
        """Test when only additions are made."""
        old = create_snapshot(1, ipv4=["1.0.0.0/8"], ipv6=[])
        new = create_snapshot(2, ipv4=["1.0.0.0/8", "2.0.0.0/8"], ipv6=["2001::/32"])

        diff = compute_diff(new, old)

        assert diff.added_v4 == ["2.0.0.0/8"]
        assert diff.removed_v4 == []
        assert diff.added_v6 == ["2001::/32"]
        assert diff.removed_v6 == []
        assert diff.has_changes is True

    def test_removals_only(self):
        """Test when only removals are made."""
        old = create_snapshot(1, ipv4=["1.0.0.0/8", "2.0.0.0/8"], ipv6=["2001::/32"])
        new = create_snapshot(2, ipv4=["1.0.0.0/8"], ipv6=[])

        diff = compute_diff(new, old)

        assert diff.added_v4 == []
        assert diff.removed_v4 == ["2.0.0.0/8"]
        assert diff.added_v6 == []
        assert diff.removed_v6 == ["2001::/32"]
        assert diff.has_changes is True

    def test_mixed_changes(self):
        """Test mixed additions and removals."""
        old = create_snapshot(1, ipv4=["1.0.0.0/8", "2.0.0.0/8"], ipv6=["2001::/32"])
        new = create_snapshot(2, ipv4=["1.0.0.0/8", "3.0.0.0/8"], ipv6=["2002::/32"])

        diff = compute_diff(new, old)

        assert diff.added_v4 == ["3.0.0.0/8"]
        assert diff.removed_v4 == ["2.0.0.0/8"]
        assert diff.added_v6 == ["2002::/32"]
        assert diff.removed_v6 == ["2001::/32"]
        assert diff.has_changes is True

    def test_first_snapshot(self):
        """Test when there's no previous snapshot."""
        new = create_snapshot(1, ipv4=["1.0.0.0/8"], ipv6=["2001::/32"])

        diff = compute_diff(new, None)

        # All current prefixes are "added"
        assert diff.added_v4 == ["1.0.0.0/8"]
        assert diff.removed_v4 == []
        assert diff.added_v6 == ["2001::/32"]
        assert diff.removed_v6 == []
        assert diff.has_changes is True
        assert diff.old_snapshot_id is None

    def test_first_snapshot_empty(self):
        """Test first snapshot with no prefixes."""
        new = create_snapshot(1, ipv4=[], ipv6=[])

        diff = compute_diff(new, None)

        assert diff.added_v4 == []
        assert diff.added_v6 == []
        assert diff.has_changes is False

    def test_snapshot_ids_set(self):
        """Test that snapshot IDs are properly set."""
        old = create_snapshot(10, ipv4=["1.0.0.0/8"])
        new = create_snapshot(20, ipv4=["1.0.0.0/8", "2.0.0.0/8"])

        diff = compute_diff(new, old)

        assert diff.new_snapshot_id == 20
        assert diff.old_snapshot_id == 10

    def test_sorted_output(self):
        """Test that output lists are sorted."""
        old = create_snapshot(1, ipv4=["1.0.0.0/8"])
        new = create_snapshot(
            2,
            ipv4=["1.0.0.0/8", "3.0.0.0/8", "2.0.0.0/8", "10.0.0.0/8"]
        )

        diff = compute_diff(new, old)

        # Should be sorted
        assert diff.added_v4 == ["10.0.0.0/8", "2.0.0.0/8", "3.0.0.0/8"]


class TestDiffResultSummary:
    """Tests for DiffResult.summary property."""

    def test_summary_no_changes(self):
        """Test summary when no changes."""
        diff = DiffResult(
            target="AS15169",
            has_changes=False,
        )
        assert "No changes" in diff.summary

    def test_summary_with_changes(self):
        """Test summary with changes."""
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8", "2.0.0.0/8"],
            removed_v4=["3.0.0.0/8"],
            added_v6=["2001::/32"],
            removed_v6=[],
            has_changes=True,
        )

        summary = diff.summary
        assert "2 added IPv4" in summary
        assert "1 removed IPv4" in summary
        assert "1 added IPv6" in summary
        assert "AS15169" in summary


class TestFormatDiffHuman:
    """Tests for human-readable formatting."""

    def test_format_no_changes(self):
        """Test formatting when no changes."""
        diff = DiffResult(target="AS15169", has_changes=False)
        output = format_diff_human(diff)

        assert "AS15169" in output
        assert "No changes" in output

    def test_format_with_changes(self):
        """Test formatting with changes."""
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=["2.0.0.0/8"],
            added_v6=[],
            removed_v6=[],
            has_changes=True,
        )
        output = format_diff_human(diff)

        assert "AS15169" in output
        assert "+ 1.0.0.0/8" in output
        assert "- 2.0.0.0/8" in output

    def test_format_truncates_long_lists(self):
        """Test that long lists are truncated."""
        diff = DiffResult(
            target="AS15169",
            added_v4=[f"{i}.0.0.0/8" for i in range(20)],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            has_changes=True,
        )
        output = format_diff_human(diff)

        assert "... and 10 more" in output


class TestFormatDiffJson:
    """Tests for JSON formatting."""

    def test_format_includes_all_fields(self):
        """Test that JSON output includes all fields."""
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            has_changes=True,
            diff_hash="abc123",
            new_snapshot_id=10,
            old_snapshot_id=5,
        )

        output = format_diff_json(diff)

        assert output['target'] == "AS15169"
        assert output['has_changes'] is True
        assert output['added_v4'] == ["1.0.0.0/8"]
        assert output['diff_hash'] == "abc123"
        assert output['new_snapshot_id'] == 10
        assert output['old_snapshot_id'] == 5
        assert 'summary' in output
