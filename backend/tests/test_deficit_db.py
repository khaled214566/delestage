"""Service-layer tests for M3 (deficit computation) against a real
PostgreSQL, each in a transaction that's always rolled back. These call
app.services.deficit directly rather than going over HTTP — consistent with
test_schema_db.py testing the DB layer directly rather than through the API.
"""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

import app.services.deficit as deficit_service
from app.models.deficit import DeficitPlan, DeficitRevision, DeficitSlot
from app.models.enums import DeficitPlanStatus, OrderType
from app.models.users import User

pytestmark = pytest.mark.db

PLAN_DATE = date(2026, 9, 19)

DOCUMENTED_CSV = """slot,demandMW,generationMW,importsMW,marginMW
19:00-19:30,4350,3800,200,50
19:30-20:00,4400,3800,200,50
20:00-20:30,4300,3800,200,50
20:30-21:00,4150,3800,200,50
21:00-21:30,4000,3800,200,50
"""


@pytest.fixture()
async def ahmed(adb) -> User:
    result = await adb.execute(select(User).where(User.username == "ahmed"))
    return result.scalar_one()


async def test_get_or_create_plan_is_idempotent(adb, ahmed):
    first = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    second = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    assert first.id == second.id
    assert first.status == DeficitPlanStatus.DRAFT


async def test_documented_csv_gives_documented_deficits(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    results = await deficit_service.import_csv(adb, plan=plan, csv_text=DOCUMENTED_CSV, actor=ahmed)

    assert [status for _, status in results] == ["created"] * 5
    assert [slot.deficit_mw for slot, _ in results] == [300, 350, 250, 100, 0]
    # The zero-deficit slot's raw calculation is negative (4000-3800-200-50=-50);
    # confirm it's actually floored, not coincidentally zero.
    assert results[-1][0].demand_mw - results[-1][0].generation_mw - results[-1][0].imports_mw - results[-1][0].margin_mw < 0


async def test_real_time_edit_and_revision_history(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    await deficit_service.import_csv(adb, plan=plan, csv_text=DOCUMENTED_CSV, actor=ahmed)

    slot_1900 = (await adb.execute(
        select(DeficitSlot).where(
            DeficitSlot.plan_id == plan.id,
            DeficitSlot.slot_start == datetime(2026, 9, 19, 19, 0, tzinfo=UTC),
        )
    )).scalar_one()
    assert slot_1900.deficit_mw == 300

    # "At 18:50 imports drop from 200 to 150" (doc, worked example 1)
    slot_1900, status = await deficit_service.apply_patch(
        adb, slot=slot_1900, patch={"imports_mw": 150.0}, actor=ahmed,
    )
    assert status == "updated"
    assert slot_1900.deficit_mw == 350

    revisions = (await adb.execute(
        select(DeficitRevision).where(DeficitRevision.slot_id == slot_1900.id)
    )).scalars().all()
    assert len(revisions) == 1
    assert revisions[0].old_values["imports_mw"] == 200
    assert revisions[0].new_values["imports_mw"] == 150
    assert revisions[0].old_values["deficit_mw"] == 300
    assert revisions[0].new_values["deficit_mw"] == 350
    assert revisions[0].changed_by == ahmed.id


async def test_reimporting_identical_csv_is_a_no_op(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    await deficit_service.import_csv(adb, plan=plan, csv_text=DOCUMENTED_CSV, actor=ahmed)

    results = await deficit_service.import_csv(adb, plan=plan, csv_text=DOCUMENTED_CSV, actor=ahmed)
    assert [status for _, status in results] == ["unchanged"] * 5

    revision_count = (await adb.execute(select(DeficitRevision))).scalars().all()
    assert revision_count == []  # no spurious revisions from re-importing the same values


async def test_validate_requires_at_least_one_slot(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.REAL_TIME, actor=ahmed)
    with pytest.raises(ValueError, match="no slots"):
        await deficit_service.validate_plan(adb, plan=plan, actor=ahmed)


async def test_validate_then_cannot_revalidate_or_reopen(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)
    await deficit_service.import_csv(adb, plan=plan, csv_text=DOCUMENTED_CSV, actor=ahmed)

    validated = await deficit_service.validate_plan(adb, plan=plan, actor=ahmed)
    assert validated.status == DeficitPlanStatus.VALIDATED
    assert validated.validated_by == ahmed.id

    with pytest.raises(ValueError, match="already validated"):
        await deficit_service.validate_plan(adb, plan=plan, actor=ahmed)

    with pytest.raises(ValueError, match="already VALIDATED"):
        await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.J_1, actor=ahmed)


async def test_p0_style_floor_never_goes_negative_end_to_end(adb, ahmed):
    plan = await deficit_service.get_or_create_plan(adb, plan_date=PLAN_DATE, mode=OrderType.REAL_TIME, actor=ahmed)
    slot, status = await deficit_service.upsert_slot(
        adb, plan=plan,
        slot_start=datetime(2026, 9, 19, 21, 0, tzinfo=UTC), slot_end=datetime(2026, 9, 19, 21, 30, tzinfo=UTC),
        demand_mw=4000, generation_mw=3800, imports_mw=200, margin_mw=50, actor=ahmed,
    )
    assert status == "created"
    assert slot.deficit_mw == 0
