"""Configuration loading and validation for IRR Automation."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass
class RADBConfig:
    """RADB API configuration."""
    base_url: str = "https://api.radb.net"
    timeout_seconds: int = 60
    max_retries: int = 3


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "./data/irr.sqlite"


@dataclass
class TicketingConfig:
    """AT&T Ticketing API configuration."""
    base_url: str = ""
    api_token: str = ""
    timeout_seconds: int = 30
    max_retries: int = 3


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    file: Optional[str] = None


@dataclass
class DiffConfig:
    """Diff computation configuration."""
    lookback_hours: int = 24


@dataclass
class Config:
    """Main configuration container."""
    irr_sources: List[str] = field(default_factory=lambda: ["RADB", "RIPE", "NTTCOM"])
    targets: List[str] = field(default_factory=list)
    api_url: Optional[str] = None  # When set, proxy all IRR queries via this URL
    radb: RADBConfig = field(default_factory=RADBConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    ticketing: TicketingConfig = field(default_factory=TicketingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    diff: DiffConfig = field(default_factory=DiffConfig)


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in the format ${VAR_NAME}."""
    pattern = r'\$\{([^}]+)\}'

    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(pattern, replacer, value)


def _expand_env_vars_recursive(obj):
    """Recursively expand environment variables in a data structure."""
    if isinstance(obj, str):
        return _expand_env_vars(obj)
    elif isinstance(obj, dict):
        return {k: _expand_env_vars_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars_recursive(item) for item in obj]
    return obj


def load_config(config_path: str) -> Config:
    """
    Load configuration from a YAML file.

    Supports environment variable interpolation using ${VAR_NAME} syntax.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Config object with all settings.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f) or {}

    # Expand environment variables
    raw_config = _expand_env_vars_recursive(raw_config)

    # Build config object
    config = Config()

    # IRR sources
    if 'irr_sources' in raw_config:
        config.irr_sources = raw_config['irr_sources']

    # Targets
    if 'targets' in raw_config:
        config.targets = raw_config['targets']

    # API proxy URL (when set, IRR queries go through the deployed API)
    if 'api_url' in raw_config:
        config.api_url = raw_config['api_url'] or None
    if os.environ.get('IRR_API_URL'):
        config.api_url = os.environ['IRR_API_URL']

    # RADB config
    if 'radb' in raw_config:
        radb_raw = raw_config['radb']
        config.radb = RADBConfig(
            base_url=radb_raw.get('base_url', config.radb.base_url),
            timeout_seconds=radb_raw.get('timeout_seconds', config.radb.timeout_seconds),
            max_retries=radb_raw.get('max_retries', config.radb.max_retries),
        )

    # Database config
    if 'database' in raw_config:
        db_raw = raw_config['database']
        config.database = DatabaseConfig(
            path=db_raw.get('path', config.database.path),
        )

    # Apply environment variable overrides for database
    if os.environ.get('IRR_DB_PATH'):
        config.database.path = os.environ['IRR_DB_PATH']

    # Ticketing config
    if 'ticketing' in raw_config:
        tick_raw = raw_config['ticketing']
        config.ticketing = TicketingConfig(
            base_url=tick_raw.get('base_url', config.ticketing.base_url),
            api_token=tick_raw.get('api_token', config.ticketing.api_token),
            timeout_seconds=tick_raw.get('timeout_seconds', config.ticketing.timeout_seconds),
            max_retries=tick_raw.get('max_retries', config.ticketing.max_retries),
        )

    # Apply environment variable overrides for ticketing
    if os.environ.get('ABC_BASE_URL'):
        config.ticketing.base_url = os.environ['ABC_BASE_URL']
    if os.environ.get('ABC_TOKEN'):
        config.ticketing.api_token = os.environ['ABC_TOKEN']

    # Logging config
    if 'logging' in raw_config:
        log_raw = raw_config['logging']
        config.logging = LoggingConfig(
            level=log_raw.get('level', config.logging.level),
            format=log_raw.get('format', config.logging.format),
            file=log_raw.get('file'),
        )

    # Apply environment variable overrides for logging
    if os.environ.get('IRR_LOG_LEVEL'):
        config.logging.level = os.environ['IRR_LOG_LEVEL']
    if os.environ.get('IRR_LOG_FORMAT'):
        config.logging.format = os.environ['IRR_LOG_FORMAT']

    # Diff config
    if 'diff' in raw_config:
        diff_raw = raw_config['diff']
        config.diff = DiffConfig(
            lookback_hours=diff_raw.get('lookback_hours', config.diff.lookback_hours),
        )

    # Validate configuration
    validate_config(config)

    return config


# Valid IRR sources that we know how to query
VALID_IRR_SOURCES = {'RIPE', 'RADB', 'ARIN', 'APNIC', 'LACNIC', 'AFRINIC', 'NTTCOM'}


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""
    pass


def validate_config(config: Config) -> None:
    """
    Validate configuration has required fields and valid values.

    Args:
        config: The configuration object to validate.

    Raises:
        ConfigValidationError: If validation fails.
    """
    errors = []

    # Validate IRR sources are recognized
    if config.irr_sources:
        unknown_sources = set(s.upper() for s in config.irr_sources) - VALID_IRR_SOURCES
        if unknown_sources:
            errors.append(f"Unknown IRR sources: {unknown_sources}. Valid sources: {VALID_IRR_SOURCES}")
    else:
        errors.append("At least one IRR source must be configured")

    # Validate numeric fields are positive
    if config.radb.timeout_seconds <= 0:
        errors.append("radb.timeout_seconds must be positive")
    if config.radb.max_retries < 0:
        errors.append("radb.max_retries must be non-negative")

    if config.ticketing.timeout_seconds <= 0:
        errors.append("ticketing.timeout_seconds must be positive")
    if config.ticketing.max_retries < 0:
        errors.append("ticketing.max_retries must be non-negative")

    if config.diff.lookback_hours <= 0:
        errors.append("diff.lookback_hours must be positive")

    # Validate logging level
    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    if config.logging.level.upper() not in valid_levels:
        errors.append(f"logging.level must be one of: {valid_levels}")

    # Validate logging format
    valid_formats = {'json', 'text'}
    if config.logging.format.lower() not in valid_formats:
        errors.append(f"logging.format must be one of: {valid_formats}")

    if errors:
        raise ConfigValidationError(
            "Configuration validation failed:\n  - " + "\n  - ".join(errors)
        )


def get_default_config() -> Config:
    """Return a Config object with default values."""
    return Config()
