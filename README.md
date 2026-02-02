# IRR Prefix Change Detection & Ticket Automation

A Python CLI tool that automatically detects routing prefix changes in Internet Routing Registry (IRR) databases and creates tickets in AT&T's ticketing system when changes are detected.

## Features

- **Multi-Source IRR Queries**: Query multiple IRR sources including all Regional Internet Registries (RIRs) and major IRRs
- **Dual Protocol Support**: Uses REST API for RIPE and WHOIS protocol for other sources
- **Fetch Prefixes**: Query for IPv4 and IPv6 prefixes by ASN
- **Snapshot Storage**: Persist prefix snapshots in SQLite for historical tracking
- **Change Detection**: Compute diffs between snapshots to detect added/removed prefixes
- **Ticket Automation**: Automatically create tickets when changes are detected
- **Idempotency**: Prevent duplicate tickets using diff hashing
- **Dry-Run Mode**: Test the workflow without creating actual tickets
- **Transaction Support**: Atomic database operations for data integrity

## Supported IRR Sources

| Source | Type | Region/Scope | Protocol |
|--------|------|--------------|----------|
| **RIPE** | RIR | Europe, Middle East, Central Asia | REST API |
| **RADB** | IRR | Global (Merit Network) | WHOIS |
| **ARIN** | RIR | North America | WHOIS |
| **APNIC** | RIR | Asia Pacific | WHOIS |
| **LACNIC** | RIR | Latin America & Caribbean | WHOIS |
| **AFRINIC** | RIR | Africa | WHOIS |
| **NTTCOM** | IRR | NTT Communications | WHOIS |

Results from all configured sources are merged and deduplicated automatically.

## Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Setup

1. Clone or download this repository:
```bash
cd irr-automation
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure the application:
```bash
# Copy and edit the configuration file
cp config.yaml config.local.yaml
# Edit config.local.yaml with your settings
```

5. Set environment variables for the ticketing API:
```bash
# Windows
set ABC_BASE_URL=https://abc.internal.att.com/api
set ABC_TOKEN=your-api-token-here

# Linux/Mac
export ABC_BASE_URL=https://abc.internal.att.com/api
export ABC_TOKEN=your-api-token-here
```

## Configuration

### config.yaml

```yaml
# IRR sources to query (supports: RIPE, RADB, ARIN, APNIC, LACNIC, AFRINIC, NTTCOM)
irr_sources:
  - RIPE      # Uses REST API
  - RADB      # Uses WHOIS
  - ARIN      # Uses WHOIS
  - APNIC     # Uses WHOIS

# ASNs to monitor
targets:
  - AS15169    # Google
  - AS16509    # Amazon
  - AS8075     # Microsoft

# API settings
radb:
  base_url: "https://rest.db.ripe.net"  # RIPE REST API endpoint
  timeout_seconds: 60                    # Applies to both REST and WHOIS
  max_retries: 3

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
| `IRR_DB_PATH` | Override database path | No |
| `IRR_LOG_LEVEL` | Override log level | No |
| `IRR_LOG_FORMAT` | Override log format | No |

## Usage

### Initialize Database

```bash
python -m app.cli init-db --config config.yaml
```

### Fetch Prefixes

Fetch current prefixes for an ASN and store a snapshot:

```bash
python -m app.cli fetch --target AS15169 --config config.yaml

# With verbose output to see queries to each IRR source
python -m app.cli fetch --target AS15169 --config config.yaml -v
```

### Compute Diff

Compare current snapshot against previous (24 hours ago by default):

```bash
# Human-readable output
python -m app.cli diff --target AS15169 --config config.yaml

# JSON output
python -m app.cli diff --target AS15169 --config config.yaml --json
```

### Submit Ticket

Create a ticket for detected changes:

```bash
# Dry run (no actual ticket created)
python -m app.cli submit --target AS15169 --config config.yaml --dry-run

# Actual submission
python -m app.cli submit --target AS15169 --config config.yaml
```

### All-in-One Run

Fetch, diff, and submit ticket if changes detected:

```bash
# Single target
python -m app.cli run --target AS15169 --config config.yaml --dry-run

# All configured targets
python -m app.cli run-all --config config.yaml --dry-run
```

### View History

Show snapshot history for an ASN:

```bash
python -m app.cli history --target AS15169 --config config.yaml --limit 10
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

# Run with coverage report
pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_store.py -v
```

## Daily Cron Job

To run daily checks for all configured ASNs:

```bash
# Add to crontab (runs at 6 AM daily)
0 6 * * * cd /path/to/irr-automation && /path/to/.venv/bin/python -m app.cli run-all --config config.yaml
```

## Project Structure

```
irr-automation/
├── app/
│   ├── __init__.py        # Package initialization
│   ├── config.py          # Configuration loading and validation
│   ├── logger.py          # Structured logging
│   ├── radb_client.py     # IRR client (REST + WHOIS)
│   ├── store.py           # SQLite database layer with transactions
│   ├── diff.py            # Diff computation
│   ├── ticketing.py       # Ticketing API client
│   └── cli.py             # CLI entry point
├── tests/
│   ├── __init__.py
│   ├── test_cli.py        # CLI tests
│   ├── test_store.py      # Database tests
│   ├── test_radb_client.py # IRR client tests (including WHOIS)
│   ├── test_diff.py       # Diff computation tests
│   └── test_ticketing.py  # Ticketing API tests
├── data/                   # Database files (created at runtime)
├── logs/                   # Log files (created at runtime)
├── config.yaml             # Configuration file
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata
└── README.md               # This file
```

## Troubleshooting

### "Configuration file not found"

Ensure `config.yaml` exists in the specified path or use the `--config` option to specify the correct path.

### "Configuration validation failed"

Check that:
1. All IRR sources in `irr_sources` are valid (RIPE, RADB, ARIN, APNIC, LACNIC, AFRINIC, NTTCOM)
2. Numeric fields (timeout, retries) are positive
3. Logging level and format are valid

### "No snapshot found for target"

Run the `fetch` command first to create an initial snapshot before running `diff` or `submit`.

### "Failed to fetch prefixes"

Check your internet connection. For WHOIS-based sources, ensure port 43 outbound is not blocked. The tool will retry automatically on transient failures. Use `-v` flag to see detailed error messages.

### "WHOIS query timed out"

Some IRR servers may be slow or temporarily unavailable. Try increasing `timeout_seconds` in the config or removing the problematic source from `irr_sources`.

### "Ticket creation failed"

Verify that:
1. `ABC_BASE_URL` and `ABC_TOKEN` environment variables are set
2. The API token is valid and not expired
3. The ticketing service is accessible

### Database Locked

If you see "database is locked" errors, ensure only one instance of the tool is running at a time.

## Architecture Notes

- **RIPE REST API**: Used for RIPE source queries. Fast and reliable.
- **WHOIS Protocol**: Used for all other sources (RADB, ARIN, APNIC, etc.). Connects to port 43 of each IRR's WHOIS server.
- **Prefix Merging**: Results from all sources are combined using set union, so duplicates are automatically removed.
- **Transaction Support**: Database operations can be wrapped in transactions for atomicity.

## License

Internal AT&T use only.
