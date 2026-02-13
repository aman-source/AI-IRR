"""Environment-based configuration for the IRR Prefix Lookup API."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bgpq4_cmd: str = "wsl,bgpq4"         # Comma-separated command parts
    bgpq4_source: str = "RADB"
    bgpq4_timeout: int = 120
    bgpq4_aggregate: bool = True
    log_level: str = "INFO"
    cors_origins: str = "*"

    model_config = {"env_prefix": "IRR_API_"}

    @property
    def bgpq4_cmd_list(self) -> list[str]:
        return [s.strip() for s in self.bgpq4_cmd.split(",")]


settings = Settings()
