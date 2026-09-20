"""Database integration tests for shed order lifecycle and allocation.

These tests require PostgreSQL at head (`alembic upgrade head`).
They are skipped when the database is unreachable.
"""
import pytest
from datetime import date, datetime, UTC
from sqlalchemy import select

from app.models.deficit import DeficitPlan, DeficitSlot
from app.models.enums import DeficitPlanStatus, OrderStatus, OrderType, UserRole
from app.models.users import User
from app.models.order import ShedOrder, OrderAllocationNode
from app.services import order as order_service

pytestmark = [pytest.mark.asyncio, pytest.mark.db]

async def _create_test_user(db, role="DISPATCHER"):
    from app.core.security import hash_password
    user = User(username=f"test_{role.lower()}_{datetime.now().timestamp()}", name=f"Test {role}", 
                hashed_password=hash_password("test123"),
                role=UserRole(role), scope_type="national", is_active=True)
    db.add(user)
    await db.flush()
    return user

async def _create_validated_plan(db, user):
    plan = DeficitPlan(date=date(2026, 9, 19), mode=OrderType.J_1,
                       status=DeficitPlanStatus.VALIDATED, created_by=user.id,
                       validated_by=user.id, validated_at=datetime.now(UTC), slots=[])
    db.add(plan)
    await db.flush()
    # Add a slot with 300 MW deficit
    slot = DeficitSlot(
        plan_id=plan.id, 
        slot_start=datetime(2026, 9, 19, 19, 0, tzinfo=UTC),
        slot_end=datetime(2026, 9, 19, 19, 30, tzinfo=UTC),
        demand_mw=4350, generation_mw=3800, imports_mw=200, margin_mw=50, deficit_mw=300
    )
    db.add(slot)
    await db.flush()
    return plan

async def test_create_order_from_validated_plan(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    assert order.status == OrderStatus.DRAFT
    assert order.plan_id == plan.id

async def test_create_order_from_draft_plan_fails(adb):
    user = await _create_test_user(adb)
    plan = DeficitPlan(date=date(2026, 9, 20), mode=OrderType.J_1,
                       status=DeficitPlanStatus.DRAFT, created_by=user.id)
    adb.add(plan)
    await adb.flush()
    
    with pytest.raises(ValueError):
        await order_service.create_order_from_plan(adb, plan.id, actor=user)

async def test_create_duplicate_order_fails(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    await order_service.create_order_from_plan(adb, plan.id, actor=user)
    with pytest.raises(ValueError):
        await order_service.create_order_from_plan(adb, plan.id, actor=user)

async def test_run_allocation(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    
    order = await order_service.run_allocation(adb, order.id, actor=user)
    assert order.status == OrderStatus.ALLOCATED
    nodes = (await adb.execute(select(OrderAllocationNode).where(OrderAllocationNode.order_id == order.id))).scalars().all()
    assert len(nodes) > 0

async def test_allocation_creates_tree(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    
    order = await order_service.run_allocation(adb, order.id, actor=user)
    
    nodes = (await adb.execute(select(OrderAllocationNode).where(OrderAllocationNode.order_id == order.id))).scalars().all()
    national_nodes = [n for n in nodes if n.node_type == "NATIONAL"]
    crc_nodes = [n for n in nodes if n.node_type == "CRC"]
    bcc_nodes = [n for n in nodes if n.node_type == "BCC"]
    
    assert len(national_nodes) == 1
    assert len(crc_nodes) > 0
    assert len(bcc_nodes) > 0
    for crc in crc_nodes:
        assert crc.parent_id == national_nodes[0].id
    for bcc in bcc_nodes:
        assert bcc.parent_id in [c.id for c in crc_nodes]

async def test_allocation_sum_conservation(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    
    order = await order_service.run_allocation(adb, order.id, actor=user)
    
    nodes = (await adb.execute(select(OrderAllocationNode).where(OrderAllocationNode.order_id == order.id))).scalars().all()
    national_nodes = [n for n in nodes if n.node_type == "NATIONAL"]
    crc_nodes = [n for n in nodes if n.node_type == "CRC"]
    
    assert sum(c.target_mw for c in crc_nodes) == national_nodes[0].target_mw

async def test_validate_order(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    await order_service.run_allocation(adb, order.id, actor=user)
    
    validated = await order_service.validate_order(adb, order.id, actor=user)
    assert validated.status == OrderStatus.VALIDATED

async def test_cancel_order(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    
    cancelled = await order_service.cancel_order(adb, order.id, reason="Testing cancellation", actor=user)
    assert cancelled.status == OrderStatus.CANCELLED

async def test_invalid_transition(adb):
    user = await _create_test_user(adb)
    plan = await _create_validated_plan(adb, user)
    order = await order_service.create_order_from_plan(adb, plan.id, actor=user)
    
    with pytest.raises(ValueError):
        await order_service.validate_order(adb, order.id, actor=user)
