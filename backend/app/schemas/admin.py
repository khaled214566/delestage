"""Pydantic schemas for M9 — Administration, Parameters & Audit."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─── Parameters ────────────────────────────────────────────────────────────────

class ParametersRead(BaseModel):
    id: int
    max_duration_min: int
    rest_time_min: int
    slot_size_min: int
    rotation_warn_pct: int
    regional_key: dict[str, float]

    model_config = {"from_attributes": True}


class ParametersPatch(BaseModel):
    """All fields optional — send only the ones you want to change."""
    max_duration_min: int | None = Field(None, gt=0, le=240)
    rest_time_min: int | None = Field(None, ge=0, le=1440)
    slot_size_min: int | None = Field(None)
    rotation_warn_pct: int | None = Field(None, ge=1, le=100)

    @field_validator("slot_size_min")
    @classmethod
    def slot_must_be_15_or_30(cls, v: int | None) -> int | None:
        if v is not None and v not in (15, 30):
            raise ValueError("slot_size_min must be 15 or 30")
        return v


# ─── Users ─────────────────────────────────────────────────────────────────────

class UserRead(BaseModel):
    id: int
    username: str
    name: str
    role: str
    scope_type: str
    scope_id: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8)
    role: str
    scope_type: str = "national"
    scope_id: str | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        valid = {"DISPATCHER", "CRC_OPERATOR", "BCC_OPERATOR", "ADMIN"}
        if v not in valid:
            raise ValueError(f"role must be one of {valid}")
        return v

    @field_validator("scope_type")
    @classmethod
    def scope_type_must_be_valid(cls, v: str) -> str:
        valid = {"national", "crc", "bcc"}
        if v not in valid:
            raise ValueError(f"scope_type must be one of {valid}")
        return v


# ─── Audit ─────────────────────────────────────────────────────────────────────

class AuditLogRead(BaseModel):
    seq: int
    timestamp: datetime
    actor_id: str
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    payload: Any
    prev_hash: str
    hash: str

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogRead]


class ChainVerifyResponse(BaseModel):
    ok: bool
    total_checked: int
    broken_at_seq: int | None
