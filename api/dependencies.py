"""FastAPI dependency injection for RADBClient."""

from fastapi import Request

from app.radb_client import RADBClient


def get_radb_client(request: Request) -> RADBClient:
    """Retrieve the shared RADBClient instance from app state."""
    return request.app.state.radb_client
