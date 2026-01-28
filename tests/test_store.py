"""Tests for the SQLite store module."""

import pytest
import time

from app.store import SnapshotStore, compute_content_hash


@pytest.fixture
def store():
    """Create an in-memory database for testing."""
    s = SnapshotStore(':memory:')
    s.migrate()
    yield s
    s.close()


class TestComputeContentHash:
    """Tests for content hash computation."""

    def test_same_prefixes_same_hash(self):
        """Same prefixes should produce same hash."""
        hash1 = compute_content_hash(['1.0.0.0/8', '2.0.0.0/8'], ['2001::/32'])
        hash2 = compute_content_hash(['1.0.0.0/8', '2.0.0.0/8'], ['2001::/32'])
        assert hash1 == hash2

    def test_order_independent(self):
        """Hash should be independent of input order."""
        hash1 = compute_content_hash(['2.0.0.0/8', '1.0.0.0/8'], ['2001::/32'])
        hash2 = compute_content_hash(['1.0.0.0/8', '2.0.0.0/8'], ['2001::/32'])
        assert hash1 == hash2

    def test_different_prefixes_different_hash(self):
        """Different prefixes should produce different hashes."""
        hash1 = compute_content_hash(['1.0.0.0/8'], ['2001::/32'])
        hash2 = compute_content_hash(['3.0.0.0/8'], ['2001::/32'])
        assert hash1 != hash2

    def test_empty_prefixes(self):
        """Empty prefix lists should produce valid hash."""
        hash1 = compute_content_hash([], [])
        assert len(hash1) == 64  # SHA256 hex length


class TestSnapshotOperations:
    """Tests for snapshot CRUD operations."""

    def test_save_and_retrieve_snapshot(self, store):
        """Test saving and retrieving a snapshot."""
        snapshot_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB', 'RIPE'],
            ipv4_prefixes=['8.8.8.0/24', '8.8.4.0/24'],
            ipv6_prefixes=['2001:4860::/32'],
        )

        assert snapshot_id is not None
        assert snapshot_id > 0

        snapshot = store.get_snapshot_by_id(snapshot_id)
        assert snapshot is not None
        assert snapshot.target == 'AS15169'
        assert snapshot.target_type == 'asn'
        assert snapshot.irr_sources == ['RADB', 'RIPE']
        assert '8.8.8.0/24' in snapshot.ipv4_prefixes
        assert '8.8.4.0/24' in snapshot.ipv4_prefixes
        assert '2001:4860::/32' in snapshot.ipv6_prefixes

    def test_get_latest_snapshot(self, store):
        """Test getting the latest snapshot."""
        # Create first snapshot
        store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8'],
            ipv6_prefixes=[],
        )

        # Create second snapshot
        second_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['2.0.0.0/8'],
            ipv6_prefixes=[],
        )

        latest = store.get_latest_snapshot('AS15169')
        assert latest is not None
        assert latest.id == second_id
        assert '2.0.0.0/8' in latest.ipv4_prefixes

    def test_get_snapshot_before_timestamp(self, store):
        """Test getting snapshot before a timestamp."""
        # Create first snapshot
        first_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8'],
            ipv6_prefixes=[],
        )

        first_snapshot = store.get_snapshot_by_id(first_id)

        time.sleep(0.1)

        # Create second snapshot
        store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['2.0.0.0/8'],
            ipv6_prefixes=[],
        )

        # Get snapshot before the second one
        future_ts = int(time.time()) + 100
        previous = store.get_snapshot_before('AS15169', future_ts)
        assert previous is not None

    def test_get_snapshot_history(self, store):
        """Test getting snapshot history."""
        for i in range(5):
            store.save_snapshot(
                target='AS15169',
                target_type='asn',
                irr_sources=['RADB'],
                ipv4_prefixes=[f'{i}.0.0.0/8'],
                ipv6_prefixes=[],
            )
        history = store.get_snapshot_history('AS15169', limit=3)
        assert len(history) == 3
        # Should be newest first
        assert '4.0.0.0/8' in history[0].ipv4_prefixes

    def test_no_snapshot_found(self, store):
        """Test when no snapshot is found."""
        latest = store.get_latest_snapshot('AS99999')
        assert latest is None


class TestDiffOperations:
    """Tests for diff CRUD operations."""

    def test_save_and_retrieve_diff(self, store):
        """Test saving and retrieving a diff."""
        # Create snapshots first
        old_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8'],
            ipv6_prefixes=[],
        )

        new_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8', '2.0.0.0/8'],
            ipv6_prefixes=[],
        )

        diff_id = store.save_diff(
            new_snapshot_id=new_id,
            old_snapshot_id=old_id,
            target='AS15169',
            added_v4=['2.0.0.0/8'],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='abc123',
        )

        diff = store.get_diff_by_id(diff_id)
        assert diff is not None
        assert diff.target == 'AS15169'
        assert diff.added_v4 == ['2.0.0.0/8']
        assert diff.has_changes is True

    def test_get_diff_by_hash(self, store):
        """Test getting diff by hash."""
        new_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8'],
            ipv6_prefixes=[],
        )

        store.save_diff(
            new_snapshot_id=new_id,
            old_snapshot_id=None,
            target='AS15169',
            added_v4=['1.0.0.0/8'],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='unique_hash_123',
        )

        diff = store.get_diff_by_hash('unique_hash_123')
        assert diff is not None
        assert diff.diff_hash == 'unique_hash_123'

    def test_diff_no_changes(self, store):
        """Test diff with no changes."""
        new_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=[],
            ipv6_prefixes=[],
        )

        diff_id = store.save_diff(
            new_snapshot_id=new_id,
            old_snapshot_id=None,
            target='AS15169',
            added_v4=[],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='no_changes_hash',
        )

        diff = store.get_diff_by_id(diff_id)
        assert diff.has_changes is False


class TestTicketOperations:
    """Tests for ticket CRUD operations."""

    def test_save_and_retrieve_ticket(self, store):
        """Test saving and retrieving a ticket."""
        # Create snapshot and diff first
        snapshot_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=['1.0.0.0/8'],
            ipv6_prefixes=[],
        )

        diff_id = store.save_diff(
            new_snapshot_id=snapshot_id,
            old_snapshot_id=None,
            target='AS15169',
            added_v4=['1.0.0.0/8'],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='diff_hash_123',
        )

        ticket_id = store.save_ticket(
            diff_id=diff_id,
            target='AS15169',
            status='pending',
            request_payload={'test': 'payload'},
        )

        ticket = store.get_ticket_by_id(ticket_id)
        assert ticket is not None
        assert ticket.target == 'AS15169'
        assert ticket.status == 'pending'
        assert ticket.request_payload == {'test': 'payload'}

    def test_update_ticket_status(self, store):
        """Test updating ticket status."""
        snapshot_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=[],
            ipv6_prefixes=[],
        )

        diff_id = store.save_diff(
            new_snapshot_id=snapshot_id,
            old_snapshot_id=None,
            target='AS15169',
            added_v4=[],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='hash',
        )

        ticket_id = store.save_ticket(
            diff_id=diff_id,
            target='AS15169',
            status='pending',
            request_payload={},
        )

        store.update_ticket_status(
            ticket_id=ticket_id,
            status='submitted',
            response_payload={'ticket_id': 'TKT-123'},
            external_ticket_id='TKT-123',
        )

        ticket = store.get_ticket_by_id(ticket_id)
        assert ticket.status == 'submitted'
        assert ticket.external_ticket_id == 'TKT-123'
        assert ticket.response_payload == {'ticket_id': 'TKT-123'}

    def test_get_ticket_for_diff(self, store):
        """Test getting ticket for a diff."""
        snapshot_id = store.save_snapshot(
            target='AS15169',
            target_type='asn',
            irr_sources=['RADB'],
            ipv4_prefixes=[],
            ipv6_prefixes=[],
        )

        diff_id = store.save_diff(
            new_snapshot_id=snapshot_id,
            old_snapshot_id=None,
            target='AS15169',
            added_v4=[],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            diff_hash='hash',
        )

        store.save_ticket(
            diff_id=diff_id,
            target='AS15169',
            status='submitted',
            request_payload={},
            external_ticket_id='TKT-456',
        )

        ticket = store.get_ticket_for_diff(diff_id)
        assert ticket is not None
        assert ticket.external_ticket_id == 'TKT-456'
