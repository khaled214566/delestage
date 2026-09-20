"""
M9 Administration router.

Endpoints:
  GET  /api/admin/parameters            → current parameters (any logged-in user)
  PATCH /api/admin/parameters           → update parameters (ADMIN only)

  GET  /api/admin/users                 → list users (ADMIN only)
  POST /api/admin/users                 → create user (ADMIN only)
  PATCH /api/admin/users/{id}/toggle   → activate/deactivate (ADMIN only)

  GET  /api/admin/audit                 → paginated audit log (ADMIN / DISPATCHER)
  GET  /api/admin/audit/verify          → verify hash chain (ADMIN only)
  GET  /api/admin/audit/export.csv      → download CSV (ADMIN only)
"""
from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.users import User
from app.schemas.admin import (
    AuditListResponse,
    AuditLogRead,
    ChainVerifyResponse,
    ParametersPatch,
    ParametersRead,
    UserCreate,
    UserRead,
)
from app.services.admin import (
    create_user,
    get_parameters,
    list_audit_logs,
    list_users,
    patch_parameters,
    toggle_user_active,
)
from app.services.audit import verify_chain

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ─── Dependency helpers ────────────────────────────────────────────────────────

def _require_admin(current: User = Depends(get_current_user)) -> User:
    if current.role != UserRole.ADMIN:
        raise HTTPException(403, "Admin role required")
    return current


def _require_admin_or_dispatcher(current: User = Depends(get_current_user)) -> User:
    if current.role not in (UserRole.ADMIN, UserRole.DISPATCHER):
        raise HTTPException(403, "Admin or Dispatcher role required")
    return current


# ─── Parameters ────────────────────────────────────────────────────────────────

@router.get("/parameters", response_model=ParametersRead)
async def read_parameters(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(get_current_user),   # any authenticated user
):
    return await get_parameters(db)


@router.patch("/parameters", response_model=ParametersRead)
async def update_parameters(
    patch: ParametersPatch,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(_require_admin),
):
    try:
        return await patch_parameters(
            db, patch,
            actor_id=str(current.id),
            actor_name=current.name,
        )
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


# ─── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserRead])
async def read_users(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_admin),
):
    return await list_users(db)


@router.post("/users", response_model=UserRead, status_code=201)
async def add_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(_require_admin),
):
    try:
        user = await create_user(
            db, body,
            actor_id=str(current.id),
            actor_name=current.name,
        )
        await db.commit()
        await db.refresh(user)
        return user
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/users/{user_id}/toggle", response_model=UserRead)
async def toggle_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(_require_admin),
):
    try:
        user = await toggle_user_active(
            db, user_id,
            actor_id=str(current.id),
            actor_name=current.name,
        )
        await db.commit()
        await db.refresh(user)
        return user
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ─── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit", response_model=AuditListResponse)
async def read_audit_log(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    action: str | None = None,
    actor: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_admin_or_dispatcher),
):
    total, items = await list_audit_logs(db, page, page_size, action, actor)
    return AuditListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/audit/verify", response_model=ChainVerifyResponse)
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_admin),
):
    return await verify_chain(db)


@router.get("/audit/export.csv")
async def export_audit_csv(
    action: str | None = None,
    actor: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_admin),
):
    _, items = await list_audit_logs(db, page=1, page_size=10_000, action_filter=action, actor_filter=actor)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["seq", "timestamp", "actor_id", "actor_name", "action",
                    "entity_type", "entity_id", "prev_hash", "hash"],
    )
    writer.writeheader()
    for item in items:
        writer.writerow({
            "seq": item.seq,
            "timestamp": item.timestamp.isoformat(),
            "actor_id": item.actor_id,
            "actor_name": item.actor_name,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "prev_hash": item.prev_hash,
            "hash": item.hash,
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'},
    )
