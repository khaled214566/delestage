from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import ShedEvent
from app.models.enums import EventStatus, AlarmLevel, PriorityLevel, FeederStatus, OrderStatus, UserRole
from app.models.hierarchy import Feeder, Bcc, Substation, FeederHistory
from app.models.order import ShedOrder, AllocationNode, FeederAssignment
from app.models.parameters import Parameters
from app.models.users import User
from app.schemas.execution import ConfirmOpenRequest, ConfirmCloseRequest, BccExecutionDashboard, FeederExecutionItem
from app.services import audit
from app.services import monitoring as monitoring_service
from app.core.websocket import ws_manager


async def get_bcc_dashboard(db: AsyncSession, bcc_id: str, user: User) -> BccExecutionDashboard:
    """Retrieve operational dashboard view for a BCC Operator."""
    now = datetime.now(timezone.utc)

    # 1. Scope enforcement: BCC operators can only see their own BCC
    if user.role == UserRole.BCC_OPERATOR and user.scope_id != bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: you are scoped to {user.scope_id}, not {bcc_id}",
        )

    bcc = await db.get(Bcc, bcc_id)
    if not bcc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"BCC '{bcc_id}' not found")

    params = await db.get(Parameters, 1)
    rest_time_min = params.rest_time_min if params else 180
    max_duration_min = params.max_duration_min if params else 45.0

    # 2. Get active order target for this BCC
    order_query = (
        select(ShedOrder)
        .where(ShedOrder.status.in_([OrderStatus.ACTIVE, OrderStatus.VALIDATED, OrderStatus.ALLOCATED]))
        .order_by(ShedOrder.id.desc())
        .limit(1)
    )
    active_order = (await db.execute(order_query)).scalar_one_or_none()

    target_mw = 0.0
    planned_feeder_ids: set[str] = set()
    if active_order:
        node_query = select(AllocationNode).where(
            AllocationNode.order_id == active_order.id,
            AllocationNode.entity_id == bcc_id,
        )
        bcc_node = (await db.execute(node_query)).scalar_one_or_none()
        if bcc_node:
            target_mw = bcc_node.target_mw
            # Fetch assigned feeders
            fa_query = select(FeederAssignment.feeder_id).where(FeederAssignment.node_id == bcc_node.id)
            planned_feeder_ids = set((await db.execute(fa_query)).scalars().all())

    # 3. Load all feeders in this BCC with substation and history
    feeders_query = (
        select(Feeder)
        .options(selectinload(Feeder.substation), selectinload(Feeder.history))
        .where(Feeder.bcc_id == bcc_id)
        .order_by(Feeder.priority.asc(), Feeder.id.asc())
    )
    feeders = list((await db.execute(feeders_query)).scalars().all())

    # Load open events for this BCC
    events_query = (
        select(ShedEvent)
        .where(ShedEvent.bcc_id == bcc_id, ShedEvent.status == EventStatus.OPEN)
    )
    open_events = {ev.feeder_id: ev for ev in (await db.execute(events_query)).scalars().all()}

    actual_mw = sum(ev.mw_actual for ev in open_events.values())
    gap_mw = round(target_mw - actual_mw, 1)

    items: List[FeederExecutionItem] = []
    for f in feeders:
        open_ev = open_events.get(f.id)
        is_open = open_ev is not None or f.status == FeederStatus.OPEN

        # Eligibility check
        is_eligible = True
        ineligibility_reason: Optional[str] = None
        rest_left: Optional[float] = None

        if f.priority == PriorityLevel.P0 or f.critical:
            is_eligible = False
            ineligibility_reason = "Ligne P0 prioritaire (infrastructure critique, coupure interdite)"
        elif is_open:
            is_eligible = False
            ineligibility_reason = "Ligne déjà déconnectée"
        elif f.status in (FeederStatus.MAINTENANCE, FeederStatus.UNAVAILABLE):
            is_eligible = False
            ineligibility_reason = f"Ligne indisponible ({f.status.value})"
        elif f.history and f.history.last_shed_end:
            elapsed_rest = (now - f.history.last_shed_end).total_seconds() / 60.0
            if elapsed_rest < rest_time_min:
                is_eligible = False
                rest_left = round(rest_time_min - elapsed_rest, 1)
                ineligibility_reason = f"En repos ({rest_left} min restantes sur {rest_time_min} min)"

        elapsed_mins: Optional[float] = None
        alarm_lvl: Optional[str] = None
        if open_ev:
            elapsed_mins = open_ev.compute_duration(now)
            alarm_lvl = open_ev.get_alarm_level(max_duration_min, now).value

        items.append(
            FeederExecutionItem(
                feeder_id=f.id,
                feeder_name=f.name,
                substation_name=f.substation.name if f.substation else "",
                priority=f.priority.value,
                is_critical=f.critical,
                avg_mw=f.avg_mw,
                status=FeederStatus.OPEN.value if is_open else f.status.value,
                is_eligible=is_eligible,
                ineligibility_reason=ineligibility_reason,
                rest_time_left_min=rest_left,
                is_planned_in_order=f.id in planned_feeder_ids,
                current_event_id=open_ev.id if open_ev else None,
                open_time=open_ev.open_time if open_ev else None,
                elapsed_minutes=elapsed_mins,
                alarm_level=alarm_lvl,
            )
        )

    return BccExecutionDashboard(
        bcc_id=bcc.id,
        bcc_name=bcc.name,
        target_mw=round(target_mw, 1),
        actual_mw=round(actual_mw, 1),
        gap_mw=gap_mw,
        open_feeders_count=len(open_events),
        feeders=items,
    )


async def confirm_opening(db: AsyncSession, req: ConfirmOpenRequest, user: User) -> ShedEvent:
    """
    UC5: Confirm manual breaker opening on terrain.
    Locks feeder row, validates P0 and rest time rules, creates OPEN event,
    starts timer, records in audit log and broadcasts telemetry.
    """
    now = datetime.now(timezone.utc)
    open_time = req.open_time or now

    # Lock feeder row for concurrency protection
    query = (
        select(Feeder)
        .options(selectinload(Feeder.history))
        .where(Feeder.id == req.feeder_id)
        .with_for_update()
    )
    feeder = (await db.execute(query)).scalar_one_or_none()
    if not feeder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Feeder '{req.feeder_id}' not found")

    # Scope verification
    if user.role == UserRole.BCC_OPERATOR and user.scope_id != feeder.bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Out of scope: cannot operate feeder belonging to {feeder.bcc_id}",
        )

    # Hard Rule: P0 and Critical infrastructure can NEVER be shed
    if feeder.priority == PriorityLevel.P0 or feeder.critical:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="P0 feeder cannot be shed. Strict safety constraint.",
        )

    # Check if already open
    existing_open = (
        await db.execute(
            select(ShedEvent).where(ShedEvent.feeder_id == feeder.id, ShedEvent.status == EventStatus.OPEN)
        )
    ).scalar_one_or_none()
    if existing_open or feeder.status == FeederStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Feeder '{feeder.id}' is already OPEN",
        )

    # Rest time verification (180 min standard)
    params = await db.get(Parameters, 1)
    rest_time_min = params.rest_time_min if params else 180

    if feeder.history and feeder.history.last_shed_end:
        elapsed_rest = (open_time - feeder.history.last_shed_end).total_seconds() / 60.0
        if elapsed_rest < rest_time_min and not req.justification:
            rest_left = round(rest_time_min - elapsed_rest)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rest time violated ({rest_left} min remaining). Written justification is required.",
            )

    # Create OPEN ShedEvent
    event = ShedEvent(
        order_id=req.order_id,
        feeder_id=feeder.id,
        bcc_id=feeder.bcc_id,
        open_time=open_time,
        mw_before=feeder.avg_mw,
        mw_actual=req.mw_actual,
        operator_id=user.id,
        status=EventStatus.OPEN,
    )
    db.add(event)

    # Update feeder status
    feeder.status = FeederStatus.OPEN
    if feeder.history:
        feeder.history.last_shed_start = open_time

    # Record in cryptographic audit trail
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="FEEDER_OPENED",
        entity="feeder",
        entity_id=feeder.id,
        payload={
            "feeder_id": feeder.id,
            "order_id": req.order_id,
            "mw_actual": req.mw_actual,
            "justification": req.justification,
        },
    )

    await db.commit()
    await db.refresh(event)

    # Broadcast telemetry
    summary = await monitoring_service.get_monitoring_summary(db)
    await ws_manager.broadcast(summary.model_dump(mode="json"))

    return event


async def confirm_restoration(db: AsyncSession, event_id: int, req: ConfirmCloseRequest, user: User) -> ShedEvent:
    """
    UC7: Confirm breaker re-energization / restoration.
    Locks event and feeder, sets close_time, computes duration & ENS,
    updates feeder_history in SAME transaction, logs audit trail and broadcasts telemetry.
    """
    now = datetime.now(timezone.utc)
    close_time = req.close_time or now

    # Lock event row
    ev_query = (
        select(ShedEvent)
        .where(ShedEvent.id == event_id)
        .with_for_update()
    )
    event = (await db.execute(ev_query)).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event #{event_id} not found")

    if event.status != EventStatus.OPEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Event #{event_id} is already closed")

    # Lock feeder row
    f_query = (
        select(Feeder)
        .options(selectinload(Feeder.history))
        .where(Feeder.id == event.feeder_id)
        .with_for_update()
    )
    feeder = (await db.execute(f_query)).scalar_one_or_none()
    if not feeder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Feeder '{event.feeder_id}' not found")

    # Scope verification
    if user.role == UserRole.BCC_OPERATOR and user.scope_id != feeder.bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Out of scope: cannot restore feeder belonging to {feeder.bcc_id}",
        )

    if close_time < event.open_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="close_time cannot precede open_time")

    # Compute duration and ENS
    duration_minutes = (close_time - event.open_time).total_seconds() / 60.0
    ens_mwh = round(event.mw_actual * duration_minutes / 60.0, 3)

    event.close_time = close_time
    event.duration_min = round(duration_minutes, 1)
    event.ens_mwh = ens_mwh
    event.status = EventStatus.CLOSED

    # Update feeder and history in the same transaction
    feeder.status = FeederStatus.CLOSED
    if feeder.history:
        feeder.history.cumulative_minutes += int(round(duration_minutes))
        feeder.history.rotations += 1
        feeder.history.last_shed_end = close_time

    # Record in cryptographic audit trail
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="FEEDER_RESTORED",
        entity="feeder",
        entity_id=feeder.id,
        payload={
            "feeder_id": feeder.id,
            "event_id": event.id,
            "duration_min": round(duration_minutes, 1),
            "ens_mwh": ens_mwh,
            "rotations": feeder.history.rotations if feeder.history else 1,
        },
    )

    await db.commit()
    await db.refresh(event)

    # Broadcast telemetry
    summary = await monitoring_service.get_monitoring_summary(db)
    await ws_manager.broadcast(summary.model_dump(mode="json"))

    return event
