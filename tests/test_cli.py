"""Tests for CLI module."""

import argparse
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import sys

from app.cli import (
    create_parser,
    cmd_init_db,
    cmd_fetch,
    cmd_diff,
    cmd_submit,
    cmd_run,
    cmd_run_all,
    cmd_history,
    main,
    get_timestamp_str,
    print_output,
)
from app.config import Config, RADBConfig, DatabaseConfig, TicketingConfig, LoggingConfig, DiffConfig
from app.store import Snapshot, Diff, Ticket
from app.diff import DiffResult
from app.radb_client import PrefixResult
from app.ticketing import TicketResponse


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    return Config(
        irr_sources=['RIPE', 'RADB'],
        targets=['AS15169', 'AS16509'],
        radb=RADBConfig(base_url='https://rest.db.ripe.net', timeout_seconds=60, max_retries=3),
        database=DatabaseConfig(path=':memory:'),
        ticketing=TicketingConfig(base_url='https://api.example.com', api_token='test-token'),
        logging=LoggingConfig(level='INFO', format='text'),
        diff=DiffConfig(lookback_hours=24),
    )


@pytest.fixture
def mock_args():
    """Create mock CLI arguments."""
    return argparse.Namespace(
        config='config.yaml',
        verbose=False,
        quiet=False,
        json=False,
        target='AS15169',
        dry_run=False,
        limit=10,
    )


@pytest.fixture
def mock_snapshot():
    """Create a mock snapshot."""
    return Snapshot(
        id=1,
        target='AS15169',
        target_type='asn',
        timestamp=1700000000,
        irr_sources=['RIPE'],
        ipv4_prefixes=['8.8.8.0/24', '8.8.4.0/24'],
        ipv6_prefixes=['2001:4860::/32'],
        content_hash='abc123',
        created_at=1700000000,
    )


@pytest.fixture
def mock_diff_record():
    """Create a mock diff record."""
    return Diff(
        id=1,
        new_snapshot_id=2,
        old_snapshot_id=1,
        target='AS15169',
        added_v4=['8.8.4.0/24'],
        removed_v4=[],
        added_v6=[],
        removed_v6=[],
        diff_hash='def456',
        has_changes=True,
        created_at=1700000000,
    )


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_created(self):
        """Test that parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == 'irr-cli'

    def test_parser_has_all_subcommands(self):
        """Test that all subcommands are available."""
        parser = create_parser()
        # Parse with each subcommand to verify they exist
        subcommands = ['init-db', 'fetch', 'diff', 'submit', 'run', 'run-all', 'history']

        for cmd in subcommands:
            if cmd in ['init-db', 'run-all']:
                args = parser.parse_args([cmd])
            elif cmd == 'history':
                args = parser.parse_args([cmd, '--target', 'AS15169'])
            else:
                args = parser.parse_args([cmd, '--target', 'AS15169'])
            assert args.command == cmd

    def test_global_options(self):
        """Test global options are parsed."""
        parser = create_parser()
        args = parser.parse_args(['-v', '-c', 'custom.yaml', '--json', 'init-db'])
        assert args.verbose is True
        assert args.config == 'custom.yaml'
        assert args.json is True

    def test_fetch_requires_target(self):
        """Test that fetch command requires target."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['fetch'])

    def test_dry_run_option(self):
        """Test dry-run option for submit command."""
        parser = create_parser()
        args = parser.parse_args(['submit', '--target', 'AS15169', '--dry-run'])
        assert args.dry_run is True


class TestCmdInitDb:
    """Tests for init-db command."""

    @patch('app.cli.SnapshotStore')
    def test_init_db_success(self, mock_store_class, mock_config, mock_args):
        """Test successful database initialization."""
        mock_store = Mock()
        mock_store_class.return_value = mock_store

        result = cmd_init_db(mock_config, mock_args)

        assert result == 0
        mock_store_class.assert_called_once_with(mock_config.database.path)
        mock_store.migrate.assert_called_once()
        mock_store.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    def test_init_db_json_output(self, mock_store_class, mock_config, mock_args, capsys):
        """Test init-db with JSON output."""
        mock_store = Mock()
        mock_store_class.return_value = mock_store
        mock_args.json = True

        result = cmd_init_db(mock_config, mock_args)

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output['status'] == 'success'


class TestCmdFetch:
    """Tests for fetch command."""

    @patch('app.cli.SnapshotStore')
    @patch('app.cli.RADBClient')
    def test_fetch_success(self, mock_client_class, mock_store_class, mock_config, mock_args, mock_snapshot):
        """Test successful prefix fetch."""
        # Setup mocks
        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={'8.8.8.0/24', '8.8.4.0/24'},
            ipv6_prefixes={'2001:4860::/32'},
            sources_queried=['RIPE'],
            errors=[],
        )
        mock_client_class.return_value = mock_client

        mock_store = Mock()
        mock_store.save_snapshot.return_value = 1
        mock_store.get_snapshot_by_id.return_value = mock_snapshot
        mock_store_class.return_value = mock_store

        result = cmd_fetch(mock_config, mock_args)

        assert result == 0
        mock_client.fetch_prefixes.assert_called_once()
        mock_store.save_snapshot.assert_called_once()
        mock_client.close.assert_called_once()
        mock_store.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    @patch('app.cli.RADBClient')
    def test_fetch_all_errors_returns_1(self, mock_client_class, mock_store_class, mock_config, mock_args):
        """Test that fetch returns 1 when all sources fail."""
        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes=set(),
            ipv6_prefixes=set(),
            sources_queried=[],
            errors=['Failed to query RIPE'],
        )
        mock_client_class.return_value = mock_client

        result = cmd_fetch(mock_config, mock_args)

        assert result == 1
        mock_client.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    @patch('app.cli.RADBClient')
    def test_fetch_json_output(self, mock_client_class, mock_store_class, mock_config, mock_args, mock_snapshot, capsys):
        """Test fetch with JSON output."""
        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={'8.8.8.0/24'},
            ipv6_prefixes=set(),
            sources_queried=['RIPE'],
            errors=[],
        )
        mock_client_class.return_value = mock_client

        mock_store = Mock()
        mock_store.save_snapshot.return_value = 1
        mock_store.get_snapshot_by_id.return_value = mock_snapshot
        mock_store_class.return_value = mock_store

        mock_args.json = True
        result = cmd_fetch(mock_config, mock_args)

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output['target'] == 'AS15169'
        assert 'snapshot' in output


class TestCmdDiff:
    """Tests for diff command."""

    @patch('app.cli.SnapshotStore')
    def test_diff_no_snapshot(self, mock_store_class, mock_config, mock_args):
        """Test diff when no snapshot exists."""
        mock_store = Mock()
        mock_store.get_latest_snapshot.return_value = None
        mock_store_class.return_value = mock_store

        result = cmd_diff(mock_config, mock_args)

        assert result == 1
        mock_store.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    @patch('app.cli.compute_diff')
    def test_diff_success(self, mock_compute_diff, mock_store_class, mock_config, mock_args, mock_snapshot):
        """Test successful diff computation."""
        mock_store = Mock()
        mock_store.get_latest_snapshot.return_value = mock_snapshot
        mock_store.get_snapshot_before.return_value = None
        mock_store_class.return_value = mock_store

        mock_compute_diff.return_value = DiffResult(
            target='AS15169',
            added_v4=['8.8.8.0/24'],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            has_changes=True,
            diff_hash='abc123',
            new_snapshot_id=1,
            old_snapshot_id=None,
        )

        result = cmd_diff(mock_config, mock_args)

        assert result == 0
        mock_store.close.assert_called_once()


class TestCmdSubmit:
    """Tests for submit command."""

    @patch('app.cli.TicketingClient')
    @patch('app.cli.SnapshotStore')
    def test_submit_no_diff(self, mock_store_class, mock_ticket_class, mock_config, mock_args):
        """Test submit when no diff exists."""
        mock_store = Mock()
        mock_store.get_latest_diff.return_value = None
        mock_store_class.return_value = mock_store

        result = cmd_submit(mock_config, mock_args)

        assert result == 1
        mock_store.close.assert_called_once()

    @patch('app.cli.TicketingClient')
    @patch('app.cli.SnapshotStore')
    def test_submit_no_changes(self, mock_store_class, mock_ticket_class, mock_config, mock_args, mock_diff_record):
        """Test submit when no changes detected."""
        mock_diff_record.has_changes = False

        mock_store = Mock()
        mock_store.get_latest_diff.return_value = mock_diff_record
        mock_store_class.return_value = mock_store

        result = cmd_submit(mock_config, mock_args)

        assert result == 0
        mock_store.close.assert_called_once()

    @patch('app.cli.TicketingClient')
    @patch('app.cli.SnapshotStore')
    def test_submit_dry_run(self, mock_store_class, mock_ticket_class, mock_config, mock_args, mock_diff_record, mock_snapshot):
        """Test submit with dry-run."""
        mock_store = Mock()
        mock_store.get_latest_diff.return_value = mock_diff_record
        mock_store.get_ticket_for_diff.return_value = None
        mock_store.get_snapshot_by_id.return_value = mock_snapshot
        mock_store.save_ticket.return_value = 1
        mock_store_class.return_value = mock_store

        mock_client = Mock()
        mock_client.get_payload.return_value = {'type': 'irr_prefix_change'}
        mock_client.create_ticket.return_value = TicketResponse(
            ticket_id=None,
            status='dry_run',
        )
        mock_ticket_class.return_value = mock_client

        mock_args.dry_run = True
        result = cmd_submit(mock_config, mock_args)

        assert result == 0
        mock_client.create_ticket.assert_called_once()


class TestCmdRun:
    """Tests for run command (all-in-one)."""

    @patch('app.cli.TicketingClient')
    @patch('app.cli.SnapshotStore')
    @patch('app.cli.RADBClient')
    def test_run_success_no_changes(self, mock_radb_class, mock_store_class, mock_ticket_class, mock_config, mock_args, mock_snapshot):
        """Test run command when no changes detected."""
        # Setup RADB client mock
        mock_radb = Mock()
        mock_radb.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={'8.8.8.0/24'},
            ipv6_prefixes=set(),
            sources_queried=['RIPE'],
            errors=[],
        )
        mock_radb_class.return_value = mock_radb

        # Setup store mock - no previous snapshot means first run
        mock_store = Mock()
        mock_store.get_snapshot_before.return_value = None
        mock_store.save_snapshot.return_value = 1
        mock_store.get_snapshot_by_id.return_value = mock_snapshot
        mock_store.save_diff.return_value = 1
        mock_store_class.return_value = mock_store

        result = cmd_run(mock_config, mock_args)

        assert result == 0
        mock_radb.close.assert_called_once()
        mock_store.close.assert_called_once()

    @patch('app.cli.TicketingClient')
    @patch('app.cli.SnapshotStore')
    @patch('app.cli.RADBClient')
    def test_run_fetch_failure(self, mock_radb_class, mock_store_class, mock_ticket_class, mock_config, mock_args):
        """Test run command when fetch fails."""
        mock_radb = Mock()
        mock_radb.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes=set(),
            ipv6_prefixes=set(),
            sources_queried=[],
            errors=['Connection error'],
        )
        mock_radb_class.return_value = mock_radb

        result = cmd_run(mock_config, mock_args)

        assert result == 1
        mock_radb.close.assert_called_once()


class TestCmdRunAll:
    """Tests for run-all command."""

    @patch('app.cli.cmd_run')
    def test_run_all_no_targets(self, mock_cmd_run, mock_args):
        """Test run-all with no configured targets."""
        config = Config(targets=[])

        result = cmd_run_all(config, mock_args)

        assert result == 1
        mock_cmd_run.assert_not_called()

    @patch('app.cli.cmd_run')
    def test_run_all_success(self, mock_cmd_run, mock_config, mock_args):
        """Test run-all with successful runs."""
        mock_cmd_run.return_value = 0

        result = cmd_run_all(mock_config, mock_args)

        assert result == 0
        assert mock_cmd_run.call_count == len(mock_config.targets)

    @patch('app.cli.cmd_run')
    def test_run_all_partial_failure(self, mock_cmd_run, mock_config, mock_args):
        """Test run-all with some failures."""
        mock_cmd_run.side_effect = [0, 1]  # First succeeds, second fails

        result = cmd_run_all(mock_config, mock_args)

        assert result == 1  # Should return 1 if any failed


class TestCmdHistory:
    """Tests for history command."""

    @patch('app.cli.SnapshotStore')
    def test_history_no_snapshots(self, mock_store_class, mock_config, mock_args):
        """Test history when no snapshots exist."""
        mock_store = Mock()
        mock_store.get_snapshot_history.return_value = []
        mock_store_class.return_value = mock_store

        result = cmd_history(mock_config, mock_args)

        assert result == 0
        mock_store.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    def test_history_with_snapshots(self, mock_store_class, mock_config, mock_args, mock_snapshot):
        """Test history with existing snapshots."""
        mock_store = Mock()
        mock_store.get_snapshot_history.return_value = [mock_snapshot]
        mock_store_class.return_value = mock_store

        result = cmd_history(mock_config, mock_args)

        assert result == 0
        mock_store.get_snapshot_history.assert_called_once_with('AS15169', 10)
        mock_store.close.assert_called_once()

    @patch('app.cli.SnapshotStore')
    def test_history_json_output(self, mock_store_class, mock_config, mock_args, mock_snapshot, capsys):
        """Test history with JSON output."""
        mock_store = Mock()
        mock_store.get_snapshot_history.return_value = [mock_snapshot]
        mock_store_class.return_value = mock_store

        mock_args.json = True
        result = cmd_history(mock_config, mock_args)

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output['target'] == 'AS15169'
        assert len(output['snapshots']) == 1


class TestMain:
    """Tests for main entry point."""

    @patch('app.cli.load_config')
    @patch('app.cli.setup_logging')
    def test_main_no_command(self, mock_setup, mock_load, capsys):
        """Test main with no command."""
        with patch.object(sys, 'argv', ['irr-cli']):
            result = main()
        assert result == 1

    @patch('app.cli.load_config')
    @patch('app.cli.setup_logging')
    @patch('app.cli.cmd_init_db')
    def test_main_init_db(self, mock_cmd, mock_setup, mock_load, mock_config):
        """Test main with init-db command."""
        mock_load.return_value = mock_config
        mock_cmd.return_value = 0

        with patch.object(sys, 'argv', ['irr-cli', 'init-db']):
            result = main()

        assert result == 0
        mock_cmd.assert_called_once()

    @patch('app.cli.load_config')
    def test_main_config_not_found(self, mock_load, capsys):
        """Test main when config file not found."""
        mock_load.side_effect = FileNotFoundError("Config not found")

        with patch.object(sys, 'argv', ['irr-cli', 'init-db']):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert 'ERROR' in captured.err

    @patch('app.cli.load_config')
    @patch('app.cli.setup_logging')
    @patch('app.cli.cmd_fetch')
    def test_main_keyboard_interrupt(self, mock_cmd, mock_setup, mock_load, mock_config):
        """Test main handles keyboard interrupt."""
        mock_load.return_value = mock_config
        mock_cmd.side_effect = KeyboardInterrupt()

        with patch.object(sys, 'argv', ['irr-cli', 'fetch', '-t', 'AS15169']):
            result = main()

        assert result == 130


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_timestamp_str(self):
        """Test timestamp string generation."""
        ts = get_timestamp_str()
        assert isinstance(ts, str)
        # Should be in format YYYY-MM-DD HH:MM:SS
        assert len(ts) == 19

    def test_print_output_quiet_mode(self, capsys):
        """Test print_output respects quiet mode."""
        print_output("Test message", quiet=True)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_output_normal_mode(self, capsys):
        """Test print_output in normal mode."""
        print_output("Test message", quiet=False)
        captured = capsys.readouterr()
        assert "Test message" in captured.out
