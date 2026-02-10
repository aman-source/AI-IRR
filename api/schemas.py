"""Pydantic request/response models for the IRR Prefix Lookup API."""

import re
from typing import Optional

from pydantic import BaseModel, field_validator

from api.settings import VALID_IRR_SOURCES


class FetchRequest(BaseModel):
    target: str
    irr_sources: Optional[list[str]] = None

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^AS\d+$", v):
            raise ValueError("target must be a valid ASN (e.g. AS15169)")
        return v

    @field_validator("irr_sources")
    @classmethod
    def validate_sources(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        normalized = []
        for s in v:
            s_upper = s.strip().upper()
            if s_upper not in VALID_IRR_SOURCES:
                raise ValueError(
                    f"Invalid IRR source '{s}'. "
                    f"Valid sources: {sorted(VALID_IRR_SOURCES)}"
                )
            normalized.append(s_upper)
        return normalized


class PrefixResponse(BaseModel):
    target: str
    ipv4_prefixes: list[str]
    ipv6_prefixes: list[str]
    ipv4_count: int
    ipv6_count: int
    sources_queried: list[str]
    errors: list[str]
    query_time_ms: int


class HealthResponse(BaseModel):
    status: str
    version: str
    irr_sources_available: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    errors: list[str] = []
