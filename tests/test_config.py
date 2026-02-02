"""Tests for configuration module."""

import os
import tempfile
import pytest
from unittest.mock import patch

from app.config import (
    Config,
    RADBConfig,
    DatabaseConfig,
    TicketingConfig,
    LoggingConfig,
    DiffConfig,
    load_config,
    validate_config,
    get_default_config,
    ConfigValidationError,
    VALID_IRR_SOURCES,
    _expand_env_vars,
    _expand_env_vars_recursive,
)


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_default_config(self):
        """Test that default config is created with expected values."""
        config = get_default_config()
        assert isinstance(config, Config)
        assert 'RADB' in config.irr_sources
        assert config.targets == []

    def test_radb_config_defaults(self):
        """Test RADBConfig default values."""
        config = RADBConfig()
        assert config.base_url == "https://api.radb.net"
        assert config.timeout_seconds == 60
        assert config.max_retries == 3

    def test_database_config_defaults(self):
        """Test DatabaseConfig default values."""
        config = DatabaseConfig()
        assert config.path == "./data/irr.sqlite"

    def test_ticketing_config_defaults(self):
        """Test TicketingConfig default values."""
        config = TicketingConfig()
        assert config.base_url == ""
        assert config.api_token == ""
        assert config.timeout_seconds == 30
        assert config.max_retries == 3

    def test_logging_config_defaults(self):
        """Test LoggingConfig default values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.format == "json"
        assert config.file is None

    def test_diff_config_defaults(self):
        """Test DiffConfig default values."""
        config = DiffConfig()
        assert config.lookback_hours == 24


class TestExpandEnvVars:
    """Tests for environment variable expansion."""

    def test_expand_single_var(self):
        """Test expanding a single env var."""
        with patch.dict(os.environ, {'TEST_VAR': 'test_value'}):
            result = _expand_env_vars("${TEST_VAR}")
            assert result == "test_value"

    def test_expand_var_in_string(self):
        """Test expanding env var embedded in string."""
        with patch.dict(os.environ, {'HOST': 'localhost'}):
            result = _expand_env_vars("https://${HOST}/api")
            assert result == "https://localhost/api"

    def test_expand_missing_var(self):
        """Test that missing env vars expand to empty string."""
        result = _expand_env_vars("${NONEXISTENT_VAR}")
        assert result == ""

    def test_expand_multiple_vars(self):
        """Test expanding multiple env vars."""
        with patch.dict(os.environ, {'HOST': 'localhost', 'PORT': '8080'}):
            result = _expand_env_vars("${HOST}:${PORT}")
            assert result == "localhost:8080"

    def test_expand_recursive_dict(self):
        """Test recursive expansion in dict."""
        with patch.dict(os.environ, {'API_KEY': 'secret'}):
            data = {'key': '${API_KEY}', 'nested': {'inner': '${API_KEY}'}}
            result = _expand_env_vars_recursive(data)
            assert result['key'] == 'secret'
            assert result['nested']['inner'] == 'secret'

    def test_expand_recursive_list(self):
        """Test recursive expansion in list."""
        with patch.dict(os.environ, {'VAR': 'value'}):
            data = ['${VAR}', 'static']
            result = _expand_env_vars_recursive(data)
            assert result == ['value', 'static']

    def test_expand_non_string(self):
        """Test that non-strings are returned unchanged."""
        result = _expand_env_vars_recursive(42)
        assert result == 42

        result = _expand_env_vars_recursive(None)
        assert result is None


class TestValidateConfig:
    """Tests for configuration validation."""

    def test_valid_irr_sources(self):
        """Test that all valid IRR sources are recognized."""
        assert 'RIPE' in VALID_IRR_SOURCES
        assert 'RADB' in VALID_IRR_SOURCES
        assert 'ARIN' in VALID_IRR_SOURCES
        assert 'APNIC' in VALID_IRR_SOURCES
        assert 'LACNIC' in VALID_IRR_SOURCES
        assert 'AFRINIC' in VALID_IRR_SOURCES
        assert 'NTTCOM' in VALID_IRR_SOURCES

    def test_validate_valid_config(self):
        """Test validation passes for valid config."""
        config = Config(
            irr_sources=['RIPE', 'RADB'],
            radb=RADBConfig(timeout_seconds=60, max_retries=3),
            ticketing=TicketingConfig(timeout_seconds=30, max_retries=3),
            logging=LoggingConfig(level='INFO', format='json'),
            diff=DiffConfig(lookback_hours=24),
        )
        # Should not raise
        validate_config(config)

    def test_validate_unknown_irr_source(self):
        """Test validation fails for unknown IRR source."""
        config = Config(irr_sources=['RIPE', 'UNKNOWN'])
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "Unknown IRR sources" in str(exc_info.value)

    def test_validate_empty_irr_sources(self):
        """Test validation fails for empty IRR sources."""
        config = Config(irr_sources=[])
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "At least one IRR source" in str(exc_info.value)

    def test_validate_negative_timeout(self):
        """Test validation fails for negative timeout."""
        config = Config(
            irr_sources=['RIPE'],
            radb=RADBConfig(timeout_seconds=-1),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "timeout_seconds must be positive" in str(exc_info.value)

    def test_validate_zero_timeout(self):
        """Test validation fails for zero timeout."""
        config = Config(
            irr_sources=['RIPE'],
            radb=RADBConfig(timeout_seconds=0),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "timeout_seconds must be positive" in str(exc_info.value)

    def test_validate_negative_retries(self):
        """Test validation fails for negative retries."""
        config = Config(
            irr_sources=['RIPE'],
            radb=RADBConfig(max_retries=-1),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "max_retries must be non-negative" in str(exc_info.value)

    def test_validate_invalid_log_level(self):
        """Test validation fails for invalid log level."""
        config = Config(
            irr_sources=['RIPE'],
            logging=LoggingConfig(level='INVALID'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "logging.level must be one of" in str(exc_info.value)

    def test_validate_invalid_log_format(self):
        """Test validation fails for invalid log format."""
        config = Config(
            irr_sources=['RIPE'],
            logging=LoggingConfig(format='xml'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "logging.format must be one of" in str(exc_info.value)

    def test_validate_multiple_errors(self):
        """Test validation reports multiple errors."""
        config = Config(
            irr_sources=[],
            radb=RADBConfig(timeout_seconds=0),
            logging=LoggingConfig(level='INVALID'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        error_msg = str(exc_info.value)
        # Should contain multiple errors
        assert "At least one IRR source" in error_msg
        assert "timeout_seconds must be positive" in error_msg
        assert "logging.level must be one of" in error_msg


class TestLoadConfig:
    """Tests for loading configuration from file."""

    def test_load_config_file_not_found(self):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_basic(self):
        """Test loading a basic config file."""
        config_content = """
irr_sources:
  - RIPE
targets:
  - AS15169
radb:
  timeout_seconds: 30
database:
  path: ./test.db
logging:
  level: DEBUG
  format: text
diff:
  lookback_hours: 12
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            config = load_config(f.name)

        assert config.irr_sources == ['RIPE']
        assert config.targets == ['AS15169']
        assert config.radb.timeout_seconds == 30
        assert config.database.path == './test.db'
        assert config.logging.level == 'DEBUG'
        assert config.logging.format == 'text'
        assert config.diff.lookback_hours == 12

        os.unlink(f.name)

    def test_load_config_env_override(self):
        """Test that environment variables override config values."""
        config_content = """
irr_sources:
  - RIPE
database:
  path: ./default.db
"""
        with patch.dict(os.environ, {'IRR_DB_PATH': '/custom/path.db'}):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(config_content)
                f.flush()
                config = load_config(f.name)

            assert config.database.path == '/custom/path.db'
            os.unlink(f.name)

    def test_load_config_ticketing_env_vars(self):
        """Test ticketing config from environment variables."""
        config_content = """
irr_sources:
  - RIPE
ticketing:
  base_url: "${ABC_BASE_URL}"
  api_token: "${ABC_TOKEN}"
"""
        with patch.dict(os.environ, {
            'ABC_BASE_URL': 'https://api.example.com',
            'ABC_TOKEN': 'secret-token',
        }):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(config_content)
                f.flush()
                config = load_config(f.name)

            assert config.ticketing.base_url == 'https://api.example.com'
            assert config.ticketing.api_token == 'secret-token'
            os.unlink(f.name)

    def test_load_config_empty_file(self):
        """Test loading empty config file uses defaults."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            f.flush()
            config = load_config(f.name)

        # Should have default values
        assert 'RADB' in config.irr_sources
        assert config.radb.timeout_seconds == 60

        os.unlink(f.name)

    def test_load_config_validation_failure(self):
        """Test that invalid config raises validation error."""
        config_content = """
irr_sources:
  - INVALID_SOURCE
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_path = f.name
            f.write(config_content)
            f.flush()

        try:
            with pytest.raises(ConfigValidationError):
                load_config(temp_path)
        finally:
            os.unlink(temp_path)
