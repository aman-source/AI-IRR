"""FastAPI application for IRR Prefix Lookup API."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.bgpq4_client import BGPQ4Client
from app.store import SnapshotStore
from app.diff import DiffResult
from api.dependencies import get_bgpq4_client, get_db, verify_api_key
from api.schemas import (
    DiffHistoryResponse,
    DiffResponse,
    ErrorResponse,
    FetchRequest,
    HealthResponse,
    PrefixResponse,
    SnapshotHistoryResponse,
    SnapshotResponse,
    TargetSummary,
    TargetsResponse,
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
        sources=settings.bgpq4_sources_list,
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
# DB read endpoints (auth required)
# ---------------------------------------------------------------------------

def _fmt_ts(unix_ts: int) -> str:
    return datetime.utcfromtimestamp(unix_ts).isoformat() + "Z"


def _snapshot_to_response(s) -> SnapshotResponse:
    return SnapshotResponse(
        id=s.id,
        target=s.target,
        timestamp=_fmt_ts(s.timestamp),
        ipv4_prefixes=sorted(s.ipv4_prefixes),
        ipv6_prefixes=sorted(s.ipv6_prefixes),
        ipv4_count=len(s.ipv4_prefixes),
        ipv6_count=len(s.ipv6_prefixes),
        sources=s.irr_sources,
        content_hash=s.content_hash,
    )


def _diff_to_response(d) -> DiffResponse:
    parts = []
    if d.added_v4:
        parts.append(f"{len(d.added_v4)} added IPv4")
    if d.removed_v4:
        parts.append(f"{len(d.removed_v4)} removed IPv4")
    if d.added_v6:
        parts.append(f"{len(d.added_v6)} added IPv6")
    if d.removed_v6:
        parts.append(f"{len(d.removed_v6)} removed IPv6")
    summary = f"Detected {', '.join(parts)} prefixes for {d.target}" if parts else f"No changes for {d.target}"
    return DiffResponse(
        id=d.id,
        target=d.target,
        timestamp=_fmt_ts(d.created_at),
        has_changes=d.has_changes,
        added_v4=d.added_v4,
        removed_v4=d.removed_v4,
        added_v6=d.added_v6,
        removed_v6=d.removed_v6,
        summary=summary,
    )


@app.get(
    "/api/v1/targets",
    response_model=TargetsResponse,
    tags=["Database"],
    dependencies=[Depends(verify_api_key)],
)
def list_targets(db: SnapshotStore = Depends(get_db)):
    """List all monitored targets with their latest snapshot summary."""
    snapshots = db.get_all_targets()
    summaries = [
        TargetSummary(
            target=s.target,
            target_type=s.target_type,
            ipv4_count=len(s.ipv4_prefixes),
            ipv6_count=len(s.ipv6_prefixes),
            last_snapshot=_fmt_ts(s.timestamp),
            sources=s.irr_sources,
        )
        for s in snapshots
    ]
    return TargetsResponse(targets=summaries, total=len(summaries))


@app.get(
    "/api/v1/snapshots/{target}",
    response_model=SnapshotResponse,
    tags=["Database"],
    dependencies=[Depends(verify_api_key)],
)
def get_latest_snapshot(target: str, db: SnapshotStore = Depends(get_db)):
    """Get the latest prefix snapshot for a target."""
    snapshot = db.get_latest_snapshot(target.upper())
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {target.upper()}")
    return _snapshot_to_response(snapshot)


@app.get(
    "/api/v1/snapshots/{target}/history",
    response_model=SnapshotHistoryResponse,
    tags=["Database"],
    dependencies=[Depends(verify_api_key)],
)
def get_snapshot_history(
    target: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: SnapshotStore = Depends(get_db),
):
    """Get snapshot history for a target (newest first)."""
    snapshots = db.get_snapshot_history(target.upper(), limit)
    return SnapshotHistoryResponse(
        target=target.upper(),
        snapshots=[_snapshot_to_response(s) for s in snapshots],
    )


@app.get(
    "/api/v1/diffs/{target}",
    response_model=DiffResponse,
    tags=["Database"],
    dependencies=[Depends(verify_api_key)],
)
def get_latest_diff(target: str, db: SnapshotStore = Depends(get_db)):
    """Get the latest diff for a target."""
    diff = db.get_latest_diff(target.upper())
    if not diff:
        raise HTTPException(status_code=404, detail=f"No diff found for {target.upper()}")
    return _diff_to_response(diff)


@app.get(
    "/api/v1/diffs/{target}/history",
    response_model=DiffHistoryResponse,
    tags=["Database"],
    dependencies=[Depends(verify_api_key)],
)
def get_diff_history(
    target: str,
    limit: int = Query(default=10, ge=1, le=100),
    db: SnapshotStore = Depends(get_db),
):
    """Get diff history for a target (newest first)."""
    diffs = db.get_diff_history(target.upper(), limit)
    return DiffHistoryResponse(
        target=target.upper(),
        diffs=[_diff_to_response(d) for d in diffs],
    )
