"""Pydantic request/response models for the IRR Prefix Lookup API."""

import re
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class FetchRequest(BaseModel):
    target: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        v = v.strip().upper()
        # ASN: AS15169 (AS followed by digits)
        # AS-SET: AS-GOOGLE or AS-GOOGLE:EXAMPLE (AS- followed by alphanumeric/hyphen/colon)
        if not re.match(r"^AS(\d+|-[A-Z0-9][-A-Z0-9:]*)$", v):
            raise ValueError(
                "target must be a valid ASN (e.g. AS15169) or AS-SET (e.g. AS-GOOGLE or AS-GOOGLE:EXAMPLE)"
            )
        return v


class PrefixResponse(BaseModel):
    target: str
    ipv4_prefixes: list[str]
    ipv6_prefixes: list[str]
    ipv4_raw_count: int
    ipv4_count: int
    ipv6_raw_count: int
    ipv6_count: int
    sources_queried: list[str]
    errors: list[str]
    query_time_ms: int


class HealthResponse(BaseModel):
    status: str
    version: str
    sources: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    errors: list[str] = []


# --- Dashboard API schemas ---

class SnapshotOut(BaseModel):
    id: int
    target: str
    target_type: str
    timestamp: int
    irr_sources: List[str]
    ipv4_count: int
    ipv6_count: int
    content_hash: str
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class DiffOut(BaseModel):
    id: int
    target: str
    new_snapshot_id: int
    old_snapshot_id: Optional[int]
    added_v4: List[str]
    removed_v4: List[str]
    added_v6: List[str]
    removed_v6: List[str]
    has_changes: bool
    diff_hash: str
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class TicketOut(BaseModel):
    id: int
    target: str
    diff_id: int
    external_ticket_id: Optional[str]
    status: str
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int  # ceil(total / page_size)


class OverviewStats(BaseModel):
    total_targets: int
    last_run_at: Optional[int]   # Unix timestamp or None
    recent_diffs: int            # diffs in last 24h with has_changes=True
    open_tickets: int


class AddTargetRequest(BaseModel):
    target: str = Field(..., pattern=r'^(AS\d+|AS-[A-Z0-9_:-]+)$', description="ASN (AS12345) or AS-SET (AS-FOO)")


class RunResult(BaseModel):
    targets_processed: int
    diffs_found: int
    tickets_created: int
    errors: List[str]
