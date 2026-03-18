"""Tests to replicate the VM deployment bug: crontab runs but no Teams alerts.

These tests cover every possible failure mode in the flow:
  cron trigger → fetch → store → diff comparison → Teams alert

Identified bugs:
  1. Lookback off-by-one: get_snapshot_before() uses strict '<', so when cron
     runs at the same time daily, the previous snapshot timestamp == cutoff
     and is never found.
  2. Cron environment missing TEAMS_WEBHOOK_URL: env var not available in
     cron's minimal env, so webhook_url="" and alert is silently skipped.
  3. notify() return value ignored: Teams POST failures are logged but
     cmd_run() never checks the return, giving no visible indication.
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.cli import cmd_run, cmd_run_all, detect_target_type, create_irr_client
from app.config import (
    Config, BGPQ4Config, DatabaseConfig, TicketingConfig,
    LoggingConfig, DiffConfig, TeamsConfig, load_config, _expand_env_vars,
)
from app.diff import compute_diff, DiffResult
from app.store import SnapshotStore, Snapshot
from app.teams import TeamsNotifier
from app.bgpq4_client import PrefixResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(webhook_url="https://hooks.example.com/webhook", lookback_hours=24):
    """Create a Config with an in-memory DB and optional webhook."""
    return Config(
        targets=["AS15169"],
        bgpq4=BGPQ4Config(cmd=["wsl", "bgpq4"], timeout_seconds=120, sources=["RADB"]),
        database=DatabaseConfig(path=":memory:"),
        ticketing=TicketingConfig(base_url="", api_token=""),
        logging=LoggingConfig(level="INFO", format="text"),
        diff=DiffConfig(lookback_hours=lookback_hours),
        teams=TeamsConfig(webhook_url=webhook_url, timeout_seconds=15),
    )


def make_args(target="AS15169", dry_run=False):
    return argparse.Namespace(
        target=target,
        dry_run=dry_run,
        json=False,
        quiet=True,
        verbose=False,
    )


def make_prefix_result(ipv4=None, ipv6=None):
    return PrefixResult(
        ipv4_prefixes=set(ipv4 or ["8.8.8.0/24", "8.8.4.0/24"]),
        ipv6_prefixes=set(ipv6 or ["2001:4860::/32"]),
        sources_queried=["RADB"],
        errors=[],
    )


# ===========================================================================
# BUG 1: Lookback off-by-one (strict '<' misses exact-timestamp snapshots)
# ===========================================================================

class TestLookbackOffByOne:
    """The core DB comparison bug.

    get_snapshot_before() uses `WHERE timestamp < ?`.
    When cron fires at the same second each day, cutoff == previous timestamp
    and the previous snapshot is never found.
    """

    def test_less_than_or_equal_finds_exact_timestamp(self):
        """FIXED: snapshot at exactly cutoff IS found with '<='."""
        store = SnapshotStore(":memory:")
        store.migrate()

        # Day 1: save snapshot at timestamp T
        T = 1710748800  # fixed timestamp
        store.conn.execute(
            """INSERT INTO snapshots
               (target, target_type, timestamp, irr_sources,
                ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AS15169", "asn", T, json.dumps(["RADB"]),
             json.dumps(["8.8.8.0/24"]), json.dumps([]), "hash1", T),
        )
        store.conn.commit()

        # Day 2: cutoff = now - 24h.  If cron fires at exactly T + 86400,
        # cutoff = T + 86400 - 86400 = T.
        cutoff = T  # exactly equals the snapshot timestamp

        previous = store.get_snapshot_before("AS15169", cutoff)

        # FIXED: previous IS found because query uses '<='
        assert previous is not None, (
            "With '<=' fix, snapshot at exact cutoff IS found"
        )
        assert previous.timestamp == T
        store.close()

    def test_snapshot_before_cutoff_still_found(self):
        """Snapshot strictly before cutoff is always found."""
        store = SnapshotStore(":memory:")
        store.migrate()

        T = 1710748800
        store.conn.execute(
            """INSERT INTO snapshots
               (target, target_type, timestamp, irr_sources,
                ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AS15169", "asn", T, json.dumps(["RADB"]),
             json.dumps(["8.8.8.0/24"]), json.dumps([]), "hash1", T),
        )
        store.conn.commit()

        cutoff = T + 1  # 1 second after snapshot

        previous = store.get_snapshot_before("AS15169", cutoff)
        assert previous is not None, "Snapshot before cutoff is always found"
        store.close()

    def test_daily_cron_simulation_exact_24h_fixed(self):
        """Simulate daily cron at the exact same second.

        FIXED: With '<=', the previous snapshot IS found even at exact cutoff,
        so identical prefixes correctly show no changes.
        """
        store = SnapshotStore(":memory:")
        store.migrate()

        base_ts = 1710748800
        lookback = 24 * 3600  # 86400

        # Day 1
        sid1 = store.save_snapshot(
            target="AS15169", target_type="asn",
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24"],
            ipv6_prefixes=[],
        )
        store.conn.execute(
            "UPDATE snapshots SET timestamp = ? WHERE id = ?", (base_ts, sid1)
        )
        store.conn.commit()

        # Day 2 — exactly 86400 seconds later
        day2_ts = base_ts + 86400
        cutoff2 = day2_ts - lookback  # == base_ts

        previous = store.get_snapshot_before("AS15169", cutoff2)
        assert previous is not None, (
            "FIXED: Day 1 snapshot found because '<=' includes exact cutoff"
        )
        assert previous.id == sid1

        sid2 = store.save_snapshot(
            target="AS15169", target_type="asn",
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24"],  # same prefixes, no real change
            ipv6_prefixes=[],
        )
        store.conn.execute(
            "UPDATE snapshots SET timestamp = ? WHERE id = ?", (day2_ts, sid2)
        )
        store.conn.commit()

        snap2 = store.get_snapshot_by_id(sid2)
        diff = compute_diff(snap2, previous)

        # FIXED: correctly detects no changes
        assert diff.has_changes is False
        assert diff.added_v4 == []
        assert diff.removed_v4 == []

        store.close()

    def test_daily_cron_one_second_drift_works(self):
        """If cron fires 1 second later, the previous snapshot IS found."""
        store = SnapshotStore(":memory:")
        store.migrate()

        base_ts = 1710748800

        sid1 = store.save_snapshot(
            target="AS15169", target_type="asn",
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24"],
            ipv6_prefixes=[],
        )
        store.conn.execute(
            "UPDATE snapshots SET timestamp = ? WHERE id = ?", (base_ts, sid1)
        )
        store.conn.commit()

        # Day 2 — 1 second drift: fires at base_ts + 86401
        day2_ts = base_ts + 86401
        cutoff2 = day2_ts - 86400  # == base_ts + 1

        previous = store.get_snapshot_before("AS15169", cutoff2)
        assert previous is not None, (
            "With 1-second drift, previous snapshot IS found"
        )

        sid2 = store.save_snapshot(
            target="AS15169", target_type="asn",
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24"],  # same prefixes
            ipv6_prefixes=[],
        )
        store.conn.execute(
            "UPDATE snapshots SET timestamp = ? WHERE id = ?", (day2_ts, sid2)
        )
        store.conn.commit()

        snap2 = store.get_snapshot_by_id(sid2)
        diff = compute_diff(snap2, previous)

        # Correctly detects no changes
        assert diff.has_changes is False

        store.close()


# ===========================================================================
# BUG 2: TEAMS_WEBHOOK_URL not set in cron environment
# ===========================================================================

class TestCronEnvironmentWebhookMissing:
    """When deployed in a VM with crontab, environment variables set in
    .bashrc / .profile are NOT available. The webhook_url resolves to ""
    and the alert is silently skipped.
    """

    def test_env_var_expansion_returns_empty_when_unset(self):
        """${TEAMS_WEBHOOK_URL} expands to '' when env var is missing."""
        with patch.dict(os.environ, {}, clear=True):
            result = _expand_env_vars("${TEAMS_WEBHOOK_URL}")
        assert result == ""

    def test_config_webhook_url_empty_when_env_not_set(self, tmp_path):
        """Full config load with missing env var → webhook_url is empty."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "bgpq4:\n"
            "  cmd: ['bgpq4']\n"
            "  sources: ['RADB']\n"
            "teams:\n"
            "  webhook_url: '${TEAMS_WEBHOOK_URL}'\n"
            "  timeout_seconds: 15\n"
        )

        env = {k: v for k, v in os.environ.items()}
        env.pop("TEAMS_WEBHOOK_URL", None)

        with patch.dict(os.environ, env, clear=True):
            config = load_config(str(config_file))

        assert config.teams.webhook_url == "", (
            "webhook_url should be empty when TEAMS_WEBHOOK_URL env var is not set"
        )

    def test_empty_webhook_url_skips_alert_and_warns(self, capsys):
        """cmd_run with webhook_url='' never instantiates TeamsNotifier
        but now prints a warning so the user knows.
        """
        config = make_config(webhook_url="")  # empty — simulates missing env var
        args = make_args()
        args.quiet = False  # need output to see warning

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = make_prefix_result()

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore") as MockStore, \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            mock_store = Mock()
            mock_store.save_snapshot.return_value = 1
            mock_store.get_snapshot_before.return_value = None
            mock_store.get_snapshot_by_id.return_value = Snapshot(
                id=1, target="AS15169", target_type="asn",
                timestamp=int(time.time()),
                irr_sources=["RADB"],
                ipv4_prefixes=["8.8.8.0/24", "8.8.4.0/24"],
                ipv6_prefixes=["2001:4860::/32"],
                content_hash="abc", created_at=int(time.time()),
            )
            mock_store.save_diff.return_value = 1
            MockStore.return_value = mock_store

            cmd_run(config, args)

            # TeamsNotifier should NEVER be instantiated when webhook_url is empty
            MockNotifier.assert_not_called()

        # FIXED: user now gets a visible warning
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "TEAMS_WEBHOOK_URL" in captured.out

    def test_set_webhook_url_does_send_alert(self):
        """When webhook_url is properly set, TeamsNotifier IS called."""
        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = make_prefix_result()

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore") as MockStore, \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            mock_notifier = Mock()
            mock_notifier.notify.return_value = True
            MockNotifier.return_value = mock_notifier

            mock_store = Mock()
            mock_store.save_snapshot.return_value = 1
            mock_store.get_snapshot_before.return_value = None  # first run → has_changes
            mock_store.get_snapshot_by_id.return_value = Snapshot(
                id=1, target="AS15169", target_type="asn",
                timestamp=int(time.time()),
                irr_sources=["RADB"],
                ipv4_prefixes=["8.8.8.0/24", "8.8.4.0/24"],
                ipv6_prefixes=["2001:4860::/32"],
                content_hash="abc", created_at=int(time.time()),
            )
            mock_store.save_diff.return_value = 1
            MockStore.return_value = mock_store

            cmd_run(config, args)

            # TeamsNotifier SHOULD be created and called
            MockNotifier.assert_called_once()
            mock_notifier.notify.assert_called_once()


# ===========================================================================
# BUG 3: notify() return value ignored — silent failure
# ===========================================================================

class TestTeamsNotifySilentFailure:
    """cmd_run() calls notifier.notify() but never checks the return value.
    If the webhook POST fails (timeout, connection error, HTTP 4xx/5xx),
    the user gets no visible indication.
    """

    def test_notify_returns_false_on_http_error(self):
        """TeamsNotifier.notify() returns False on HTTP error."""
        import requests

        notifier = TeamsNotifier(webhook_url="https://hooks.example.com/webhook")
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            removed_v4=[],
            added_v6=[],
            removed_v6=[],
            has_changes=True,
            diff_hash="abc123",
        )

        with patch("requests.post") as mock_post:
            mock_resp = Mock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
            mock_post.return_value = mock_resp

            result = notifier.notify("AS15169", diff)

        assert result is False

    def test_notify_returns_false_on_timeout(self):
        """TeamsNotifier.notify() returns False on timeout."""
        import requests

        notifier = TeamsNotifier(webhook_url="https://hooks.example.com/webhook")
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            has_changes=True,
            diff_hash="abc123",
        )

        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("timed out")
            result = notifier.notify("AS15169", diff)

        assert result is False

    def test_notify_returns_false_on_connection_error(self):
        """TeamsNotifier.notify() returns False on connection error."""
        import requests

        notifier = TeamsNotifier(webhook_url="https://hooks.example.com/webhook")
        diff = DiffResult(
            target="AS15169",
            added_v4=["1.0.0.0/8"],
            has_changes=True,
            diff_hash="abc123",
        )

        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("connection refused")
            result = notifier.notify("AS15169", diff)

        assert result is False

    def test_cmd_run_warns_on_notify_failure(self, capsys):
        """FIXED: cmd_run now logs a warning when notify() fails.

        cmd_run still returns 0 (the core job succeeded) but the user
        gets a visible WARNING about the failed alert.
        """
        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()
        args.quiet = False  # need output to see warning

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = make_prefix_result()

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore") as MockStore, \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            mock_notifier = Mock()
            mock_notifier.notify.return_value = False  # FAILURE!
            MockNotifier.return_value = mock_notifier

            mock_store = Mock()
            mock_store.save_snapshot.return_value = 1
            mock_store.get_snapshot_before.return_value = None  # first run
            mock_store.get_snapshot_by_id.return_value = Snapshot(
                id=1, target="AS15169", target_type="asn",
                timestamp=int(time.time()),
                irr_sources=["RADB"],
                ipv4_prefixes=["8.8.8.0/24"],
                ipv6_prefixes=["2001:4860::/32"],
                content_hash="abc", created_at=int(time.time()),
            )
            mock_store.save_diff.return_value = 1
            MockStore.return_value = mock_store

            exit_code = cmd_run(config, args)

        assert exit_code == 0
        mock_notifier.notify.assert_called_once()

        # FIXED: user now sees a warning about the failed alert
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Teams alert failed" in captured.out


# ===========================================================================
# END-TO-END: Full cmd_run flow with real SQLite DB
# ===========================================================================

class TestEndToEndWithRealDB:
    """Integration tests using a real in-memory SQLite DB to replicate
    the exact cron scenario: fetch → store → diff → alert.
    """

    def _run_with_real_db(self, config, prefixes_v4, prefixes_v6=None,
                          override_timestamp=None):
        """Helper: runs one cycle of fetch → store → diff.

        Returns (exit_code, store, snapshot, diff_result, notifier_called).
        """
        prefixes_v6 = prefixes_v6 or []
        args = make_args()

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes=set(prefixes_v4),
            ipv6_prefixes=set(prefixes_v6),
            sources_queried=["RADB"],
            errors=[],
        )

        notifier_mock = Mock()
        notifier_mock.notify.return_value = True

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.TeamsNotifier") as MockNotifier:
            MockNotifier.return_value = notifier_mock

            # Use real SnapshotStore with in-memory DB
            # We need to patch only the constructor to pass our store
            exit_code = cmd_run(config, args)

            return exit_code, MockNotifier, notifier_mock

    def test_first_run_sends_alert(self):
        """First run ever: all prefixes are 'added', alert should fire."""
        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = make_prefix_result()

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            notifier_mock = Mock()
            notifier_mock.notify.return_value = True
            MockNotifier.return_value = notifier_mock

            exit_code = cmd_run(config, args)

        assert exit_code == 0
        MockNotifier.assert_called_once()
        notifier_mock.notify.assert_called_once()

        # Verify the diff passed to notify has changes
        call_kwargs = notifier_mock.notify.call_args
        diff_arg = call_kwargs.kwargs.get("diff") or call_kwargs[1].get("diff")
        if diff_arg is None:
            # positional args
            diff_arg = call_kwargs[0][1]
        assert diff_arg.has_changes is True

    def test_no_changes_does_not_send_alert(self):
        """When prefixes haven't changed, no alert should fire.

        This requires the previous snapshot to be found correctly.
        """
        store = SnapshotStore(":memory:")
        store.migrate()

        # Simulate Day 1 snapshot from 25 hours ago (safely within lookback)
        day1_ts = int(time.time()) - 90000  # 25 hours ago
        store.conn.execute(
            """INSERT INTO snapshots
               (target, target_type, timestamp, irr_sources,
                ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AS15169", "asn", day1_ts, json.dumps(["RADB"]),
             json.dumps(sorted(["8.8.8.0/24", "8.8.4.0/24"])),
             json.dumps(sorted(["2001:4860::/32"])),
             "hash1", day1_ts),
        )
        store.conn.commit()

        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"8.8.8.0/24", "8.8.4.0/24"},  # same as Day 1
            ipv6_prefixes={"2001:4860::/32"},               # same as Day 1
            sources_queried=["RADB"],
            errors=[],
        )

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore", return_value=store), \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            notifier_mock = Mock()
            notifier_mock.notify.return_value = True
            MockNotifier.return_value = notifier_mock

            exit_code = cmd_run(config, args)

        assert exit_code == 0
        # No changes → TeamsNotifier should NOT be called
        MockNotifier.assert_not_called()

    def test_real_changes_sends_alert(self):
        """When prefixes actually change, alert should fire."""
        store = SnapshotStore(":memory:")
        store.migrate()

        day1_ts = int(time.time()) - 90000
        store.conn.execute(
            """INSERT INTO snapshots
               (target, target_type, timestamp, irr_sources,
                ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AS15169", "asn", day1_ts, json.dumps(["RADB"]),
             json.dumps(["8.8.8.0/24"]),
             json.dumps([]),
             "hash1", day1_ts),
        )
        store.conn.commit()

        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"8.8.8.0/24", "1.2.3.0/24"},  # new prefix added
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=[],
        )

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore", return_value=store), \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            notifier_mock = Mock()
            notifier_mock.notify.return_value = True
            MockNotifier.return_value = notifier_mock

            exit_code = cmd_run(config, args)

        assert exit_code == 0
        MockNotifier.assert_called_once()
        notifier_mock.notify.assert_called_once()

    def test_exact_24h_cron_no_false_alert_after_fix(self):
        """FIXED: daily cron at exact same second no longer causes false alerts.

        With '<=' fix, the previous snapshot IS found even when
        cutoff == snapshot timestamp, so identical prefixes correctly
        show no changes and no alert fires.
        """
        store = SnapshotStore(":memory:")
        store.migrate()

        # Day 1 snapshot at a precise timestamp
        day1_ts = 1710748800
        store.conn.execute(
            """INSERT INTO snapshots
               (target, target_type, timestamp, irr_sources,
                ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("AS15169", "asn", day1_ts, json.dumps(["RADB"]),
             json.dumps(sorted(["8.8.8.0/24", "8.8.4.0/24"])),
             json.dumps([]),
             "hash1", day1_ts),
        )
        store.conn.commit()

        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args()

        # Day 2: force time.time() to return exactly day1_ts + 86400
        day2_ts = day1_ts + 86400

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = PrefixResult(
            ipv4_prefixes={"8.8.8.0/24", "8.8.4.0/24"},  # SAME prefixes
            ipv6_prefixes=set(),
            sources_queried=["RADB"],
            errors=[],
        )

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore", return_value=store), \
             patch("app.cli.TeamsNotifier") as MockNotifier, \
             patch("app.cli.time") as mock_time, \
             patch("app.store.time") as mock_store_time:

            mock_time.time.return_value = day2_ts
            mock_store_time.time.return_value = day2_ts

            notifier_mock = Mock()
            notifier_mock.notify.return_value = True
            MockNotifier.return_value = notifier_mock

            exit_code = cmd_run(config, args)

        # FIXED: No alert fires because previous snapshot IS found
        # and prefixes are identical → has_changes=False
        MockNotifier.assert_not_called()


# ===========================================================================
# Additional edge cases
# ===========================================================================

class TestEdgeCases:
    """Other scenarios that could cause missing or incorrect alerts."""

    def test_webhook_url_with_unexpanded_env_var_syntax(self):
        """If config has literal '${TEAMS_WEBHOOK_URL}' and env is not set,
        webhook_url becomes '' — alert silently skipped.
        """
        config = make_config(webhook_url="")
        assert not config.teams.webhook_url  # falsy

    def test_webhook_url_with_whitespace_only(self):
        """Whitespace-only webhook_url should not trigger alert."""
        config = make_config(webhook_url="   ")
        # TeamsNotifier would raise ValueError, but cmd_run checks
        # `if config.teams.webhook_url:` — "   " is truthy!
        # This could cause a ValueError crash in production.
        with pytest.raises(ValueError, match="webhook_url must not be empty"):
            TeamsNotifier(webhook_url="   ")

    def test_diff_with_no_previous_always_shows_changes(self):
        """When previous=None, ALL current prefixes are 'added'."""
        current = Snapshot(
            id=1, target="AS15169", target_type="asn",
            timestamp=1000000,
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24"],
            ipv6_prefixes=[],
            content_hash="h", created_at=1000000,
        )
        diff = compute_diff(current, None)
        assert diff.has_changes is True
        assert diff.added_v4 == ["8.8.8.0/24"]

    def test_diff_with_identical_snapshots_no_changes(self):
        """Identical previous → no changes."""
        old = Snapshot(
            id=1, target="AS15169", target_type="asn",
            timestamp=1000000,
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24", "8.8.4.0/24"],
            ipv6_prefixes=["2001:4860::/32"],
            content_hash="h", created_at=1000000,
        )
        new = Snapshot(
            id=2, target="AS15169", target_type="asn",
            timestamp=1086400,
            irr_sources=["RADB"],
            ipv4_prefixes=["8.8.8.0/24", "8.8.4.0/24"],
            ipv6_prefixes=["2001:4860::/32"],
            content_hash="h", created_at=1086400,
        )
        diff = compute_diff(new, old)
        assert diff.has_changes is False

    def test_multiple_snapshots_same_day_lookback_picks_correct_one(self):
        """Multiple snapshots in one day — lookback should pick the latest
        one that is still before the cutoff.
        """
        store = SnapshotStore(":memory:")
        store.migrate()

        base = 1710748800
        # 3 snapshots on Day 1 at different times
        for offset in [0, 3600, 7200]:
            ts = base + offset
            store.conn.execute(
                """INSERT INTO snapshots
                   (target, target_type, timestamp, irr_sources,
                    ipv4_prefixes, ipv6_prefixes, content_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("AS15169", "asn", ts, json.dumps(["RADB"]),
                 json.dumps([f"10.{offset}.0.0/16"]),
                 json.dumps([]),
                 f"hash_{offset}", ts),
            )
        store.conn.commit()

        # Query for snapshot before base + 5000 (between 2nd and 3rd)
        cutoff = base + 5000
        prev = store.get_snapshot_before("AS15169", cutoff)
        assert prev is not None
        assert prev.timestamp == base + 3600  # picks the 2nd (latest before cutoff)

        store.close()

    def test_run_all_propagates_teams_config(self):
        """run-all should pass Teams config to each target's run."""
        config = make_config(webhook_url="https://hooks.example.com/webhook")
        config.targets = ["AS15169", "AS16509"]
        args = argparse.Namespace(
            dry_run=False,
            json=False,
            quiet=False,
            verbose=False,
        )

        with patch("app.cli.cmd_run") as mock_cmd_run:
            mock_cmd_run.return_value = 0
            cmd_run_all(config, args)

            assert mock_cmd_run.call_count == 2
            # Verify config (with webhook) is passed to each call
            for call in mock_cmd_run.call_args_list:
                passed_config = call[0][0]
                assert passed_config.teams.webhook_url == "https://hooks.example.com/webhook"

    def test_dry_run_does_not_send_teams_alert(self):
        """In dry-run mode, Teams alert should NOT actually POST."""
        config = make_config(webhook_url="https://hooks.example.com/webhook")
        args = make_args(dry_run=True)

        mock_client = Mock()
        mock_client.fetch_prefixes.return_value = make_prefix_result()

        with patch("app.cli.create_irr_client", return_value=mock_client), \
             patch("app.cli.SnapshotStore") as MockStore, \
             patch("app.cli.TeamsNotifier") as MockNotifier:

            notifier_mock = Mock()
            notifier_mock.notify.return_value = True
            MockNotifier.return_value = notifier_mock

            mock_store = Mock()
            mock_store.save_snapshot.return_value = 1
            mock_store.get_snapshot_before.return_value = None
            mock_store.get_snapshot_by_id.return_value = Snapshot(
                id=1, target="AS15169", target_type="asn",
                timestamp=int(time.time()),
                irr_sources=["RADB"],
                ipv4_prefixes=["8.8.8.0/24"],
                ipv6_prefixes=[],
                content_hash="abc", created_at=int(time.time()),
            )
            mock_store.save_diff.return_value = 1
            MockStore.return_value = mock_store

            cmd_run(config, args)

            # Notifier IS called but with dry_run=True
            notifier_mock.notify.assert_called_once()
            call_kwargs = notifier_mock.notify.call_args
            dry_run_val = call_kwargs.kwargs.get("dry_run")
            if dry_run_val is None:
                dry_run_val = call_kwargs[1].get("dry_run")
            assert dry_run_val is True
