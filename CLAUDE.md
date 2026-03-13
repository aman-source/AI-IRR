# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IRR Prefix Change Detection & Ticket Automation — a Python CLI tool that monitors routing prefix changes in Internet Routing Registry (IRR) databases using BGPQ4, then creates AT&T tickets and sends Microsoft Teams alerts when changes are detected.

## Commands

### Setup
```bash
python -m venv .venv
pip install -r requirements.txt
```

### Running Tests
```bash
pytest tests/ -v                                        # All tests
pytest tests/ -v --cov=app --cov-report=term-missing    # With coverage
pytest tests/test_bgpq4_client.py -v                    # Single test file
```

### CLI Usage
```bash
python -m app.cli init-db                               # Initialize SQLite database
python -m app.cli fetch --target AS15169                # Fetch prefixes for a target
python -m app.cli run --target AS15169 --dry-run        # Fetch + diff + submit (one target)
python -m app.cli run-all --dry-run                     # Process all configured targets
python -m app.cli history --target AS15169              # View snapshot history
```

Global flags: `--config <path>`, `--verbose`, `--quiet`, `--json`

### Docker (API Mode)
```bash
docker build -t irr-automation .
docker run -p 8000:8000 irr-automation
```

## Architecture

The system has two operational modes:

**CLI Mode (primary):** `app/cli.py` → loads `config.yaml` → calls `BGPQ4Client` (subprocess to `bgpq4` via WSL) → stores snapshots in SQLite via `store.py` → computes diffs via `diff.py` → creates AT&T tickets via `ticketing.py` → sends Teams alerts via `teams.py`.

**API Proxy Mode (optional):** When a target specifies `api_url`, `APIProxyClient` replaces `BGPQ4Client` and queries a deployed FastAPI service (`api/main.py`) instead of running bgpq4 locally.

### Key Modules (`app/`)

- **bgpq4_client.py** — Wraps bgpq4 subprocess. Handles AS-SET expansion, prefix aggregation, and IRR source selection in one call. Returns IPv4/IPv6 prefix lists.
- **store.py** — SQLite layer with three tables: `snapshots` (time-series prefix history), `diffs` (computed changes), `tickets` (creation audit). Uses `content_hash` and `diff_hash` for idempotency.
- **diff.py** — Compares current vs. previous snapshot; computes SHA256 hash of changes to prevent duplicate tickets.
- **ticketing.py** — AT&T Ticketing API client with tenacity-based exponential backoff retry.
- **teams.py** — Posts Adaptive Card JSON to a Power Automate webhook URL.
- **config.py** — Loads `config.yaml` with `${ENV_VAR}` interpolation into typed dataclasses.
- **api/main.py** — Optional FastAPI service exposing `/api/v1/fetch` and `/health`.

### Deduplication Strategy

1. `content_hash` (SHA256 of prefix set) prevents storing duplicate snapshots for the same target.
2. `diff_hash` (SHA256 of added/removed prefixes) prevents creating duplicate tickets for the same change.

### Environment Variables

| Variable | Purpose |
|---|---|
| `ABC_BASE_URL` | AT&T Ticketing API endpoint |
| `ABC_TOKEN` | Bearer token for ticketing |
| `TEAMS_WEBHOOK_URL` | Power Automate webhook for Teams |
| `IRR_API_URL` | Optional remote bgpq4 API endpoint |
| `IRR_DB_PATH` | Override database path |
| `IRR_LOG_LEVEL` / `IRR_LOG_FORMAT` | Logging overrides |

### Configuration (`config.yaml`)

Defines BGPQ4 settings, target ASNs/AS-SETs, database path, ticketing credentials, Teams webhook, logging, and `diff_lookback_hours`. All sensitive values should use `${ENV_VAR}` interpolation.
