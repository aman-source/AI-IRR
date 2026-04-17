"""FastAPI application for IRR Prefix Lookup API."""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.bgpq4_client import BGPQ4Client
from app.config import load_config
from app.diff import compute_diff
from app.store import SnapshotStore
from api.dependencies import get_bgpq4_client, get_store
from api.schemas import (
    ErrorResponse,
    FetchRequest,
    HealthResponse,
    OverviewStats,
    PrefixResponse,
    RunResult,
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
# Application lifespan — create / destroy the shared BGPQ4Client and SnapshotStore
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    app.state.bgpq4_client = BGPQ4Client(
        bgpq4_cmd=settings.bgpq4_cmd_list,
        timeout=settings.bgpq4_timeout,
        sources=settings.bgpq4_sources_list,
        aggregate=settings.bgpq4_aggregate,
    )
    db_path = settings.db_path
    store = SnapshotStore(db_path)
    store.migrate()
    app.state.store = store
    logging.getLogger("app").info("IRR Prefix Lookup API started (BGPQ4)")
    yield
    store.close()
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

    # If no prefixes were retrieved at all and there are errors, fail with 502
    if not result.ipv4_prefixes and not result.ipv6_prefixes and result.errors:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "BGPQ4 query failed",
                "detail": "No prefixes could be retrieved",
                "errors": result.errors,
            },
        )

    # Return partial results with errors if at least one IP version succeeded
    return PrefixResponse(
        target=target,
        ipv4_prefixes=sorted(result.ipv4_prefixes),
        ipv6_prefixes=sorted(result.ipv6_prefixes),
        ipv4_raw_count=result.ipv4_raw_count,
        ipv4_count=len(result.ipv4_prefixes),
        ipv6_raw_count=result.ipv6_raw_count,
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
        sources=settings.bgpq4_sources_list,
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
    try:
        req = FetchRequest(target=target)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return await _do_fetch(req.target, client)


# ---------------------------------------------------------------------------
# Target management endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/targets",
    response_model=List[str],
    tags=["Targets"],
)
async def list_targets(store: SnapshotStore = Depends(get_store)):
    """Return all tracked targets (those with at least one stored snapshot)."""
    return store.get_unique_targets()


@app.get(
    "/api/v1/overview",
    response_model=OverviewStats,
    tags=["Dashboard"],
)
async def get_overview(store: SnapshotStore = Depends(get_store)):
    """Return dashboard summary statistics."""
    since = int(time.time()) - 86400  # last 24 hours
    return OverviewStats(
        total_targets=store.count_unique_targets(),
        last_run_at=store.get_latest_run_at(),
        recent_diffs=store.count_recent_diffs(since),
        open_tickets=store.count_open_tickets(),
    )


@app.post(
    "/api/v1/run",
    response_model=RunResult,
    tags=["Dashboard"],
)
async def trigger_run(
    bgpq4_client: BGPQ4Client = Depends(get_bgpq4_client),
    store: SnapshotStore = Depends(get_store),
):
    """Trigger a fetch+diff run for all configured targets."""
    try:
        config = load_config(settings.config_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="config.yaml not found")

    targets_processed = 0
    diffs_found = 0
    tickets_created = 0  # ticket creation not yet implemented via API
    errors: List[str] = []

    for target in config.targets:
        try:
            fetch_result = await asyncio.to_thread(bgpq4_client.fetch_prefixes, target)

            if fetch_result.errors and not fetch_result.ipv4_prefixes and not fetch_result.ipv6_prefixes:
                errors.append(f"{target}: fetch failed — {fetch_result.errors}")
                continue

            target_type = "asn" if re.match(r"^AS\d+$", target) else "as-set"
            lookback_seconds = config.diff.lookback_hours * 3600
            current_time = int(time.time())
            cutoff_time = current_time - lookback_seconds
            previous = store.get_snapshot_before(target, cutoff_time)

            snapshot_id = store.save_snapshot(
                target=target,
                target_type=target_type,
                irr_sources=list(fetch_result.sources_queried),
                ipv4_prefixes=list(fetch_result.ipv4_prefixes),
                ipv6_prefixes=list(fetch_result.ipv6_prefixes),
            )
            snapshot = store.get_snapshot_by_id(snapshot_id)

            diff = compute_diff(snapshot, previous)

            if diff and diff.has_changes:
                store.save_diff(
                    new_snapshot_id=snapshot_id,
                    old_snapshot_id=previous.id if previous else None,
                    target=target,
                    added_v4=diff.added_v4,
                    removed_v4=diff.removed_v4,
                    added_v6=diff.added_v6,
                    removed_v6=diff.removed_v6,
                    diff_hash=diff.diff_hash,
                )
                diffs_found += 1

            targets_processed += 1
        except Exception as exc:
            errors.append(f"{target}: {exc}")

    return RunResult(
        targets_processed=targets_processed,
        diffs_found=diffs_found,
        tickets_created=tickets_created,
        errors=errors,
    )
