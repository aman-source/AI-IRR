"""Environment-based configuration for the IRR Prefix Lookup API."""

from pydantic_settings import BaseSettings


VALID_IRR_SOURCES = {"RIPE", "RADB", "ARIN", "APNIC", "LACNIC", "AFRINIC", "NTTCOM"}


class Settings(BaseSettings):
    timeout: int = 60
    max_retries: int = 3
    default_sources: str = "RIPE,RADB,ARIN,APNIC,LACNIC,AFRINIC,NTTCOM"
    radb_base_url: str = "https://rest.db.ripe.net"
    log_level: str = "INFO"
    cors_origins: str = "*"

    model_config = {"env_prefix": "IRR_API_"}

    @property
    def default_sources_list(self) -> list[str]:
        return [s.strip().upper() for s in self.default_sources.split(",")]


settings = Settings()
