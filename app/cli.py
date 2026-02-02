"""CLI entry point for IRR Automation."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import load_config, Config, LoggingConfig
from app.logger import setup_logging, get_logger
from app.store import SnapshotStore
from app.radb_client import RADBClient
from app.diff import compute_diff, format_diff_human, format_diff_json, DiffResult
from app.ticketing import TicketingClient


def get_timestamp_str() -> str:
    """Get current timestamp as formatted string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def print_output(message: str, json_mode: bool = False, quiet: bool = False):
    """Print output respecting quiet mode."""
    if not quiet:
        if json_mode:
            pass  # JSON output is handled separately
        else:
            print(f"[{get_timestamp_str()}] {message}")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog='irr-cli',
        description='IRR Prefix Change Detection & Ticket Automation'
    )

    # Global options
    parser.add_argument(
        '-c', '--config',
        default='./config.yaml',
        help='Path to configuration file (default: ./config.yaml)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress non-error output'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # init-db command
    init_parser = subparsers.add_parser(
        'init-db',
        help='Initialize the database'
    )

    # fetch command
    fetch_parser = subparsers.add_parser(
        'fetch',
        help='Fetch prefixes and store snapshot'
    )
    fetch_parser.add_argument(
        '--target', '-t',
        required=True,
        help='ASN to fetch (e.g., AS15169)'
    )

    # diff command
    diff_parser = subparsers.add_parser(
        'diff',
        help='Compute diff against previous snapshot'
    )
    diff_parser.add_argument(
        '--target', '-t',
        required=True,
        help='ASN to diff (e.g., AS15169)'
    )

    # submit command
    submit_parser = subparsers.add_parser(
        'submit',
        help='Submit ticket for detected changes'
    )
    submit_parser.add_argument(
        '--target', '-t',
        required=True,
        help='ASN to submit ticket for (e.g., AS15169)'
    )
    submit_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Do not actually create the ticket'
    )

    # run command (all-in-one)
    run_parser = subparsers.add_parser(
        'run',
        help='Fetch, diff, and submit ticket if changes detected'
    )
    run_parser.add_argument(
        '--target', '-t',
        required=True,
        help='ASN to process (e.g., AS15169)'
    )
    run_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Do not actually create the ticket'
    )

    # run-all command
    run_all_parser = subparsers.add_parser(
        'run-all',
        help='Run for all configured targets'
    )
    run_all_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Do not actually create tickets'
    )

    # history command
    history_parser = subparsers.add_parser(
        'history',
        help='Show snapshot history'
    )
    history_parser.add_argument(
        '--target', '-t',
        required=True,
        help='ASN to show history for (e.g., AS15169)'
    )
    history_parser.add_argument(
        '--limit', '-l',
        type=int,
        default=10,
        help='Maximum number of snapshots to show (default: 10)'
    )

    return parser


def cmd_init_db(config: Config, args: argparse.Namespace) -> int:
    """Initialize the database."""
    logger = get_logger('cli')

    print_output("Initializing database...", args.json, args.quiet)

    store = SnapshotStore(config.database.path)
    store.migrate()
    store.close()

    print_output(f"Database initialized at {config.database.path}", args.json, args.quiet)

    if args.json:
        print(json.dumps({
            'status': 'success',
            'database_path': config.database.path,
        }))

    return 0


def cmd_fetch(config: Config, args: argparse.Namespace) -> int:
    """Fetch prefixes and store snapshot."""
    logger = get_logger('cli')
    target = args.target.upper()

    print_output(f"Fetching prefixes for {target}...", args.json, args.quiet)

    # Fetch prefixes
    client = RADBClient(
        base_url=config.radb.base_url,
        timeout=config.radb.timeout_seconds,
        max_retries=config.radb.max_retries,
    )

    try:
        result = client.fetch_prefixes(target, config.irr_sources)
    finally:
        client.close()

    if result.errors and not result.ipv4_prefixes and not result.ipv6_prefixes:
        print_output(f"ERROR: Failed to fetch prefixes: {result.errors}", args.json, args.quiet)
        return 1

    # Store snapshot
    store = SnapshotStore(config.database.path)
    store.migrate()

    try:
        snapshot_id = store.save_snapshot(
            target=target,
            target_type='asn',
            irr_sources=result.sources_queried,
            ipv4_prefixes=list(result.ipv4_prefixes),
            ipv6_prefixes=list(result.ipv6_prefixes),
        )

        snapshot = store.get_snapshot_by_id(snapshot_id)
    finally:
        store.close()

    print_output(
        f"Found {len(result.ipv4_prefixes):,} IPv4 prefixes, "
        f"{len(result.ipv6_prefixes):,} IPv6 prefixes",
        args.json, args.quiet
    )
    print_output(f"Snapshot saved (id: {snapshot_id}, hash: {snapshot.content_hash[:12]}...)", args.json, args.quiet)

    if args.json:
        print(json.dumps({
            'target': target,
            'snapshot': {
                'id': snapshot_id,
                'ipv4_count': len(result.ipv4_prefixes),
                'ipv6_count': len(result.ipv6_prefixes),
                'hash': snapshot.content_hash,
                'sources': result.sources_queried,
            },
            'errors': result.errors,
        }))

    return 0


def cmd_diff(config: Config, args: argparse.Namespace) -> int:
    """Compute diff against previous snapshot."""
    logger = get_logger('cli')
    target = args.target.upper()

    store = SnapshotStore(config.database.path)
    store.migrate()

    try:
        # Get latest snapshot
        current = store.get_latest_snapshot(target)
        if not current:
            print_output(f"ERROR: No snapshot found for {target}", args.json, args.quiet)
            return 1

        # Get previous snapshot (based on lookback window)
        # Find the most recent snapshot that is older than (current - lookback)
        lookback_seconds = config.diff.lookback_hours * 3600
        cutoff_time = current.timestamp - lookback_seconds
        previous = store.get_snapshot_before(target, cutoff_time)

        # Compute diff
        diff = compute_diff(current, previous)

    finally:
        store.close()

    if args.json:
        print(json.dumps(format_diff_json(diff)))
    else:
        if previous:
            prev_time = datetime.fromtimestamp(previous.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            print_output(f"Comparing with previous snapshot ({prev_time})", args.json, args.quiet)
        else:
            print_output("No previous snapshot found (first run)", args.json, args.quiet)

        print(format_diff_human(diff))

    return 0


def cmd_submit(config: Config, args: argparse.Namespace) -> int:
    """Submit ticket for detected changes."""
    logger = get_logger('cli')
    target = args.target.upper()
    dry_run = args.dry_run

    store = SnapshotStore(config.database.path)
    store.migrate()

    try:
        # Get latest diff
        diff_record = store.get_latest_diff(target)
        if not diff_record:
            print_output(f"ERROR: No diff found for {target}. Run 'diff' command first.", args.json, args.quiet)
            return 1

        if not diff_record.has_changes:
            print_output(f"No changes to submit for {target}", args.json, args.quiet)
            if args.json:
                print(json.dumps({
                    'target': target,
                    'status': 'no_changes',
                }))
            return 0

        # Check if ticket already exists for this diff
        existing_ticket = store.get_ticket_for_diff(diff_record.id)
        if existing_ticket and existing_ticket.status in ('submitted', 'created'):
            print_output(
                f"Ticket already exists for this diff: {existing_ticket.external_ticket_id}",
                args.json, args.quiet
            )
            if args.json:
                print(json.dumps({
                    'target': target,
                    'status': 'already_submitted',
                    'ticket_id': existing_ticket.external_ticket_id,
                }))
            return 0

        # Create diff result from stored diff
        diff_result = DiffResult(
            target=target,
            added_v4=diff_record.added_v4,
            removed_v4=diff_record.removed_v4,
            added_v6=diff_record.added_v6,
            removed_v6=diff_record.removed_v6,
            has_changes=diff_record.has_changes,
            diff_hash=diff_record.diff_hash,
            new_snapshot_id=diff_record.new_snapshot_id,
            old_snapshot_id=diff_record.old_snapshot_id,
        )

        # Get IRR sources from snapshot
        snapshot = store.get_snapshot_by_id(diff_record.new_snapshot_id)
        irr_sources = snapshot.irr_sources if snapshot else config.irr_sources

        # Submit ticket
        client = TicketingClient(
            base_url=config.ticketing.base_url,
            api_token=config.ticketing.api_token,
            timeout=config.ticketing.timeout_seconds,
            max_retries=config.ticketing.max_retries,
        )

        try:
            # Get payload for storage
            payload = client.get_payload(target, diff_result, irr_sources)

            # Save pending ticket
            ticket_id = store.save_ticket(
                diff_id=diff_record.id,
                target=target,
                status='pending',
                request_payload=payload,
            )

            # Submit
            response = client.create_ticket(target, diff_result, irr_sources, dry_run=dry_run)

            # Update ticket status
            store.update_ticket_status(
                ticket_id=ticket_id,
                status=response.status,
                response_payload={
                    'ticket_id': response.ticket_id,
                    'error_message': response.error_message,
                },
                external_ticket_id=response.ticket_id,
            )

        finally:
            client.close()

        if dry_run:
            print_output(f"[DRY-RUN] Would create ticket for {target}", args.json, args.quiet)
        elif response.status == 'created':
            print_output(f"Ticket created: {response.ticket_id}", args.json, args.quiet)
        elif response.status == 'duplicate':
            print_output(f"Ticket already exists: {response.ticket_id}", args.json, args.quiet)
        else:
            print_output(f"ERROR: Failed to create ticket: {response.error_message}", args.json, args.quiet)

        if args.json:
            print(json.dumps({
                'target': target,
                'status': response.status,
                'ticket_id': response.ticket_id,
                'is_duplicate': response.is_duplicate,
                'error_message': response.error_message,
                'dry_run': dry_run,
            }))

        return 0 if response.status in ('created', 'duplicate', 'dry_run') else 1

    finally:
        store.close()


def cmd_run(config: Config, args: argparse.Namespace) -> int:
    """All-in-one: fetch, diff, and submit if changes detected."""
    logger = get_logger('cli')
    target = args.target.upper()
    dry_run = args.dry_run

    print_output(f"Processing {target}...", args.json, args.quiet)

    # Step 1: Fetch
    print_output(f"Fetching prefixes for {target}...", args.json, args.quiet)

    client = RADBClient(
        base_url=config.radb.base_url,
        timeout=config.radb.timeout_seconds,
        max_retries=config.radb.max_retries,
    )

    try:
        fetch_result = client.fetch_prefixes(target, config.irr_sources)
    finally:
        client.close()

    if fetch_result.errors and not fetch_result.ipv4_prefixes and not fetch_result.ipv6_prefixes:
        print_output(f"ERROR: Failed to fetch prefixes: {fetch_result.errors}", args.json, args.quiet)
        return 1

    print_output(
        f"Found {len(fetch_result.ipv4_prefixes):,} IPv4, "
        f"{len(fetch_result.ipv6_prefixes):,} IPv6 prefixes",
        args.json, args.quiet
    )

    # Step 2: Store snapshot
    store = SnapshotStore(config.database.path)
    store.migrate()

    try:
        # Get previous snapshot before saving new one
        # Find the most recent snapshot that is older than (now - lookback)
        lookback_seconds = config.diff.lookback_hours * 3600
        current_time = int(time.time())
        cutoff_time = current_time - lookback_seconds
        previous = store.get_snapshot_before(target, cutoff_time)

        # Save new snapshot
        snapshot_id = store.save_snapshot(
            target=target,
            target_type='asn',
            irr_sources=fetch_result.sources_queried,
            ipv4_prefixes=list(fetch_result.ipv4_prefixes),
            ipv6_prefixes=list(fetch_result.ipv6_prefixes),
        )
        snapshot = store.get_snapshot_by_id(snapshot_id)

        print_output(f"Snapshot saved (hash: {snapshot.content_hash[:12]}...)", args.json, args.quiet)

        # Step 3: Compute diff
        diff = compute_diff(snapshot, previous)

        if previous:
            prev_time = datetime.fromtimestamp(previous.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            print_output(f"Comparing with previous snapshot ({prev_time})", args.json, args.quiet)
        else:
            print_output("No previous snapshot found (first run)", args.json, args.quiet)

        # Store diff
        diff_id = store.save_diff(
            new_snapshot_id=snapshot_id,
            old_snapshot_id=previous.id if previous else None,
            target=target,
            added_v4=diff.added_v4,
            removed_v4=diff.removed_v4,
            added_v6=diff.added_v6,
            removed_v6=diff.removed_v6,
            diff_hash=diff.diff_hash,
        )

        # Print diff summary
        if not args.json and not args.quiet:
            print("Changes detected:" if diff.has_changes else "No changes detected")
            if diff.added_v4:
                print(f"  - Added IPv4: {len(diff.added_v4)} prefixes")
            if diff.removed_v4:
                print(f"  - Removed IPv4: {len(diff.removed_v4)} prefixes")
            if diff.added_v6:
                print(f"  - Added IPv6: {len(diff.added_v6)} prefixes")
            if diff.removed_v6:
                print(f"  - Removed IPv6: {len(diff.removed_v6)} prefixes")

        # Step 4: Submit ticket if changes detected
        ticket_response = None
        if diff.has_changes:
            ticket_client = TicketingClient(
                base_url=config.ticketing.base_url,
                api_token=config.ticketing.api_token,
                timeout=config.ticketing.timeout_seconds,
                max_retries=config.ticketing.max_retries,
            )

            try:
                payload = ticket_client.get_payload(target, diff, fetch_result.sources_queried)

                # Save pending ticket
                ticket_id = store.save_ticket(
                    diff_id=diff_id,
                    target=target,
                    status='pending',
                    request_payload=payload,
                )

                # Submit
                ticket_response = ticket_client.create_ticket(
                    target, diff, fetch_result.sources_queried, dry_run=dry_run
                )

                # Update ticket status
                store.update_ticket_status(
                    ticket_id=ticket_id,
                    status=ticket_response.status,
                    response_payload={
                        'ticket_id': ticket_response.ticket_id,
                        'error_message': ticket_response.error_message,
                    },
                    external_ticket_id=ticket_response.ticket_id,
                )

                if dry_run:
                    print_output(f"[DRY-RUN] Would create ticket", args.json, args.quiet)
                elif ticket_response.status == 'created':
                    print_output(f"Ticket created: {ticket_response.ticket_id}", args.json, args.quiet)
                elif ticket_response.status == 'duplicate':
                    print_output(f"Ticket already exists: {ticket_response.ticket_id}", args.json, args.quiet)
                else:
                    print_output(
                        f"ERROR: Failed to create ticket: {ticket_response.error_message}",
                        args.json, args.quiet
                    )

            finally:
                ticket_client.close()

        # JSON output
        if args.json:
            output = {
                'target': target,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'snapshot': {
                    'id': snapshot_id,
                    'ipv4_count': len(fetch_result.ipv4_prefixes),
                    'ipv6_count': len(fetch_result.ipv6_prefixes),
                    'hash': snapshot.content_hash,
                },
                'diff': format_diff_json(diff),
            }

            if ticket_response:
                output['ticket'] = {
                    'id': ticket_response.ticket_id,
                    'status': ticket_response.status,
                    'dry_run': dry_run,
                }

            print(json.dumps(output))

        return 0

    finally:
        store.close()


def cmd_run_all(config: Config, args: argparse.Namespace) -> int:
    """Run for all configured targets."""
    logger = get_logger('cli')
    dry_run = args.dry_run

    if not config.targets:
        print_output("ERROR: No targets configured in config file", args.json, args.quiet)
        return 1

    print_output(f"Processing {len(config.targets)} targets...", args.json, args.quiet)

    results = []
    failed = 0

    for target in config.targets:
        # Create a namespace with the target
        run_args = argparse.Namespace(
            target=target,
            dry_run=dry_run,
            json=args.json,
            quiet=True,  # Quiet individual runs
            verbose=args.verbose,
        )

        print_output(f"Processing {target}...", args.json, args.quiet)
        exit_code = cmd_run(config, run_args)

        if exit_code != 0:
            failed += 1
            results.append({'target': target, 'status': 'failed'})
        else:
            results.append({'target': target, 'status': 'success'})

    print_output(
        f"Completed: {len(config.targets) - failed} succeeded, {failed} failed",
        args.json, args.quiet
    )

    if args.json:
        print(json.dumps({
            'total': len(config.targets),
            'succeeded': len(config.targets) - failed,
            'failed': failed,
            'results': results,
        }))

    return 1 if failed > 0 else 0


def cmd_history(config: Config, args: argparse.Namespace) -> int:
    """Show snapshot history."""
    logger = get_logger('cli')
    target = args.target.upper()
    limit = args.limit

    store = SnapshotStore(config.database.path)
    store.migrate()

    try:
        snapshots = store.get_snapshot_history(target, limit)
    finally:
        store.close()

    if not snapshots:
        print_output(f"No snapshots found for {target}", args.json, args.quiet)
        if args.json:
            print(json.dumps({'target': target, 'snapshots': []}))
        return 0

    if args.json:
        print(json.dumps({
            'target': target,
            'snapshots': [
                {
                    'id': s.id,
                    'timestamp': datetime.fromtimestamp(s.timestamp).isoformat(),
                    'ipv4_count': len(s.ipv4_prefixes),
                    'ipv6_count': len(s.ipv6_prefixes),
                    'hash': s.content_hash,
                    'sources': s.irr_sources,
                }
                for s in snapshots
            ]
        }))
    else:
        print(f"Snapshot history for {target}:")
        print("-" * 80)
        for s in snapshots:
            ts = datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{s.id}] {ts}")
            print(f"       IPv4: {len(s.ipv4_prefixes):,} | IPv6: {len(s.ipv6_prefixes):,}")
            print(f"       Hash: {s.content_hash[:12]}... | Sources: {', '.join(s.irr_sources)}")
            print()

    return 0


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}", file=sys.stderr)
        return 1

    # Override logging level if verbose
    if args.verbose:
        config.logging.level = 'DEBUG'

    # Setup logging
    setup_logging(config.logging)

    # Route to command handler
    commands = {
        'init-db': cmd_init_db,
        'fetch': cmd_fetch,
        'diff': cmd_diff,
        'submit': cmd_submit,
        'run': cmd_run,
        'run-all': cmd_run_all,
        'history': cmd_history,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            return handler(config, args)
        except KeyboardInterrupt:
            print("\nInterrupted by user", file=sys.stderr)
            return 130
        except Exception as e:
            logger = get_logger('cli')
            logger.error(f"Unexpected error: {e}", exc_info=True)
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
