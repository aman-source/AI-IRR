"""Pydantic request/response models for the IRR Prefix Lookup API."""

import re
from typing import Optional

from pydantic import BaseModel, field_validator


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
