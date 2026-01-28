"""Prefix diff computation for IRR Automation."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional, Set

from app.store import Snapshot


@dataclass
class DiffResult:
    """Result of comparing two snapshots."""
    target: str
    added_v4: List[str] = field(default_factory=list)
    removed_v4: List[str] = field(default_factory=list)
    added_v6: List[str] = field(default_factory=list)
    removed_v6: List[str] = field(default_factory=list)
    has_changes: bool = False
    diff_hash: str = ""
    new_snapshot_id: Optional[int] = None
    old_snapshot_id: Optional[int] = None

    @property
    def summary(self) -> str:
        """Generate a human-readable summary of changes."""
        parts = []
        if self.added_v4:
            parts.append(f"{len(self.added_v4)} added IPv4")
        if self.removed_v4:
            parts.append(f"{len(self.removed_v4)} removed IPv4")
        if self.added_v6:
            parts.append(f"{len(self.added_v6)} added IPv6")
        if self.removed_v6:
            parts.append(f"{len(self.removed_v6)} removed IPv6")

        if not parts:
            return f"No changes detected for {self.target}"

        return f"Detected {', '.join(parts)} prefixes for {self.target}"


def compute_diff_hash(
    target: str,
    added_v4: List[str],
    removed_v4: List[str],
    added_v6: List[str],
    removed_v6: List[str],
) -> str:
    """
    Compute SHA256 hash of diff for idempotency.

    The hash is computed from the target and sorted prefix lists to ensure
    consistent hashing regardless of input order.

    Args:
        target: ASN or AS-SET.
        added_v4: List of added IPv4 prefixes.
        removed_v4: List of removed IPv4 prefixes.
        added_v6: List of added IPv6 prefixes.
        removed_v6: List of removed IPv6 prefixes.

    Returns:
        Hex-encoded SHA256 hash.
    """
    content = json.dumps({
        'target': target,
        'added_v4': sorted(added_v4),
        'removed_v4': sorted(removed_v4),
        'added_v6': sorted(added_v6),
        'removed_v6': sorted(removed_v6),
    }, sort_keys=True)

    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def compute_diff(
    current: Snapshot,
    previous: Optional[Snapshot],
) -> DiffResult:
    """
    Compute the difference between two snapshots.

    Args:
        current: The current (new) snapshot.
        previous: The previous (old) snapshot. None if this is the first snapshot.

    Returns:
        DiffResult with lists of added and removed prefixes.
    """
    result = DiffResult(
        target=current.target,
        new_snapshot_id=current.id,
        old_snapshot_id=previous.id if previous else None,
    )

    # Convert to sets for efficient comparison
    current_v4: Set[str] = set(current.ipv4_prefixes)
    current_v6: Set[str] = set(current.ipv6_prefixes)

    if previous is None:
        # First snapshot - all prefixes are "added"
        result.added_v4 = sorted(current_v4)
        result.added_v6 = sorted(current_v6)
        result.has_changes = bool(current_v4 or current_v6)
    else:
        previous_v4: Set[str] = set(previous.ipv4_prefixes)
        previous_v6: Set[str] = set(previous.ipv6_prefixes)

        # Compute differences
        result.added_v4 = sorted(current_v4 - previous_v4)
        result.removed_v4 = sorted(previous_v4 - current_v4)
        result.added_v6 = sorted(current_v6 - previous_v6)
        result.removed_v6 = sorted(previous_v6 - current_v6)

        result.has_changes = bool(
            result.added_v4 or result.removed_v4 or
            result.added_v6 or result.removed_v6
        )

    # Compute diff hash
    result.diff_hash = compute_diff_hash(
        target=result.target,
        added_v4=result.added_v4,
        removed_v4=result.removed_v4,
        added_v6=result.added_v6,
        removed_v6=result.removed_v6,
    )

    return result


def format_diff_human(diff: DiffResult) -> str:
    """
    Format a diff result as human-readable text.

    Args:
        diff: The diff result to format.

    Returns:
        Human-readable string representation.
    """
    lines = [f"Changes for {diff.target}:"]

    if not diff.has_changes:
        lines.append("  No changes detected")
        return '\n'.join(lines)

    if diff.added_v4:
        lines.append(f"  Added IPv4 ({len(diff.added_v4)}):")
        for prefix in diff.added_v4[:10]:  # Show first 10
            lines.append(f"    + {prefix}")
        if len(diff.added_v4) > 10:
            lines.append(f"    ... and {len(diff.added_v4) - 10} more")

    if diff.removed_v4:
        lines.append(f"  Removed IPv4 ({len(diff.removed_v4)}):")
        for prefix in diff.removed_v4[:10]:
            lines.append(f"    - {prefix}")
        if len(diff.removed_v4) > 10:
            lines.append(f"    ... and {len(diff.removed_v4) - 10} more")

    if diff.added_v6:
        lines.append(f"  Added IPv6 ({len(diff.added_v6)}):")
        for prefix in diff.added_v6[:10]:
            lines.append(f"    + {prefix}")
        if len(diff.added_v6) > 10:
            lines.append(f"    ... and {len(diff.added_v6) - 10} more")

    if diff.removed_v6:
        lines.append(f"  Removed IPv6 ({len(diff.removed_v6)}):")
        for prefix in diff.removed_v6[:10]:
            lines.append(f"    - {prefix}")
        if len(diff.removed_v6) > 10:
            lines.append(f"    ... and {len(diff.removed_v6) - 10} more")

    return '\n'.join(lines)


def format_diff_json(diff: DiffResult) -> dict:
    """
    Format a diff result as a JSON-serializable dict.

    Args:
        diff: The diff result to format.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    return {
        'target': diff.target,
        'has_changes': diff.has_changes,
        'added_v4': diff.added_v4,
        'removed_v4': diff.removed_v4,
        'added_v6': diff.added_v6,
        'removed_v6': diff.removed_v6,
        'diff_hash': diff.diff_hash,
        'new_snapshot_id': diff.new_snapshot_id,
        'old_snapshot_id': diff.old_snapshot_id,
        'summary': diff.summary,
    }
