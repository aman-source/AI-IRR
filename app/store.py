"""SQLite database layer for IRR Automation."""

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Generator


@dataclass
class Snapshot:
    """Represents a prefix snapshot."""
    id: int
    target: str
    target_type: str
    timestamp: int
    irr_sources: List[str]
    ipv4_prefixes: List[str]
    ipv6_prefixes: List[str]
    content_hash: str
    created_at: int


@dataclass
class Diff:
    """Represents a diff between two snapshots."""
    id: int
    new_snapshot_id: int
    old_snapshot_id: Optional[int]
    target: str
    added_v4: List[str]
    removed_v4: List[str]
    added_v6: List[str]
    removed_v6: List[str]
    diff_hash: str
    has_changes: bool
    created_at: int


@dataclass
class Ticket:
    """Represents a ticket record."""
    id: int
    diff_id: int
    target: str
    external_ticket_id: Optional[str]
    status: str
    request_payload: dict
    response_payload: Optional[dict]
    created_at: int


SCHEMA_SQL = """
-- Stores daily prefix snapshots
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,
    target_type TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    irr_sources TEXT NOT NULL,
    ipv4_prefixes TEXT NOT NULL,
    ipv6_prefixes TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

-- Stores computed diffs between snapshots
CREATE TABLE IF NOT EXISTS diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    new_snapshot_id INTEGER NOT NULL,
    old_snapshot_id INTEGER,
    target TEXT NOT NULL,
    added_v4 TEXT NOT NULL,
    removed_v4 TEXT NOT NULL,
    added_v6 TEXT NOT NULL,
    removed_v6 TEXT NOT NULL,
    diff_hash TEXT NOT NULL,
    has_changes INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (new_snapshot_id) REFERENCES snapshots(id),
    FOREIGN KEY (old_snapshot_id) REFERENCES snapshots(id)
);

-- Tracks tickets created for diffs
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    diff_id INTEGER NOT NULL,
    target TEXT NOT NULL,
    external_ticket_id TEXT,
    status TEXT NOT NULL,
    request_payload TEXT NOT NULL,
    response_payload TEXT,
    created_at INTEGER NOT NULL,
    FOREIGN KEY (diff_id) REFERENCES diffs(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_target_ts ON snapshots(target, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_diffs_hash ON diffs(diff_hash);
CREATE INDEX IF NOT EXISTS idx_tickets_diff ON tickets(diff_id);
"""


def compute_content_hash(ipv4_prefixes: List[str], ipv6_prefixes: List[str]) -> str:
    """
    Compute SHA256 hash of prefix lists for deduplication.

    Args:
        ipv4_prefixes: List of IPv4 CIDR prefixes.
        ipv6_prefixes: List of IPv6 CIDR prefixes.

    Returns:
        Hex-encoded SHA256 hash.
    """
    # Sort for consistent hashing
    sorted_v4 = sorted(ipv4_prefixes)
    sorted_v6 = sorted(ipv6_prefixes)

    # Combine into a single string
    content = json.dumps({"v4": sorted_v4, "v6": sorted_v6}, sort_keys=True)

    return hashlib.sha256(content.encode('utf-8')).hexdigest()


class SnapshotStore:
    """SQLite-backed storage for snapshots, diffs, and tickets."""

    def __init__(self, db_path: str):
        """
        Initialize the store.

        Args:
            db_path: Path to SQLite database file. Use ':memory:' for in-memory DB.
        """
        self.db_path = db_path

        # Create parent directories if needed
        if db_path != ':memory:':
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn: Optional[sqlite3.Connection] = None
        self._in_transaction: bool = False

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def migrate(self):
        """Create database tables if they don't exist."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for atomic transactions.

        All database operations within the context will be committed
        together, or rolled back if an exception occurs.

        Usage:
            with store.transaction():
                store.save_snapshot(...)
                store.save_diff(...)
                store.save_ticket(...)

        Yields:
            The database connection.
        """
        self._in_transaction = True
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self._in_transaction = False

    def _commit_if_not_in_transaction(self) -> None:
        """Commit the current transaction if not in a managed transaction."""
        if not self._in_transaction:
            self.conn.commit()

    # -------------------------------------------------------------------------
    # Snapshot operations
    # -------------------------------------------------------------------------

    def save_snapshot(
        self,
        target: str,
        target_type: str,
        irr_sources: List[str],
        ipv4_prefixes: List[str],
        ipv6_prefixes: List[str],
    ) -> int:
        """
        Save a new prefix snapshot.

        Args:
            target: ASN or AS-SET (e.g., "AS15169").
            target_type: "asn" or "as-set".
            irr_sources: List of IRR sources queried.
            ipv4_prefixes: List of IPv4 CIDR prefixes.
            ipv6_prefixes: List of IPv6 CIDR prefixes.

        Returns:
            ID of the created snapshot.
        """
        now = int(time.time())
        content_hash = compute_content_hash(ipv4_prefixes, ipv6_prefixes)

        cursor = self.conn.execute(
            """
            INSERT INTO snapshots
                (target, target_type, timestamp, irr_sources, ipv4_prefixes,
                 ipv6_prefixes, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target,
                target_type,
                now,
                json.dumps(irr_sources),
                json.dumps(sorted(ipv4_prefixes)),
                json.dumps(sorted(ipv6_prefixes)),
                content_hash,
                now,
            )
        )
        self._commit_if_not_in_transaction()
        return cursor.lastrowid

    def get_latest_snapshot(self, target: str) -> Optional[Snapshot]:
        """
        Get the most recent snapshot for a target.

        Args:
            target: ASN or AS-SET.

        Returns:
            Snapshot or None if not found.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM snapshots
            WHERE target = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (target,)
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_snapshot_before(self, target: str, timestamp: int) -> Optional[Snapshot]:
        """
        Get the most recent snapshot before a given timestamp.

        Args:
            target: ASN or AS-SET.
            timestamp: Unix timestamp.

        Returns:
            Snapshot or None if not found.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM snapshots
            WHERE target = ? AND timestamp < ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (target, timestamp)
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_snapshot_history(self, target: str, limit: int = 10) -> List[Snapshot]:
        """
        Get snapshot history for a target.

        Args:
            target: ASN or AS-SET.
            limit: Maximum number of snapshots to return.

        Returns:
            List of snapshots, newest first.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM snapshots
            WHERE target = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (target, limit)
        )
        return [self._row_to_snapshot(row) for row in cursor.fetchall()]

    def get_snapshot_by_id(self, snapshot_id: int) -> Optional[Snapshot]:
        """Get a snapshot by its ID."""
        cursor = self.conn.execute(
            "SELECT * FROM snapshots WHERE id = ?",
            (snapshot_id,)
        )
        row = cursor.fetchone()
        return self._row_to_snapshot(row) if row else None

    def _row_to_snapshot(self, row: sqlite3.Row) -> Snapshot:
        """Convert a database row to a Snapshot object."""
        return Snapshot(
            id=row['id'],
            target=row['target'],
            target_type=row['target_type'],
            timestamp=row['timestamp'],
            irr_sources=json.loads(row['irr_sources']),
            ipv4_prefixes=json.loads(row['ipv4_prefixes']),
            ipv6_prefixes=json.loads(row['ipv6_prefixes']),
            content_hash=row['content_hash'],
            created_at=row['created_at'],
        )

    # -------------------------------------------------------------------------
    # Diff operations
    # -------------------------------------------------------------------------

    def save_diff(
        self,
        new_snapshot_id: int,
        old_snapshot_id: Optional[int],
        target: str,
        added_v4: List[str],
        removed_v4: List[str],
        added_v6: List[str],
        removed_v6: List[str],
        diff_hash: str,
    ) -> int:
        """
        Save a computed diff.

        Args:
            new_snapshot_id: ID of the new snapshot.
            old_snapshot_id: ID of the old snapshot (None if first snapshot).
            target: ASN or AS-SET.
            added_v4: List of added IPv4 prefixes.
            removed_v4: List of removed IPv4 prefixes.
            added_v6: List of added IPv6 prefixes.
            removed_v6: List of removed IPv6 prefixes.
            diff_hash: Hash for idempotency.

        Returns:
            ID of the created diff.
        """
        now = int(time.time())
        has_changes = bool(added_v4 or removed_v4 or added_v6 or removed_v6)

        cursor = self.conn.execute(
            """
            INSERT INTO diffs
                (new_snapshot_id, old_snapshot_id, target, added_v4, removed_v4,
                 added_v6, removed_v6, diff_hash, has_changes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_snapshot_id,
                old_snapshot_id,
                target,
                json.dumps(sorted(added_v4)),
                json.dumps(sorted(removed_v4)),
                json.dumps(sorted(added_v6)),
                json.dumps(sorted(removed_v6)),
                diff_hash,
                1 if has_changes else 0,
                now,
            )
        )
        self._commit_if_not_in_transaction()
        return cursor.lastrowid

    def get_diff_by_hash(self, diff_hash: str) -> Optional[Diff]:
        """
        Get a diff by its hash.

        Args:
            diff_hash: The diff hash.

        Returns:
            Diff or None if not found.
        """
        cursor = self.conn.execute(
            "SELECT * FROM diffs WHERE diff_hash = ?",
            (diff_hash,)
        )
        row = cursor.fetchone()
        return self._row_to_diff(row) if row else None

    def get_diff_by_id(self, diff_id: int) -> Optional[Diff]:
        """Get a diff by its ID."""
        cursor = self.conn.execute(
            "SELECT * FROM diffs WHERE id = ?",
            (diff_id,)
        )
        row = cursor.fetchone()
        return self._row_to_diff(row) if row else None

    def get_latest_diff(self, target: str) -> Optional[Diff]:
        """Get the most recent diff for a target."""
        cursor = self.conn.execute(
            """
            SELECT * FROM diffs
            WHERE target = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (target,)
        )
        row = cursor.fetchone()
        return self._row_to_diff(row) if row else None

    def _row_to_diff(self, row: sqlite3.Row) -> Diff:
        """Convert a database row to a Diff object."""
        return Diff(
            id=row['id'],
            new_snapshot_id=row['new_snapshot_id'],
            old_snapshot_id=row['old_snapshot_id'],
            target=row['target'],
            added_v4=json.loads(row['added_v4']),
            removed_v4=json.loads(row['removed_v4']),
            added_v6=json.loads(row['added_v6']),
            removed_v6=json.loads(row['removed_v6']),
            diff_hash=row['diff_hash'],
            has_changes=bool(row['has_changes']),
            created_at=row['created_at'],
        )

    # -------------------------------------------------------------------------
    # Ticket operations
    # -------------------------------------------------------------------------

    def save_ticket(
        self,
        diff_id: int,
        target: str,
        status: str,
        request_payload: dict,
        response_payload: Optional[dict] = None,
        external_ticket_id: Optional[str] = None,
    ) -> int:
        """
        Save a ticket record.

        Args:
            diff_id: ID of the associated diff.
            target: ASN or AS-SET.
            status: Ticket status ("pending", "submitted", "failed").
            request_payload: JSON-serializable request payload.
            response_payload: Optional JSON-serializable response.
            external_ticket_id: Optional ticket ID from external system.

        Returns:
            ID of the created ticket.
        """
        now = int(time.time())

        cursor = self.conn.execute(
            """
            INSERT INTO tickets
                (diff_id, target, external_ticket_id, status, request_payload,
                 response_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                diff_id,
                target,
                external_ticket_id,
                status,
                json.dumps(request_payload),
                json.dumps(response_payload) if response_payload else None,
                now,
            )
        )
        self._commit_if_not_in_transaction()
        return cursor.lastrowid

    def update_ticket_status(
        self,
        ticket_id: int,
        status: str,
        response_payload: Optional[dict] = None,
        external_ticket_id: Optional[str] = None,
    ):
        """
        Update a ticket's status and response.

        Args:
            ticket_id: ID of the ticket to update.
            status: New status.
            response_payload: Optional response payload.
            external_ticket_id: Optional external ticket ID.
        """
        self.conn.execute(
            """
            UPDATE tickets
            SET status = ?,
                response_payload = ?,
                external_ticket_id = COALESCE(?, external_ticket_id)
            WHERE id = ?
            """,
            (
                status,
                json.dumps(response_payload) if response_payload else None,
                external_ticket_id,
                ticket_id,
            )
        )
        self._commit_if_not_in_transaction()

    def get_ticket_for_diff(self, diff_id: int) -> Optional[Ticket]:
        """
        Get the ticket associated with a diff.

        Args:
            diff_id: ID of the diff.

        Returns:
            Ticket or None if not found.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM tickets
            WHERE diff_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (diff_id,)
        )
        row = cursor.fetchone()
        return self._row_to_ticket(row) if row else None

    def get_ticket_by_id(self, ticket_id: int) -> Optional[Ticket]:
        """Get a ticket by its ID."""
        cursor = self.conn.execute(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,)
        )
        row = cursor.fetchone()
        return self._row_to_ticket(row) if row else None

    def _row_to_ticket(self, row: sqlite3.Row) -> Ticket:
        """Convert a database row to a Ticket object."""
        return Ticket(
            id=row['id'],
            diff_id=row['diff_id'],
            target=row['target'],
            external_ticket_id=row['external_ticket_id'],
            status=row['status'],
            request_payload=json.loads(row['request_payload']),
            response_payload=json.loads(row['response_payload']) if row['response_payload'] else None,
            created_at=row['created_at'],
        )
