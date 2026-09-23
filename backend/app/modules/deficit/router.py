"""
Deficit computation router (M3 / UC1).

Mutating routes are DISPATCHER-only, matching the documentation's own
separation-of-duties principle (elsewhere the Admin is explicitly barred
from creating orders or confirming openings — deficit input is the same
kind of operational action, not an admin one). Reads are open to any
authenticated role: the deficit context isn't sensitive, and CRC/BCC
operators reasonably want the same situational awareness of it.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.deficit as deficit_service
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.deficit import DeficitPlan, DeficitRevision, DeficitSlot
from app.models.enums import UserRole
from app.models.users import User
from app.schemas.deficit import (
    CsvImportResult,
    DeficitPlanCreate,
    DeficitPlanOut,
    DeficitRevisionOut,
    DeficitSlotIn,
    DeficitSlotOut,
    DeficitSlotPatch,
)

router = APIRouter(prefix="/api/deficit", tags=["deficit"])

_dispatcher_or_admin = require_role(UserRole.DISPATCHER, UserRole.ADMIN)


async def _get_plan_or_404(db: AsyncSession, plan_id: int) -> DeficitPlan:
    result = await db.execute(
        select(DeficitPlan).options(selectinload(DeficitPlan.slots)).where(DeficitPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plan {plan_id} not found")
    return plan


async def _get_slot_or_404(db: AsyncSession, plan_id: int, slot_id: int) -> DeficitSlot:
    slot = await db.get(DeficitSlot, slot_id)
    if slot is None or slot.plan_id != plan_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Slot {slot_id} not found in plan {plan_id}")
    return slot


@router.post("/plans", response_model=DeficitPlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: DeficitPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> DeficitPlan:
    try:
        return await deficit_service.get_or_create_plan(db, plan_date=body.date, mode=body.mode, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/plans", response_model=list[DeficitPlanOut])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DeficitPlan]:
    result = await db.execute(
        select(DeficitPlan)
        .options(selectinload(DeficitPlan.slots))
        .order_by(DeficitPlan.date.desc(), DeficitPlan.id.desc())
    )
    return list(result.scalars().all())


@router.get("/plans/{plan_id}", response_model=DeficitPlanOut)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeficitPlan:
    return await _get_plan_or_404(db, plan_id)


@router.post("/plans/{plan_id}/slots", response_model=DeficitSlotOut, status_code=status.HTTP_201_CREATED)
async def upsert_slot(
    plan_id: int,
    body: DeficitSlotIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> DeficitSlot:
    plan = await _get_plan_or_404(db, plan_id)
    slot, _status = await deficit_service.upsert_slot(
        db, plan=plan, slot_start=body.slot_start, slot_end=body.slot_end,
        demand_mw=body.demand_mw, generation_mw=body.generation_mw,
        imports_mw=body.imports_mw, margin_mw=body.margin_mw, actor=user,
    )
    return slot


@router.patch("/plans/{plan_id}/slots/{slot_id}", response_model=DeficitSlotOut)
async def edit_slot(
    plan_id: int,
    slot_id: int,
    body: DeficitSlotPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> DeficitSlot:
    slot = await _get_slot_or_404(db, plan_id, slot_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    slot, _status = await deficit_service.apply_patch(db, slot=slot, patch=patch, actor=user)
    return slot


@router.post("/plans/{plan_id}/import-csv", response_model=CsvImportResult)
async def import_csv(
    plan_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> CsvImportResult:
    plan = await _get_plan_or_404(db, plan_id)
    raw = (await file.read()).decode("utf-8")
    try:
        results = await deficit_service.import_csv(db, plan=plan, csv_text=raw, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    created = sum(1 for _, s in results if s == "created")
    updated = sum(1 for _, s in results if s == "updated")
    return CsvImportResult(created=created, updated=updated, slots=[slot for slot, _ in results])


@router.post("/plans/{plan_id}/validate", response_model=DeficitPlanOut)
async def validate_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> DeficitPlan:
    plan = await _get_plan_or_404(db, plan_id)
    try:
        return await deficit_service.validate_plan(db, plan=plan, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/plans/{plan_id}/slots/{slot_id}/revisions", response_model=list[DeficitRevisionOut])
async def list_revisions(
    plan_id: int,
    slot_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DeficitRevision]:
    await _get_slot_or_404(db, plan_id, slot_id)
    result = await db.execute(
        select(DeficitRevision).where(DeficitRevision.slot_id == slot_id).order_by(DeficitRevision.changed_at)
    )
    return list(result.scalars().all())
