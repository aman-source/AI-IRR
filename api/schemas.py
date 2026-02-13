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
        if not re.match(r"^AS[-\w:]+$", v):
            raise ValueError(
                "target must be a valid ASN (e.g. AS15169) or AS-SET (e.g. AS-GOOGLE)"
            )
        return v


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
    source: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    errors: list[str] = []
