"""Tests for configuration module."""

import os
import tempfile
import pytest
from unittest.mock import patch

from app.config import (
    Config,
    BGPQ4Config,
    DatabaseConfig,
    TicketingConfig,
    LoggingConfig,
    DiffConfig,
    load_config,
    validate_config,
    get_default_config,
    ConfigValidationError,
    VALID_BGPQ4_SOURCES,
    _expand_env_vars,
    _expand_env_vars_recursive,
)


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_default_config(self):
        """Test that default config is created with expected values."""
        config = get_default_config()
        assert isinstance(config, Config)
        assert config.bgpq4.source == 'RADB'
        assert config.targets == []

    def test_bgpq4_config_defaults(self):
        """Test BGPQ4Config default values."""
        config = BGPQ4Config()
        assert config.cmd == ["wsl", "bgpq4"]
        assert config.timeout_seconds == 120
        assert config.source == "RADB"
        assert config.aggregate is True

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

    def test_valid_bgpq4_sources(self):
        """Test that all valid BGPQ4 sources are recognized."""
        assert 'RIPE' in VALID_BGPQ4_SOURCES
        assert 'RADB' in VALID_BGPQ4_SOURCES
        assert 'ARIN' in VALID_BGPQ4_SOURCES
        assert 'APNIC' in VALID_BGPQ4_SOURCES
        assert 'LACNIC' in VALID_BGPQ4_SOURCES
        assert 'AFRINIC' in VALID_BGPQ4_SOURCES
        assert 'NTTCOM' not in VALID_BGPQ4_SOURCES

    def test_validate_valid_config(self):
        """Test validation passes for valid config."""
        config = Config(
            bgpq4=BGPQ4Config(source='RADB', timeout_seconds=120),
            ticketing=TicketingConfig(timeout_seconds=30, max_retries=3),
            logging=LoggingConfig(level='INFO', format='json'),
            diff=DiffConfig(lookback_hours=24),
        )
        # Should not raise
        validate_config(config)

    def test_validate_unknown_bgpq4_source(self):
        """Test validation fails for unknown BGPQ4 source."""
        config = Config(bgpq4=BGPQ4Config(source='UNKNOWN'))
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "Unknown BGPQ4 source" in str(exc_info.value)

    def test_validate_nttcom_source_rejected(self):
        """Test that NTTCOM source is not valid."""
        config = Config(bgpq4=BGPQ4Config(source='NTTCOM'))
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "Unknown BGPQ4 source" in str(exc_info.value)

    def test_validate_negative_timeout(self):
        """Test validation fails for negative timeout."""
        config = Config(
            bgpq4=BGPQ4Config(timeout_seconds=-1),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "timeout_seconds must be positive" in str(exc_info.value)

    def test_validate_zero_timeout(self):
        """Test validation fails for zero timeout."""
        config = Config(
            bgpq4=BGPQ4Config(timeout_seconds=0),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "timeout_seconds must be positive" in str(exc_info.value)

    def test_validate_empty_cmd(self):
        """Test validation fails for empty command."""
        config = Config(
            bgpq4=BGPQ4Config(cmd=[]),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "bgpq4.cmd must not be empty" in str(exc_info.value)

    def test_validate_invalid_log_level(self):
        """Test validation fails for invalid log level."""
        config = Config(
            logging=LoggingConfig(level='INVALID'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "logging.level must be one of" in str(exc_info.value)

    def test_validate_invalid_log_format(self):
        """Test validation fails for invalid log format."""
        config = Config(
            logging=LoggingConfig(format='xml'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        assert "logging.format must be one of" in str(exc_info.value)

    def test_validate_multiple_errors(self):
        """Test validation reports multiple errors."""
        config = Config(
            bgpq4=BGPQ4Config(source='UNKNOWN', timeout_seconds=0),
            logging=LoggingConfig(level='INVALID'),
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(config)
        error_msg = str(exc_info.value)
        assert "Unknown BGPQ4 source" in error_msg
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
targets:
  - AS15169
bgpq4:
  source: RADB
  timeout_seconds: 60
  aggregate: true
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

        assert config.targets == ['AS15169']
        assert config.bgpq4.source == 'RADB'
        assert config.bgpq4.timeout_seconds == 60
        assert config.bgpq4.aggregate is True
        assert config.database.path == './test.db'
        assert config.logging.level == 'DEBUG'
        assert config.logging.format == 'text'
        assert config.diff.lookback_hours == 12

        os.unlink(f.name)

    def test_load_config_env_override(self):
        """Test that environment variables override config values."""
        config_content = """
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
        assert config.bgpq4.source == 'RADB'
        assert config.bgpq4.timeout_seconds == 120

        os.unlink(f.name)

    def test_load_config_bgpq4_custom_cmd(self):
        """Test loading config with custom bgpq4 command."""
        config_content = """
bgpq4:
  cmd: ["/usr/local/bin/bgpq4"]
  source: RIPE
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            f.flush()
            config = load_config(f.name)

        assert config.bgpq4.cmd == ["/usr/local/bin/bgpq4"]
        assert config.bgpq4.source == "RIPE"

        os.unlink(f.name)
