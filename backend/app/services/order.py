"""M4+M5: Shed order lifecycle and allocation engine orchestration.

Coordinates the full workflow:
  1. Create a shed order from a validated deficit plan
  2. Run the allocation engine (CRC split → BCC largest-remainder → greedy feeder selection)
  3. Manual feeder overrides (add/remove) in ALLOCATED state
  4. Validate order (push to operators)
  5. Cancel order

All functions receive an AsyncSession and flush (never commit) — the
caller's transaction boundary (FastAPI's get_db) handles commit/rollback.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.audit as audit
from app.services.zone_names import feeder_display_name
from app.engine.allocator import CrcShare, BccWeight, allocate_to_crcs, allocate_to_bccs
from app.engine.rules import (
    FeederCandidate, PRIORITY_WEIGHT, compute_fairness_score, is_eligible,
)
from app.engine.selector_greedy import select_feeders
from app.models.deficit import DeficitPlan, DeficitSlot
from app.models.enums import (
    AllocationLevel, DeficitPlanStatus, EventStatus, FeederStatus, OrderStatus, PriorityLevel,
)
from app.models.event import ShedEvent
from app.models.hierarchy import Bcc, Crc, Feeder, FeederHistory
from app.models.order import AllocationNode, FeederAssignment, ShedOrder
from app.models.parameters import Parameters
from app.models.users import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.ALLOCATED, OrderStatus.CANCELLED},
    OrderStatus.ALLOCATED: {OrderStatus.VALIDATED, OrderStatus.CANCELLED},
    OrderStatus.VALIDATED: {OrderStatus.ACTIVE, OrderStatus.CANCELLED},
    OrderStatus.ACTIVE: {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}


def _check_transition(current: OrderStatus, target: OrderStatus) -> None:
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise ValueError(
            f"Cannot transition from {current.value} to {target.value}"
        )


async def _load_order(db: AsyncSession, order_id: int) -> ShedOrder:
    """Load order with full allocation tree eagerly loaded."""
    result = await db.execute(
        select(ShedOrder)
        .options(
            selectinload(ShedOrder.allocation_nodes)
            .selectinload(AllocationNode.children)
            .selectinload(AllocationNode.children)
            .selectinload(AllocationNode.feeder_assignments)
            .selectinload(FeederAssignment.feeder),
            selectinload(ShedOrder.allocation_nodes)
            .selectinload(AllocationNode.children)
            .selectinload(AllocationNode.feeder_assignments)
            .selectinload(FeederAssignment.feeder),
            selectinload(ShedOrder.allocation_nodes)
            .selectinload(AllocationNode.feeder_assignments)
            .selectinload(FeederAssignment.feeder),
            selectinload(ShedOrder.plan)
            .selectinload(DeficitPlan.slots),
        )
        .where(ShedOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError(f"Order {order_id} not found")
    return order


# ---------------------------------------------------------------------------
# 1. Create order
# ---------------------------------------------------------------------------

async def create_order(
    db: AsyncSession, *, plan_id: int, actor: User,
) -> ShedOrder:
    """Create a DRAFT shed order from a validated deficit plan.

    Validates:
    - Plan exists and is VALIDATED
    - No existing order for this plan
    """
    plan = await db.get(DeficitPlan, plan_id)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found")
    if plan.status != DeficitPlanStatus.VALIDATED:
        raise ValueError(f"Plan {plan_id} is not VALIDATED (current: {plan.status.value})")

    # Check no existing order
    existing = await db.execute(
        select(ShedOrder.id).where(ShedOrder.plan_id == plan_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"An order already exists for plan {plan_id}")

    # Compute total deficit from non-zero slots
    result = await db.execute(
        select(func.coalesce(func.sum(DeficitSlot.deficit_mw), 0.0))
        .where(DeficitSlot.plan_id == plan_id, DeficitSlot.deficit_mw > 0)
    )
    total_deficit = float(result.scalar_one())

    order = ShedOrder(
        plan_id=plan_id,
        status=OrderStatus.DRAFT,
        total_deficit_mw=total_deficit,
        created_by=actor.id,
        allocation_nodes=[],
    )
    db.add(order)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="SHED_ORDER_CREATED", entity_type="shed_order",
        entity_id=str(order.id),
        payload={"plan_id": plan_id, "total_deficit_mw": total_deficit},
    )
    return order


# ---------------------------------------------------------------------------
# 2. Run allocation engine
# ---------------------------------------------------------------------------

async def run_allocation(
    db: AsyncSession, *, order_id: int, actor: User,
) -> ShedOrder:
    """Run the allocation engine: CRC split → BCC apportionment → feeder selection.

    Transitions order from DRAFT → ALLOCATED.
    """
    order = await _load_order(db, order_id)
    _check_transition(order.status, OrderStatus.ALLOCATED)

    # Clear any previous allocation (idempotent re-run from DRAFT)
    for node in list(order.allocation_nodes):
        await db.delete(node)
    await db.flush()

    # Load plan slots with deficit > 0
    result = await db.execute(
        select(DeficitSlot)
        .where(DeficitSlot.plan_id == order.plan_id, DeficitSlot.deficit_mw > 0)
        .order_by(DeficitSlot.slot_start)
    )
    deficit_slots = list(result.scalars().all())

    if not deficit_slots:
        raise ValueError("No deficit slots found — nothing to allocate")

    # Load grid topology
    crcs_result = await db.execute(select(Crc).order_by(Crc.id))
    crcs = list(crcs_result.scalars().all())
    crc_shares = [CrcShare(crc_id=c.id, share_key=c.share_key) for c in crcs]

    bccs_result = await db.execute(select(Bcc).order_by(Bcc.id))
    all_bccs = list(bccs_result.scalars().all())
    bccs_by_crc: dict[str, list[Bcc]] = {}
    for bcc in all_bccs:
        bccs_by_crc.setdefault(bcc.crc_id, []).append(bcc)

    # Load system parameters
    params = await db.get(Parameters, 1)
    rest_time_min = float(params.rest_time_min) if params else 180.0
    slot_size_min = float(params.slot_size_min) if params else 30.0
    max_duration_min = float(params.max_duration_min) if params else 45.0

    # Load all feeders with history (for fairness scoring)
    feeders_result = await db.execute(
        select(Feeder).options(selectinload(Feeder.history))
    )
    all_feeders = list(feeders_result.scalars().all())
    feeders_by_bcc: dict[str, list[Feeder]] = {}
    for f in all_feeders:
        feeders_by_bcc.setdefault(f.bcc_id, []).append(f)

    # Track virtual cumulative minutes and rotation history across slots
    virtual_extra_minutes: dict[str, float] = {}  # feeder_id -> extra minutes from prior slots
    virtual_last_shed_end: dict[str, datetime] = {}  # feeder_id -> end time of last planned shedding
    consecutive_shed_minutes: dict[str, float] = {}  # feeder_id -> continuous shed minutes without break

    for slot in deficit_slots:
        slot_duration = (slot.slot_end - slot.slot_start).total_seconds() / 60.0
        if slot_duration <= 0:
            slot_duration = float(slot_size_min)

        assigned_in_slot: set[str] = set()

        # --- NATIONAL node ---
        national_node = AllocationNode(
            order_id=order.id, slot_id=slot.id, parent_id=None,
            level=AllocationLevel.NATIONAL, entity_id="NATIONAL",
            target_mw=slot.deficit_mw, achieved_mw=0.0,
            shortfall_mw=0.0, is_partial=False,
        )
        db.add(national_node)
        await db.flush()

        # --- CRC split ---
        crc_targets = allocate_to_crcs(slot.deficit_mw, crc_shares)
        national_achieved = 0.0

        for crc in crcs:
            crc_target = crc_targets[crc.id]
            crc_node = AllocationNode(
                order_id=order.id, slot_id=slot.id, parent_id=national_node.id,
                level=AllocationLevel.CRC, entity_id=crc.id,
                target_mw=crc_target, achieved_mw=0.0,
                shortfall_mw=0.0, is_partial=False,
            )
            db.add(crc_node)
            await db.flush()

            if crc_target <= 0:
                continue

            # --- BCC apportionment ---
            crc_bccs = bccs_by_crc.get(crc.id, [])
            bcc_weights = [BccWeight(bcc_id=b.id, managed_load_mw=b.managed_load_mw) for b in crc_bccs]
            bcc_targets = allocate_to_bccs(crc_target, bcc_weights)

            crc_achieved = 0.0

            for bcc in crc_bccs:
                bcc_target = bcc_targets.get(bcc.id, 0)
                bcc_node = AllocationNode(
                    order_id=order.id, slot_id=slot.id, parent_id=crc_node.id,
                    level=AllocationLevel.BCC, entity_id=bcc.id,
                    target_mw=float(bcc_target), achieved_mw=0.0,
                    shortfall_mw=0.0, is_partial=False,
                )
                db.add(bcc_node)
                await db.flush()

                if bcc_target <= 0:
                    continue

                # --- Feeder selection ---
                bcc_feeders = feeders_by_bcc.get(bcc.id, [])
                eligible_candidates: list[FeederCandidate] = []

                for feeder in bcc_feeders:
                    # Continuous shedding check: cannot exceed max_duration_min without rotation
                    is_consec = (virtual_last_shed_end.get(feeder.id) == slot.slot_start)
                    prev_consec = consecutive_shed_minutes.get(feeder.id, 0.0) if is_consec else 0.0
                    if prev_consec + slot_duration > max_duration_min:
                        continue

                    hist = feeder.history
                    cum_min = float(hist.cumulative_minutes if hist else 0)
                    cum_min += virtual_extra_minutes.get(feeder.id, 0.0)
                    last_shed_end = virtual_last_shed_end.get(
                        feeder.id,
                        hist.last_shed_end if hist else None,
                    )

                    if not is_eligible(
                        priority=feeder.priority,
                        critical=feeder.critical,
                        status=feeder.status,
                        last_shed_end=last_shed_end,
                        slot_start=slot.slot_start,
                        rest_time_minutes=int(rest_time_min),
                        assigned_feeder_ids=assigned_in_slot,
                        feeder_id=feeder.id,
                        allow_resting=True,
                    ):
                        continue

                    if last_shed_end is not None:
                        elapsed_rest = (slot.slot_start - last_shed_end).total_seconds() / 60.0
                        rest_left = max(0.0, rest_time_min - elapsed_rest) if elapsed_rest < rest_time_min else 0.0
                    else:
                        rest_left = 0.0

                    weight = PRIORITY_WEIGHT.get(feeder.priority, 3)
                    score = compute_fairness_score(cum_min, feeder.priority)

                    eligible_candidates.append(FeederCandidate(
                        feeder_id=feeder.id,
                        name=feeder_display_name(feeder),
                        bcc_id=feeder.bcc_id,
                        avg_mw=feeder.avg_mw,
                        priority=feeder.priority,
                        cumulative_minutes=cum_min,
                        priority_weight=weight,
                        fairness_score=score,
                        zone_id=feeder.zone_id,
                        rest_time_left_min=round(rest_left, 1),
                    ))

                selection = select_feeders(float(bcc_target), eligible_candidates)

                # Persist feeder assignments
                for fc in selection.selected:
                    assignment = FeederAssignment(
                        node_id=bcc_node.id,
                        feeder_id=fc.feeder_id,
                        slot_id=slot.id,
                        assigned_mw=fc.avg_mw,
                        fairness_score=fc.fairness_score,
                        is_manual=False,
                        assigned_by=actor.id,
                    )
                    db.add(assignment)
                    assigned_in_slot.add(fc.feeder_id)
                    # Track virtual cumulative minutes and rotation history
                    virtual_extra_minutes[fc.feeder_id] = (
                        virtual_extra_minutes.get(fc.feeder_id, 0.0) + slot_duration
                    )
                    is_c = (virtual_last_shed_end.get(fc.feeder_id) == slot.slot_start)
                    if is_c:
                        consecutive_shed_minutes[fc.feeder_id] = (
                            consecutive_shed_minutes.get(fc.feeder_id, 0.0) + slot_duration
                        )
                    else:
                        consecutive_shed_minutes[fc.feeder_id] = slot_duration

                    virtual_last_shed_end[fc.feeder_id] = slot.slot_end

                bcc_node.achieved_mw = selection.achieved_mw
                bcc_node.shortfall_mw = selection.shortfall_mw
                bcc_node.is_partial = selection.is_partial
                crc_achieved += selection.achieved_mw

            # Update CRC node
            crc_node.achieved_mw = round(crc_achieved, 2)
            crc_node.shortfall_mw = round(max(0, crc_target - crc_achieved), 2)
            crc_node.is_partial = crc_node.shortfall_mw > 0
            national_achieved += crc_achieved

        # Update NATIONAL node
        national_node.achieved_mw = round(national_achieved, 2)
        national_node.shortfall_mw = round(max(0, slot.deficit_mw - national_achieved), 2)
        national_node.is_partial = national_node.shortfall_mw > 0

    await db.flush()

    # Transition to ALLOCATED
    order.status = OrderStatus.ALLOCATED
    order.allocated_at = datetime.now(UTC)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="ORDER_ALLOCATED", entity_type="shed_order",
        entity_id=str(order.id),
        payload={"slots_processed": len(deficit_slots)},
    )

    return await _load_order(db, order.id)


# ---------------------------------------------------------------------------
# 3. Manual overrides
# ---------------------------------------------------------------------------

async def add_feeder_override(
    db: AsyncSession, *, order_id: int, node_id: int, feeder_id: str, actor: User,
) -> ShedOrder:
    """Manually add a feeder to a BCC allocation node (ALLOCATED state only)."""
    order = await _load_order(db, order_id)
    if order.status != OrderStatus.ALLOCATED:
        raise ValueError("Manual overrides only allowed in ALLOCATED state")

    node = await db.get(AllocationNode, node_id)
    if node is None or node.order_id != order_id:
        raise ValueError(f"Node {node_id} not found in order {order_id}")
    if node.level != AllocationLevel.BCC:
        raise ValueError("Feeders can only be added to BCC-level nodes")

    feeder = await db.get(Feeder, feeder_id)
    if feeder is None:
        raise ValueError(f"Feeder {feeder_id} not found")

    # Check cross-slot uniqueness
    existing = await db.execute(
        select(FeederAssignment.id)
        .where(FeederAssignment.slot_id == node.slot_id, FeederAssignment.feeder_id == feeder_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Feeder {feeder_id} already assigned in this slot")

    hist = feeder.history
    cum_min = float(hist.cumulative_minutes if hist else 0)
    weight = PRIORITY_WEIGHT.get(feeder.priority, 3)
    score = compute_fairness_score(cum_min, feeder.priority)

    assignment = FeederAssignment(
        node_id=node_id, feeder_id=feeder_id, slot_id=node.slot_id,
        assigned_mw=feeder.avg_mw, fairness_score=score,
        is_manual=True, assigned_by=actor.id,
    )
    db.add(assignment)

    # Update node achieved MW
    node.achieved_mw = round(node.achieved_mw + feeder.avg_mw, 2)
    node.shortfall_mw = round(max(0, node.target_mw - node.achieved_mw), 2)
    node.is_partial = node.shortfall_mw > 0
    await db.flush()

    # Propagate up the tree
    await _propagate_achieved(db, node)

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="MANUAL_OVERRIDE", entity_type="feeder_assignment",
        entity_id=feeder_id,
        payload={"order_id": order_id, "node_id": node_id, "action": "add", "mw": feeder.avg_mw},
    )

    return await _load_order(db, order_id)


async def remove_feeder_override(
    db: AsyncSession, *, order_id: int, assignment_id: int, actor: User,
) -> ShedOrder:
    """Remove a feeder assignment from an allocated order (ALLOCATED state only)."""
    order = await _load_order(db, order_id)
    if order.status != OrderStatus.ALLOCATED:
        raise ValueError("Manual overrides only allowed in ALLOCATED state")

    assignment = await db.get(FeederAssignment, assignment_id)
    if assignment is None:
        raise ValueError(f"Assignment {assignment_id} not found")

    node = await db.get(AllocationNode, assignment.node_id)
    if node is None or node.order_id != order_id:
        raise ValueError(f"Assignment does not belong to order {order_id}")

    removed_mw = assignment.assigned_mw
    removed_feeder = assignment.feeder_id
    await db.delete(assignment)

    # Update node
    node.achieved_mw = round(max(0, node.achieved_mw - removed_mw), 2)
    node.shortfall_mw = round(max(0, node.target_mw - node.achieved_mw), 2)
    node.is_partial = node.shortfall_mw > 0
    await db.flush()

    await _propagate_achieved(db, node)

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="MANUAL_OVERRIDE", entity_type="feeder_assignment",
        entity_id=removed_feeder,
        payload={"order_id": order_id, "node_id": node.id, "action": "remove", "mw": removed_mw},
    )

    return await _load_order(db, order_id)


async def _propagate_achieved(db: AsyncSession, node: AllocationNode) -> None:
    """Recompute achieved_mw up the tree from a BCC node to its CRC and NATIONAL parents."""
    if node.parent_id is None:
        return

    parent = await db.get(AllocationNode, node.parent_id)
    if parent is None:
        return

    # Recompute parent's achieved from all children
    children_result = await db.execute(
        select(func.coalesce(func.sum(AllocationNode.achieved_mw), 0.0))
        .where(AllocationNode.parent_id == parent.id)
    )
    parent.achieved_mw = round(float(children_result.scalar_one()), 2)
    parent.shortfall_mw = round(max(0, parent.target_mw - parent.achieved_mw), 2)
    parent.is_partial = parent.shortfall_mw > 0
    await db.flush()

    # Continue up
    await _propagate_achieved(db, parent)


# ---------------------------------------------------------------------------
# 4. Validate order
# ---------------------------------------------------------------------------

async def validate_order(
    db: AsyncSession, *, order_id: int, actor: User,
) -> ShedOrder:
    """Transition order from ALLOCATED → VALIDATED (approve and push to operators)."""
    order = await _load_order(db, order_id)
    _check_transition(order.status, OrderStatus.VALIDATED)

    order.status = OrderStatus.VALIDATED
    order.validated_by = actor.id
    order.validated_at = datetime.now(UTC)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="ORDER_VALIDATED", entity_type="shed_order",
        entity_id=str(order.id), payload={},
    )

    return await _load_order(db, order_id)


# ---------------------------------------------------------------------------
# 5. Cancel order
# ---------------------------------------------------------------------------

async def cancel_order(
    db: AsyncSession, *, order_id: int, reason: str, actor: User,
) -> ShedOrder:
    """Cancel an order (allowed from DRAFT, ALLOCATED, or VALIDATED)."""
    order = await _load_order(db, order_id)
    _check_transition(order.status, OrderStatus.CANCELLED)

    order.status = OrderStatus.CANCELLED
    order.cancelled_by = actor.id
    order.cancelled_at = datetime.now(UTC)
    order.cancellation_reason = reason
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="ORDER_CANCELLED", entity_type="shed_order",
        entity_id=str(order.id),
        payload={"reason": reason},
    )

    return await _load_order(db, order_id)


# ---------------------------------------------------------------------------
# 6. Activate order (start field execution)
# ---------------------------------------------------------------------------

async def activate_order(
    db: AsyncSession, *, order_id: int, actor: User,
) -> ShedOrder:
    """Transition order from VALIDATED → ACTIVE (start field execution)."""
    order = await _load_order(db, order_id)
    _check_transition(order.status, OrderStatus.ACTIVE)

    order.status = OrderStatus.ACTIVE
    order.activated_at = datetime.now(UTC)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="ORDER_ACTIVATED", entity_type="shed_order",
        entity_id=str(order.id), payload={},
    )

    return await _load_order(db, order_id)


# ---------------------------------------------------------------------------
# 7. Complete order
# ---------------------------------------------------------------------------

async def complete_order(
    db: AsyncSession, *, order_id: int, actor: User,
) -> ShedOrder:
    """Transition order from ACTIVE → COMPLETED (all slots finished)."""
    order = await _load_order(db, order_id)
    _check_transition(order.status, OrderStatus.COMPLETED)

    order.status = OrderStatus.COMPLETED
    order.completed_at = datetime.now(UTC)
    await db.flush()

    await audit.log(
        db, actor_id=str(actor.id), actor_name=actor.name,
        action="ORDER_COMPLETED", entity_type="shed_order",
        entity_id=str(order.id), payload={},
    )

    return await _load_order(db, order_id)


# ---------------------------------------------------------------------------
# 8. Read operations (scope-filtered)
# ---------------------------------------------------------------------------

async def list_orders(db: AsyncSession, *, user: User) -> list[dict]:
    """List all orders with summary info, scope-filtered for CRC/BCC operators."""
    result = await db.execute(
        select(ShedOrder)
        .options(
            selectinload(ShedOrder.plan).selectinload(DeficitPlan.slots),
            selectinload(ShedOrder.allocation_nodes),
        )
        .order_by(ShedOrder.created_at.desc())
    )
    orders = list(result.scalars().all())

    items = []
    for order in orders:
        plan = order.plan

        # Scope filtering: CRC/BCC operators only see orders that have
        # allocation nodes matching their scope
        if user.role.value == "CRC_OPERATOR":
            has_scope = any(
                n.level == AllocationLevel.CRC and n.entity_id == user.scope_id
                for n in order.allocation_nodes
            )
            if not has_scope and order.status != OrderStatus.DRAFT:
                continue
        elif user.role.value == "BCC_OPERATOR":
            has_scope = any(
                n.level == AllocationLevel.BCC and n.entity_id == user.scope_id
                for n in order.allocation_nodes
            )
            if not has_scope and order.status != OrderStatus.DRAFT:
                continue

        shortfall_count = sum(
            1 for n in order.allocation_nodes
            if n.level == AllocationLevel.BCC and n.is_partial
        )

        items.append({
            "id": order.id,
            "plan_id": order.plan_id,
            "plan_date": plan.date if plan else None,
            "plan_mode": plan.mode.value if plan else None,
            "status": order.status,
            "total_deficit_mw": order.total_deficit_mw,
            "created_at": order.created_at,
            "shortfall_count": shortfall_count,
        })

    return items


async def get_order(
    db: AsyncSession, *, order_id: int, user: User,
) -> ShedOrder:
    """Get a single order with full allocation tree, scope-filtered."""
    order = await _load_order(db, order_id)

    # For scope-filtered views, we don't block access but the frontend
    # should filter the tree display. The API returns the full tree and
    # lets the frontend decide what to show based on user scope.
    return order


async def delete_order(
    db: AsyncSession, *, order_id: int, actor: User,
) -> None:
    """Delete a shed order, its allocation tree, associated events, and the underlying deficit plan."""
    order = await _load_order(db, order_id)
    plan_id = order.plan_id

    # 1. Clean up associated shed events and restore feeder status if open
    events_res = await db.execute(select(ShedEvent).where(ShedEvent.order_id == order_id))
    events = list(events_res.scalars().all())
    for ev in events:
        if ev.status == EventStatus.OPEN:
            feeder = await db.get(Feeder, ev.feeder_id)
            if feeder and feeder.status == FeederStatus.OPEN:
                feeder.status = FeederStatus.CLOSED
        await db.delete(ev)

    # 2. Delete all allocation nodes (cascades to assignments)
    for node in list(order.allocation_nodes):
        await db.delete(node)

    await audit.log(
        db,
        actor_id=str(actor.id),
        actor_name=actor.name,
        action="SHED_ORDER_DELETED",
        entity_type="shed_order",
        entity_id=str(order.id),
        payload={
            "plan_id": plan_id,
            "previous_status": order.status.value,
            "total_deficit_mw": order.total_deficit_mw,
        },
    )

    await db.delete(order)

    # 3. Totally remove the associated deficit plan so it doesn't reappear in the dropdown
    if plan_id:
        plan_res = await db.execute(
            select(DeficitPlan)
            .options(
                selectinload(DeficitPlan.slots).selectinload(DeficitSlot.revisions)
            )
            .where(DeficitPlan.id == plan_id)
        )
        plan = plan_res.scalar_one_or_none()
        if plan:
            for slot in list(plan.slots):
                for rev in list(slot.revisions):
                    await db.delete(rev)
                await db.delete(slot)
            await db.delete(plan)

    await db.flush()


