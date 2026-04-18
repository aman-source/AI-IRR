"""FastAPI dependency injection for BGPQ4Client and SnapshotStore."""

from fastapi import Request

from app.bgpq4_client import BGPQ4Client
from app.store import SnapshotStore


def get_bgpq4_client(request: Request) -> BGPQ4Client:
    """Retrieve the shared BGPQ4Client instance from app state."""
    return request.app.state.bgpq4_client


def get_store(request: Request) -> SnapshotStore:
    """FastAPI dependency to access the SnapshotStore from app.state."""
    return request.app.state.store
