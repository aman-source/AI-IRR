"""FastAPI dependency injection for BGPQ4Client."""

from fastapi import Request

from app.bgpq4_client import BGPQ4Client


def get_bgpq4_client(request: Request) -> BGPQ4Client:
    """Retrieve the shared BGPQ4Client instance from app state."""
    return request.app.state.bgpq4_client
