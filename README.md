# IRR Prefix Change Detection & Ticket Automation

A Python CLI tool that automatically detects routing prefix changes in Internet Routing Registry (IRR) databases and creates tickets in AT&T's ticketing system when changes are detected.

Uses [BGPQ4](https://github.com/bgp/bgpq4) for IRR queries, which handles AS-SET expansion, prefix aggregation, and database selection in a single command.

## Features

- **BGPQ4-Powered Queries**: Single tool handles all IRR lookups via RADB (which mirrors all 5 RIRs)
- **AS-SET Support**: Query AS-SETs (e.g., `AS-GOOGLE`) — BGPQ4 expands them automatically
- **Prefix Aggregation**: Multiple specific prefixes are aggregated into summary routes (e.g., five /24s become one /22)
- **IPv4 & IPv6**: Full dual-stack support
- **Snapshot Storage**: Persist prefix snapshots in SQLite for historical tracking
- **Change Detection**: Compute diffs between snapshots to detect added/removed prefixes
- **Ticket Automation**: Automatically create tickets when changes are detected
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

# Verify
wsl bgpq4 -4 -j -A -S RADB -l pl AS15169
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

# 3. Fetch prefixes for an AS-SET
python -m app.cli fetch --target AS-GOOGLE

# 4. Run all-in-one (fetch + diff + ticket if changes)
python -m app.cli run --target AS15169 --dry-run

# 5. Run for all configured targets
python -m app.cli run-all --dry-run
```

## Configuration

### config.yaml

```yaml
# BGPQ4 settings
# RADB mirrors all 5 RIRs, so querying RADB alone is sufficient.
bgpq4:
  cmd: ["wsl", "bgpq4"]      # Command to invoke bgpq4
  source: "RADB"              # IRR source (-S flag)
  aggregate: true             # Aggregate prefixes (-A flag)
  timeout_seconds: 120        # Subprocess timeout

# Targets to monitor — ASNs or AS-SETs
targets:
  - AS15169    # Google
  - AS16509    # Amazon
  - AS8075     # Microsoft

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
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ABC_BASE_URL` | AT&T Ticketing API base URL | Yes (for ticket submission) |
| `ABC_TOKEN` | AT&T Ticketing API bearer token | Yes (for ticket submission) |
| `IRR_API_URL` | API proxy URL (use remote API instead of local bgpq4) | No |
| `IRR_DB_PATH` | Override database path | No |
| `IRR_LOG_LEVEL` | Override log level | No |
| `IRR_LOG_FORMAT` | Override log format | No |

## Usage

### Fetch Prefixes

```bash
# Fetch for a single ASN
python -m app.cli fetch --target AS15169

# Fetch for an AS-SET (expands all member ASNs)
python -m app.cli fetch --target AS-GOOGLE

# Verbose output
python -m app.cli fetch --target AS15169 -v

# JSON output
python -m app.cli fetch --target AS15169 --json
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
python -m app.cli run --target AS15169 --dry-run

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
│   ├── bgpq4_client.py     # BGPQ4 IRR client (subprocess)
│   ├── api_proxy_client.py  # Optional API proxy client
│   ├── config.py            # Configuration loading and validation
│   ├── cli.py               # CLI entry point
│   ├── store.py             # SQLite database layer
│   ├── diff.py              # Diff computation
│   ├── ticketing.py         # Ticketing API client
│   └── logger.py            # Structured logging
├── api/
│   ├── main.py              # FastAPI application
│   ├── schemas.py           # Pydantic models
│   ├── settings.py          # API settings
│   └── dependencies.py      # Dependency injection
├── tests/
│   ├── test_bgpq4_client.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_store.py
│   ├── test_diff.py
│   └── test_ticketing.py
├── data/                     # Database files (runtime)
├── config.yaml               # Configuration
├── requirements.txt
├── pyproject.toml
└── README.md
```

## How It Works

1. **BGPQ4** queries RADB (which mirrors all 5 RIRs: RIPE, ARIN, APNIC, LACNIC, AFRINIC) for prefixes
2. Prefixes are **aggregated** automatically (e.g., five /24s → one /22)
3. For AS-SETs, BGPQ4 **recursively expands** all member ASNs
4. Results are stored as a **snapshot** in SQLite
5. **Diff** is computed against the previous snapshot
6. If changes are detected, a **ticket** is created via the AT&T API

## Troubleshooting

### "bgpq4 not found" / "Command not found: wsl"

Ensure WSL is installed and bgpq4 is available:
```bash
wsl bgpq4 --version
```
If not installed: `wsl sudo apt install bgpq4`

### "bgpq4 timed out"

Increase `timeout_seconds` in the `bgpq4:` config section. Large AS-SETs may take longer to expand.

### "No snapshot found for target"

Run `fetch` first to create an initial snapshot before running `diff` or `submit`.

### "Ticket creation failed"

Verify that `ABC_BASE_URL` and `ABC_TOKEN` environment variables are set and the API token is valid.

### Database Locked

Ensure only one instance of the tool is running at a time.

## License

Internal AT&T use only.
