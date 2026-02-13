"""FastAPI application for IRR Prefix Lookup API."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.bgpq4_client import BGPQ4Client
from api.dependencies import get_bgpq4_client
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
# Application lifespan — create / destroy the shared BGPQ4Client
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    app.state.bgpq4_client = BGPQ4Client(
        bgpq4_cmd=settings.bgpq4_cmd_list,
        timeout=settings.bgpq4_timeout,
        source=settings.bgpq4_source,
        aggregate=settings.bgpq4_aggregate,
    )
    logging.getLogger("app").info("IRR Prefix Lookup API started (BGPQ4)")
    yield
    app.state.bgpq4_client.close()
    logging.getLogger("app").info("IRR Prefix Lookup API stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IRR Prefix Lookup API",
    version="2.0.0",
    description=(
        "REST API for querying Internet Routing Registry (IRR) databases "
        "via BGPQ4. Supports ASNs and AS-SETs with prefix aggregation."
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
    client: BGPQ4Client,
) -> PrefixResponse:
    start = time.perf_counter()
    result = await asyncio.to_thread(client.fetch_prefixes, target)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if not result.ipv4_prefixes and not result.ipv6_prefixes and result.errors:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "BGPQ4 query failed",
                "detail": "No prefixes could be retrieved",
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
        version="2.0.0",
        source=settings.bgpq4_source,
    )


@app.post(
    "/api/v1/fetch",
    response_model=PrefixResponse,
    responses={502: {"model": ErrorResponse}},
    tags=["Prefixes"],
)
async def fetch_prefixes(
    body: FetchRequest,
    client: BGPQ4Client = Depends(get_bgpq4_client),
):
    """Fetch IPv4/IPv6 prefixes for a target ASN or AS-SET."""
    return await _do_fetch(body.target, client)


@app.get(
    "/api/v1/prefixes/{target}",
    response_model=PrefixResponse,
    responses={502: {"model": ErrorResponse}},
    tags=["Prefixes"],
)
async def get_prefixes(
    target: str,
    client: BGPQ4Client = Depends(get_bgpq4_client),
):
    """Convenience GET endpoint for quick prefix lookups."""
    req = FetchRequest(target=target)
    return await _do_fetch(req.target, client)
