"""FastAPI application for IRR Prefix Lookup API."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.radb_client import RADBClient
from api.dependencies import get_radb_client
from api.schemas import (
    ErrorResponse,
    FetchRequest,
    HealthResponse,
    PrefixResponse,
)
from api.settings import settings


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def _setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger = logging.getLogger("app")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False


# ---------------------------------------------------------------------------
# Application lifespan — create / destroy the shared RADBClient
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    app.state.radb_client = RADBClient(
        base_url=settings.radb_base_url,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
    )
    logging.getLogger("app").info("IRR Prefix Lookup API started")
    yield
    app.state.radb_client.close()
    logging.getLogger("app").info("IRR Prefix Lookup API stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IRR Prefix Lookup API",
    version="1.0.0",
    description=(
        "REST API for querying Internet Routing Registry (IRR) databases. "
        "Supports RIPE, RADB, ARIN, APNIC, LACNIC, AFRINIC, and NTTCOM."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------
async def _do_fetch(
    target: str,
    irr_sources: list[str],
    client: RADBClient,
) -> PrefixResponse:
    start = time.perf_counter()
    result = await asyncio.to_thread(client.fetch_prefixes, target, irr_sources)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if not result.ipv4_prefixes and not result.ipv6_prefixes and result.errors:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "All IRR sources failed",
                "detail": "No prefixes could be retrieved from any source",
                "errors": result.errors,
            },
        )

    return PrefixResponse(
        target=target,
        ipv4_prefixes=sorted(result.ipv4_prefixes),
        ipv6_prefixes=sorted(result.ipv6_prefixes),
        ipv4_count=len(result.ipv4_prefixes),
        ipv6_count=len(result.ipv6_prefixes),
        sources_queried=result.sources_queried,
        errors=result.errors,
        query_time_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        irr_sources_available=settings.default_sources_list,
    )


@app.post(
    "/api/v1/fetch",
    response_model=PrefixResponse,
    responses={502: {"model": ErrorResponse}},
    tags=["Prefixes"],
)
async def fetch_prefixes(
    body: FetchRequest,
    client: RADBClient = Depends(get_radb_client),
):
    """Fetch IPv4/IPv6 prefixes for a target ASN from selected IRR sources."""
    sources = body.irr_sources or settings.default_sources_list
    return await _do_fetch(body.target, sources, client)


@app.get(
    "/api/v1/prefixes/{asn}",
    response_model=PrefixResponse,
    responses={502: {"model": ErrorResponse}},
    tags=["Prefixes"],
)
async def get_prefixes(
    asn: str,
    sources: Optional[str] = Query(
        default=None,
        description="Comma-separated IRR sources (e.g. RIPE,RADB)",
    ),
    client: RADBClient = Depends(get_radb_client),
):
    """Convenience GET endpoint for quick prefix lookups."""
    # Validate & normalize ASN
    req = FetchRequest(target=asn, irr_sources=None)

    # Parse sources query param
    if sources:
        req.irr_sources = [s.strip() for s in sources.split(",") if s.strip()]
        req = FetchRequest(target=req.target, irr_sources=req.irr_sources)

    source_list = req.irr_sources or settings.default_sources_list
    return await _do_fetch(req.target, source_list, client)
