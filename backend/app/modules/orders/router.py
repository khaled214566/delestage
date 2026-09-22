"""
Shed orders & allocation router (M4+M5 / UC2+UC3).

Mutating routes are DISPATCHER-only. Reads are scope-filtered: CRC/BCC
operators see only the portion of the allocation tree matching their scope.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.order as order_service
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.enums import UserRole
from app.models.users import User
from app.schemas.order import (
    CancelRequest,
    ManualFeederAdd,
    OrderListItem,
    ShedOrderCreate,
    ShedOrderOut,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

_dispatcher_or_admin = require_role(UserRole.DISPATCHER, UserRole.ADMIN)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post("", response_model=ShedOrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: ShedOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.create_order(db, plan_id=body.plan_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


# ---------------------------------------------------------------------------
# List & Get
# ---------------------------------------------------------------------------

@router.get("", response_model=list[OrderListItem])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[OrderListItem]:
    items = await order_service.list_orders(db, user=user)
    return [OrderListItem(**item) for item in items]


@router.get("/{order_id}", response_model=ShedOrderOut)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShedOrderOut:
    try:
        order = await order_service.get_order(db, order_id=order_id, user=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _order_to_out(order)


# ---------------------------------------------------------------------------
# Allocate (run engine)
# ---------------------------------------------------------------------------

@router.post("/{order_id}/allocate", response_model=ShedOrderOut)
async def allocate_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.run_allocation(db, order_id=order_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


# ---------------------------------------------------------------------------
# Manual overrides (ALLOCATED state only)
# ---------------------------------------------------------------------------

@router.post("/{order_id}/allocate/nodes/{node_id}/feeders", response_model=ShedOrderOut)
async def add_feeder(
    order_id: int,
    node_id: int,
    body: ManualFeederAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.add_feeder_override(
            db, order_id=order_id, node_id=node_id, feeder_id=body.feeder_id, actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


@router.delete("/{order_id}/allocate/assignments/{assignment_id}", response_model=ShedOrderOut)
async def remove_feeder(
    order_id: int,
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.remove_feeder_override(
            db, order_id=order_id, assignment_id=assignment_id, actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


# ---------------------------------------------------------------------------
# Validate & Cancel
# ---------------------------------------------------------------------------

@router.post("/{order_id}/validate", response_model=ShedOrderOut)
async def validate_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.validate_order(db, order_id=order_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


@router.post("/{order_id}/activate", response_model=ShedOrderOut)
async def activate_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.activate_order(db, order_id=order_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


@router.post("/{order_id}/complete", response_model=ShedOrderOut)
async def complete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.complete_order(db, order_id=order_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


@router.post("/{order_id}/cancel", response_model=ShedOrderOut)
async def cancel_order(
    order_id: int,
    body: CancelRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> ShedOrderOut:
    try:
        order = await order_service.cancel_order(
            db, order_id=order_id, reason=body.reason, actor=user,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_to_out(order)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_dispatcher_or_admin),
) -> None:
    try:
        await order_service.delete_order(db, order_id=order_id, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _node_to_out(node):
    """Recursively serialize an AllocationNode ORM object to the output schema."""
    from app.schemas.order import AllocationNodeOut, FeederAssignmentOut

    children_out = [_node_to_out(child) for child in (node.children or [])]
    assignments_out = []
    for a in (node.feeder_assignments or []):
        feeder = a.feeder
        assignments_out.append(FeederAssignmentOut(
            id=a.id,
            feeder_id=a.feeder_id,
            feeder_name=feeder.name if feeder else a.feeder_id,
            assigned_mw=a.assigned_mw,
            priority=feeder.priority.value if feeder else "?",
            fairness_score=a.fairness_score,
            is_manual=a.is_manual,
            assigned_at=a.assigned_at,
            assigned_by=a.assigned_by,
        ))

    return AllocationNodeOut(
        id=node.id,
        slot_id=node.slot_id,
        level=node.level,
        entity_id=node.entity_id,
        target_mw=node.target_mw,
        achieved_mw=node.achieved_mw,
        shortfall_mw=node.shortfall_mw,
        is_partial=node.is_partial,
        children=children_out,
        feeder_assignments=assignments_out,
    )


def _order_to_out(order) -> ShedOrderOut:
    """Convert a ShedOrder ORM object to the output schema, building the tree."""
    from app.schemas.order import ShedOrderOut

    # Only include root (NATIONAL) nodes — children are nested
    root_nodes = [n for n in (order.allocation_nodes or []) if n.parent_id is None]
    nodes_out = [_node_to_out(n) for n in root_nodes]

    return ShedOrderOut(
        id=order.id,
        plan_id=order.plan_id,
        status=order.status,
        total_deficit_mw=order.total_deficit_mw,
        created_by=order.created_by,
        created_at=order.created_at,
        allocated_at=order.allocated_at,
        validated_by=order.validated_by,
        validated_at=order.validated_at,
        activated_at=order.activated_at,
        completed_at=order.completed_at,
        cancelled_by=order.cancelled_by,
        cancelled_at=order.cancelled_at,
        cancellation_reason=order.cancellation_reason,
        allocation_nodes=nodes_out,
    )
