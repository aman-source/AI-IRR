"""FastAPI dependency injection for BGPQ4Client, auth, and DB."""

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.bgpq4_client import BGPQ4Client
from app.store import SnapshotStore
from api.settings import settings


# ---------------------------------------------------------------------------
# BGPQ4 client
# ---------------------------------------------------------------------------

def get_bgpq4_client(request: Request) -> BGPQ4Client:
    """Retrieve the shared BGPQ4Client instance from app state."""
    return request.app.state.bgpq4_client


# ---------------------------------------------------------------------------
# API key auth
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Enforce X-API-Key header when IRR_API_API_KEY is configured."""
    if not settings.api_key:
        return  # auth not configured — open access
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# SQLite DB (per-request, auto-closed)
# ---------------------------------------------------------------------------

def get_db() -> SnapshotStore:
    """Open a SnapshotStore for the request and close it afterward."""
    store = SnapshotStore(settings.db_path)
    try:
        store.migrate()
        yield store
    finally:
        store.close()
