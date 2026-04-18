"""Environment-based configuration for the IRR Prefix Lookup API."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bgpq4_cmd: str = "wsl,bgpq4"         # Comma-separated command parts
    bgpq4_sources: str = "RADB,RIPE,ARIN,APNIC,LACNIC,AFRINIC,RPKI"  # Comma-separated IRR sources
    bgpq4_timeout: int = 120
    bgpq4_aggregate: bool = True
    log_level: str = "INFO"
    cors_origins: str = "*"
    db_path: str = "./data/irr.sqlite"
    config_path: str = "./config.yaml"

    model_config = {"env_prefix": "IRR_API_"}

    @property
    def bgpq4_cmd_list(self) -> list[str]:
        return [s.strip() for s in self.bgpq4_cmd.split(",")]

    @property
    def bgpq4_sources_list(self) -> list[str]:
        return [s.strip() for s in self.bgpq4_sources.split(",") if s.strip()]


settings = Settings()
