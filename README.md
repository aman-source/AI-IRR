# IRR Prefix Change Detection & Ticket Automation

A Python CLI tool that automatically detects routing prefix changes in Internet Routing Registry (IRR) databases and creates tickets in AT&T's ticketing system when changes are detected.

Uses [BGPQ4](https://github.com/bgp/bgpq4) for IRR queries, which handles AS-SET expansion, prefix aggregation, and database selection in a single command.

## Features

- **Multi-Source IRR Queries**: Query all 7 sources simultaneously — RADB, RIPE, ARIN, APNIC, LACNIC, AFRINIC, and RPKI
- **RPKI Validation**: Include Route Origin Authorization (ROA) data alongside IRR data
- **Python Aggregation**: Post-processes results with `ipaddress.collapse_addresses()` for minimal supernet sets
- **Raw vs. Aggregated Counts**: Tracks both the raw prefix count and the aggregated count (e.g., 238 raw → 10 aggregated for AS-BYTEDANCE)
- **AS-SET Support**: Query AS-SETs (e.g., `AS-BYTEDANCE`) — BGPQ4 expands them automatically
- **IPv4 & IPv6**: Full dual-stack support
- **Snapshot Storage**: Persist prefix snapshots in SQLite for historical tracking
- **Change Detection**: Compute diffs between snapshots to detect added/removed prefixes
- **Ticket Automation**: Automatically create tickets when changes are detected
- **Teams Alerts**: Post Adaptive Card notifications to Microsoft Teams via Power Automate webhook
- **Idempotency**: Prevent duplicate tickets using diff hashing
- **Dry-Run Mode**: Test the workflow without creating actual tickets
- **Optional API**: FastAPI service for remote/shared access

## Prerequisites

- Python 3.10+
- [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows) with bgpq4 installed
- pip

### Install bgpq4

```bash
# In WSL
sudo apt update && sudo apt install -y bgpq4

# Verify (query all 7 sources for AS-BYTEDANCE)
wsl bgpq4 -4 -j -A -S RADB,ARIN,RIPE,APNIC,LACNIC,AFRINIC,RPKI -l pl AS-BYTEDANCE
```

## Installation

```bash
# Clone the repository
cd AI-IRR

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# 1. Initialize the database
python -m app.cli init-db

# 2. Fetch prefixes for an ASN
python -m app.cli fetch --target AS15169

# 3. Fetch prefixes for an AS-SET (e.g., ByteDance)
python -m app.cli fetch --target AS-BYTEDANCE

# 4. Run all-in-one (fetch + diff + ticket if changes)
python -m app.cli run --target AS-BYTEDANCE --dry-run

# 5. Run for all configured targets
python -m app.cli run-all --dry-run
```

## Configuration

### config.yaml

```yaml
# BGPQ4 settings
bgpq4:
  cmd: ["wsl", "bgpq4"]      # Command to invoke bgpq4
  sources:                    # IRR sources — bgpq4 queries all at once via -S RADB,RPKI,...
    - RADB                    # Global IRR mirror (mirrors all 5 RIRs)
    - RPKI                    # RPKI ROA validation
    # - RIPE                  # Uncomment to query individual RIRs directly
    # - ARIN
    # - APNIC
    # - LACNIC
    # - AFRINIC
  aggregate: true             # Aggregate prefixes with bgpq4's -A flag
  timeout_seconds: 120        # Subprocess timeout

# Targets to monitor — ASNs or AS-SETs
targets:
  - AS15169        # Google
  - AS16509        # Amazon
  - AS-BYTEDANCE   # ByteDance

# Database settings
database:
  path: "./data/irr.sqlite"

# Ticketing API settings (use environment variables)
ticketing:
  base_url: "${ABC_BASE_URL}"
  api_token: "${ABC_TOKEN}"
  timeout_seconds: 30
  max_retries: 3

# Logging settings
logging:
  level: "INFO"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"         # "json" or "text"

# Diff settings
diff:
  lookback_hours: 24     # Compare against snapshot from N hours ago

# Microsoft Teams alerts (via Power Automate webhook)
teams:
  webhook_url: "${TEAMS_WEBHOOK_URL}"
  timeout_seconds: 15
```

> **Note:** The legacy single-string `source: "RADB"` key is still accepted for backward compatibility and treated as `sources: ["RADB"]`.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ABC_BASE_URL` | AT&T Ticketing API base URL | Yes (for ticket submission) |
| `ABC_TOKEN` | AT&T Ticketing API bearer token | Yes (for ticket submission) |
| `TEAMS_WEBHOOK_URL` | Power Automate webhook URL for Teams alerts | No |
| `IRR_API_URL` | API proxy URL (use remote API instead of local bgpq4) | No |
| `IRR_DB_PATH` | Override database path | No |
| `IRR_LOG_LEVEL` | Override log level | No |
| `IRR_LOG_FORMAT` | Override log format | No |
| `IRR_API_BGPQ4_SOURCES` | Override sources for the API service (comma-separated, e.g. `RADB,RPKI`) | No |

## Usage

### Fetch Prefixes

```bash
# Fetch for a single ASN
python -m app.cli fetch --target AS15169

# Fetch for an AS-SET (expands all member ASNs)
python -m app.cli fetch --target AS-BYTEDANCE

# Verbose output
python -m app.cli fetch --target AS15169 -v

# JSON output (includes raw and aggregated counts)
python -m app.cli fetch --target AS15169 --json
```

Example output:
```
IPv4: 238 raw -> 10 aggregated  IPv6: 126 raw -> 3 aggregated
Snapshot saved (id: 1, hash: a3f9c2b1d4e8...)
```

### Compute Diff

```bash
python -m app.cli diff --target AS15169
python -m app.cli diff --target AS15169 --json
```

### Submit Ticket

```bash
# Dry run
python -m app.cli submit --target AS15169 --dry-run

# Actual submission
python -m app.cli submit --target AS15169
```

### All-in-One Run

```bash
# Single target
python -m app.cli run --target AS-BYTEDANCE --dry-run

# All configured targets
python -m app.cli run-all --dry-run
```

### View History

```bash
python -m app.cli history --target AS15169 --limit 10
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-c, --config` | Path to config file (default: ./config.yaml) |
| `-v, --verbose` | Enable debug logging |
| `-q, --quiet` | Suppress non-error output |
| `--json` | Output results as JSON |
| `--dry-run` | Don't create actual tickets |

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_bgpq4_client.py -v
pytest tests/test_aggregation.py -v
```

## Daily Cron Job

```bash
# Add to crontab (runs at 6 AM daily)
0 6 * * * cd /path/to/AI-IRR && /path/to/.venv/bin/python -m app.cli run-all
```

## Project Structure

```
AI-IRR/
├── app/
│   ├── __init__.py
│   ├── bgpq4_client.py      # BGPQ4 IRR client — multi-source, Python aggregation
│   ├── api_proxy_client.py  # Optional API proxy client
│   ├── config.py            # Configuration loading and validation
│   ├── cli.py               # CLI entry point
│   ├── store.py             # SQLite database layer
│   ├── diff.py              # Diff computation
│   ├── ticketing.py         # Ticketing API client
│   ├── teams.py             # Microsoft Teams Adaptive Card notifier
│   └── logger.py            # Structured logging
├── api/
│   ├── main.py              # FastAPI application
│   ├── schemas.py           # Pydantic models
│   ├── settings.py          # API settings
│   └── dependencies.py      # Dependency injection
├── tests/
│   ├── test_aggregation.py  # Python aggregation + AS-BYTEDANCE scenario
│   ├── test_bgpq4_client.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_store.py
│   ├── test_diff.py
│   ├── test_api.py
│   └── test_ticketing.py
├── docs/
│   └── MULTI_IRR_SOURCES.md
├── data/                    # Database files (runtime)
├── config.yaml              # Configuration
├── requirements.txt
├── pyproject.toml
└── README.md
```

## How It Works

1. **BGPQ4** queries all configured IRR sources simultaneously (e.g., `-S RADB,RPKI`) for prefixes
2. **Python aggregation** applies `ipaddress.collapse_addresses()` — removes covered subnets and merges adjacent networks into the minimal supernet set
3. For AS-SETs, BGPQ4 **recursively expands** all member ASNs
4. Both **raw count** (from bgpq4) and **aggregated count** (after Python collapse) are tracked
5. Results are stored as a **snapshot** in SQLite
6. **Diff** is computed against the previous snapshot
7. If changes are detected, a **ticket** is created via the AT&T API
8. A **Teams Adaptive Card** alert is posted via Power Automate webhook

### IRR Sources

| Source | Type | Coverage |
|--------|------|----------|
| RADB | IRR mirror | Global — mirrors all 5 RIRs |
| RIPE | RIR | Europe, Middle East, Central Asia |
| ARIN | RIR | North America |
| APNIC | RIR | Asia-Pacific |
| LACNIC | RIR | Latin America & Caribbean |
| AFRINIC | RIR | Africa |
| RPKI | ROA validation | Global — cryptographic route origin validation |

### Aggregation Example (AS-BYTEDANCE)

```
Sources: RADB,ARIN,RIPE,APNIC,LACNIC,AFRINIC,RPKI

IPv4: 238 raw prefixes → 10 aggregated
  71.18.0.0/16       101.45.0.0/16      130.44.212.0/22
  139.177.224.0/19   147.160.176.0/20   180.240.232.0/22
  192.64.14.0/23     199.103.24.0/23    202.52.224.0/21
  202.52.240.0/21

IPv6: 126 raw prefixes → 3 aggregated
  2404:8d04:2643::/48   2404:8d04:4642::/48   2605:340::/32
```

## Troubleshooting

### "bgpq4 not found" / "Command not found: wsl"

Ensure WSL is installed and bgpq4 is available:
```bash
wsl bgpq4 --version
```
If not installed: `wsl sudo apt install bgpq4`

### "bgpq4 timed out"

Increase `timeout_seconds` in the `bgpq4:` config section. Large AS-SETs with many sources may take longer.

### "No snapshot found for target"

Run `fetch` first to create an initial snapshot before running `diff` or `submit`.

### "Unknown BGPQ4 source: RADB,RPKI"

You used a comma-separated scalar in YAML instead of a list. Use:
```yaml
# Correct
bgpq4:
  sources:
    - RADB
    - RPKI

# Wrong — treated as one unknown source name
bgpq4:
  sources: "RADB,RPKI"
```

### "Ticket creation failed"

Verify that `ABC_BASE_URL` and `ABC_TOKEN` environment variables are set and the API token is valid.

### Teams alert not appearing

1. Confirm `TEAMS_WEBHOOK_URL` is set to the Power Automate webhook URL.
2. The webhook must use a **"When a HTTP request is received"** trigger configured to accept Adaptive Card format.
3. The "Post card in a chat or channel" action must reference `triggerBody()?['attachments'][0]['content']` as the card content.
4. Test with a direct `curl` POST — a `202 Accepted` response means the webhook is reachable.

### Database Locked

Ensure only one instance of the tool is running at a time.

## License

Internal AT&T use only.
