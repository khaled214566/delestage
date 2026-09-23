"""
Deficit computation (M3 / UC1).

compute_deficit() is the only pure function here — everything else touches
the database and must run inside the caller's transaction (FastAPI's get_db
already provides one; this module only flushes, never commits).

Timezone note: the CSV format in the documentation gives slots as bare
'HH:MM-HH:MM' on the plan's date, with no timezone in the source material.
Every timestamp elsewhere in this codebase (feeder.created_at, audit_log,
etc.) is UTC, so import_csv() anchors the same way — documented here since
it's an assumption, not something the spec states outright.
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, date as date_, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit as audit
from app.models.deficit import DeficitPlan, DeficitRevision, DeficitSlot
from app.models.enums import DeficitPlanStatus, OrderType
from app.models.users import User

_EDITABLE_FIELDS = ("demand_mw", "generation_mw", "imports_mw", "margin_mw", "deficit_mw")


def compute_deficit(demand_mw: float, generation_mw: float, imports_mw: float, margin_mw: float) -> float:
    """P_deficit = Demand - Generation - Imports - Margin, floored at 0.

    0 or below means no shedding for that slot — treated identically to a
    negative result, matching the documentation's own worked example
    (21:00-21:30: 4000-3800-200-50 = -50, shown as 0 MW).
    """
    return max(0.0, demand_mw - generation_mw - imports_mw - margin_mw)


def _snapshot(slot: DeficitSlot) -> dict:
    return {f: getattr(slot, f) for f in _EDITABLE_FIELDS}


async def _record_update(
    db: AsyncSession, *, slot: DeficitSlot, new_values: dict, actor: User,
) -> tuple[DeficitSlot, str]:
    """Shared by upsert_slot's edit branch and apply_patch: diff, and only
    write a revision + audit entry if something actually changed, so
    re-sending identical values (e.g. re-importing the same CSV) is a no-op."""
    old_values = _snapshot(slot)
    if old_values == new_values:
        return slot, "unchanged"

    for field, value in new_values.items():
        setattr(slot, field, value)
    await db.flush()

    db.add(DeficitRevision(slot_id=slot.id, changed_by=actor.id, old_values=old_values, new_values=new_values))
    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name, action="DEFICIT_SLOT_EDITED",
        entity_type="deficit_slot", entity_id=str(slot.id),
        payload={"old": old_values, "new": new_values},
    )
    return slot, "updated"


async def get_or_create_plan(
    db: AsyncSession, *, plan_date: date_, mode: OrderType, actor: User,
) -> DeficitPlan:
    """Idempotent for a DRAFT plan. A VALIDATED plan for the same (date,
    mode) is left frozen — M3 has no "reopen" flow, so this raises instead
    of silently handing back a plan the dispatcher can no longer edit as if
    nothing were different."""
    result = await db.execute(
        select(DeficitPlan)
        .options(selectinload(DeficitPlan.slots))
        .where(DeficitPlan.date == plan_date, DeficitPlan.mode == mode)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if existing.status == DeficitPlanStatus.VALIDATED:
            raise ValueError(f"Plan for {plan_date} ({mode.value}) is already VALIDATED")
        return existing

    # slots=[] is required, not decorative: a freshly constructed ORM object
    # does NOT automatically count its empty relationship as "loaded" —
    # without this, Pydantic's response serialization tries to lazy-load
    # .slots outside the async greenlet context and raises MissingGreenlet.
    plan = DeficitPlan(date=plan_date, mode=mode, created_by=actor.id, slots=[])
    db.add(plan)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name, action="DEFICIT_PLAN_CREATED",
        entity_type="deficit_plan", entity_id=str(plan.id),
        payload={"date": plan_date.isoformat(), "mode": mode.value},
    )
    return plan


async def upsert_slot(
    db: AsyncSession,
    *,
    plan: DeficitPlan,
    slot_start: datetime,
    slot_end: datetime,
    demand_mw: float,
    generation_mw: float,
    imports_mw: float,
    margin_mw: float,
    actor: User,
) -> tuple[DeficitSlot, str]:
    """Create the slot if (plan_id, slot_start) is new, else edit it in
    place. Returns (slot, status): 'created', 'updated' or 'unchanged'."""
    deficit_mw = compute_deficit(demand_mw, generation_mw, imports_mw, margin_mw)

    result = await db.execute(
        select(DeficitSlot).where(DeficitSlot.plan_id == plan.id, DeficitSlot.slot_start == slot_start)
    )
    slot = result.scalar_one_or_none()

    if slot is None:
        slot = DeficitSlot(
            plan_id=plan.id, slot_start=slot_start, slot_end=slot_end,
            demand_mw=demand_mw, generation_mw=generation_mw,
            imports_mw=imports_mw, margin_mw=margin_mw, deficit_mw=deficit_mw,
        )
        db.add(slot)
        await db.flush()
        await audit.log(
            db, actor_id=str(actor.id), actor_name=actor.name, action="DEFICIT_SLOT_CREATED",
            entity_type="deficit_slot", entity_id=str(slot.id),
            payload={"plan_id": plan.id, **_snapshot(slot)},
        )
        return slot, "created"

    # An existing slot's window is fixed at creation; a later CSV row for the
    # same slot_start only ever edits the four numeric inputs.
    new_values = {
        "demand_mw": demand_mw, "generation_mw": generation_mw,
        "imports_mw": imports_mw, "margin_mw": margin_mw, "deficit_mw": deficit_mw,
    }
    return await _record_update(db, slot=slot, new_values=new_values, actor=actor)


async def apply_patch(
    db: AsyncSession, *, slot: DeficitSlot, patch: dict, actor: User,
) -> tuple[DeficitSlot, str]:
    """Partial edit of an existing slot by id (PATCH /slots/{slot_id}).
    `patch` holds only the fields the caller actually supplied."""
    merged = _snapshot(slot) | patch
    new_values = dict(merged)
    new_values["deficit_mw"] = compute_deficit(
        merged["demand_mw"], merged["generation_mw"], merged["imports_mw"], merged["margin_mw"],
    )
    return await _record_update(db, slot=slot, new_values=new_values, actor=actor)


async def import_csv(
    db: AsyncSession, *, plan: DeficitPlan, csv_text: str, actor: User,
) -> list[tuple[DeficitSlot, str]]:
    """Parses the exact format from documentation section 12: header row
    `slot,demandMW,generationMW,importsMW,marginMW`, then one row per slot,
    slot given as 'HH:MM-HH:MM' on the plan's own date."""
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"slot", "demandMW", "generationMW", "importsMW", "marginMW"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV is missing column(s): {', '.join(sorted(missing))}")

    results: list[tuple[DeficitSlot, str]] = []
    for row_num, row in enumerate(reader, start=2):  # header is row 1
        try:
            start_str, end_str = row["slot"].split("-")
            slot_start = datetime.combine(plan.date, time.fromisoformat(start_str.strip()), tzinfo=UTC)
            slot_end = datetime.combine(plan.date, time.fromisoformat(end_str.strip()), tzinfo=UTC)
            demand_mw = float(row["demandMW"])
            generation_mw = float(row["generationMW"])
            imports_mw = float(row["importsMW"])
            margin_mw = float(row["marginMW"])
        except (ValueError, KeyError) as exc:
            raise ValueError(f"CSV row {row_num} ({row!r}) is invalid: {exc}") from exc

        slot, status = await upsert_slot(
            db, plan=plan, slot_start=slot_start, slot_end=slot_end,
            demand_mw=demand_mw, generation_mw=generation_mw,
            imports_mw=imports_mw, margin_mw=margin_mw, actor=actor,
        )
        results.append((slot, status))
    return results


async def validate_plan(db: AsyncSession, *, plan: DeficitPlan, actor: User) -> DeficitPlan:
    if plan.status == DeficitPlanStatus.VALIDATED:
        raise ValueError("Plan is already validated")

    result = await db.execute(select(DeficitSlot.id).where(DeficitSlot.plan_id == plan.id).limit(1))
    if result.scalar_one_or_none() is None:
        raise ValueError("Cannot validate a plan with no slots")

    plan.status = DeficitPlanStatus.VALIDATED
    plan.validated_by = actor.id
    plan.validated_at = datetime.now(UTC)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name, action="DEFICIT_PLAN_VALIDATED",
        entity_type="deficit_plan", entity_id=str(plan.id), payload={},
    )
    return plan
