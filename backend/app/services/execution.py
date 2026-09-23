from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import ShedEvent
from app.models.enums import EventStatus, AlarmLevel, PriorityLevel, FeederStatus, OrderStatus, UserRole, OrderType, DeficitPlanStatus
from app.models.hierarchy import Feeder, Bcc, Substation, FeederHistory
from app.models.order import ShedOrder, AllocationNode, FeederAssignment
from app.models.deficit import DeficitPlan, DeficitSlot
from app.models.parameters import Parameters
from app.models.users import User
from app.schemas.execution import (
    ConfirmOpenRequest, ConfirmCloseRequest, BccExecutionDashboard, FeederExecutionItem,
    EmergencyAutoShedRequest, EmergencyAutoShedResponse, EmergencyCutFeederInfo,
)
from app.services import audit
from app.services import order as order_service
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
        node_query = (
            select(AllocationNode)
            .options(selectinload(AllocationNode.slot))
            .where(
                AllocationNode.order_id == active_order.id,
                AllocationNode.entity_id == bcc_id,
            )
        )
        bcc_nodes = list((await db.execute(node_query)).scalars().all())
        if bcc_nodes:
            # Match current time slot if available
            current_node = None
            for bn in bcc_nodes:
                if bn.slot and bn.slot.slot_start <= now <= bn.slot.slot_end:
                    current_node = bn
                    break
            # Fallback to first non-zero target slot, or first slot
            if not current_node:
                current_node = next((bn for bn in bcc_nodes if bn.target_mw > 0), bcc_nodes[0])

            target_mw = current_node.target_mw

            # Fetch planned feeders for this slot (or across all slots if none)
            fa_query = select(FeederAssignment).where(FeederAssignment.node_id == current_node.id)
            assignments = list((await db.execute(fa_query)).scalars().all())
            if not assignments:
                all_node_ids = [bn.id for bn in bcc_nodes]
                fa_query = select(FeederAssignment).where(FeederAssignment.node_id.in_(all_node_ids))
                assignments = list((await db.execute(fa_query)).scalars().all())

            planned_assignments = {a.feeder_id: a for a in assignments}
            planned_feeder_ids = set(planned_assignments.keys())

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
    db_changed = False
    for f in feeders:
        open_ev = open_events.get(f.id)
        if open_ev is None and f.status == FeederStatus.OPEN:
            # Self-healing: feeder was marked OPEN without an active ShedEvent
            f.status = FeederStatus.CLOSED
            if f.history and not f.history.last_shed_end:
                f.history.last_shed_end = now
            db_changed = True

        is_open = open_ev is not None

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

        assignment = planned_assignments.get(f.id)
        is_planned = assignment is not None or f.id in planned_feeder_ids
        cum_min = float(f.history.cumulative_minutes) if f.history else 0.0
        f_score = assignment.fairness_score if assignment else None

        rec_reason: Optional[str] = None
        if is_planned:
            rec_reason = (
                f"Départ sélectionné par l'algorithme d'optimisation STEG (Priorité {f.priority.value}, "
                f"Temps de coupure cumulé: {int(cum_min)} min"
                f"{f', Score d’équité: {f_score:.2f}' if f_score is not None else ''}, "
                f"Puissance nominale: {f.avg_mw} MW). Conforme aux temps de repos et sans infrastructure vitale."
            )

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
                is_planned_in_order=is_planned,
                cumulative_minutes=cum_min,
                fairness_score=f_score,
                recommendation_reason=rec_reason,
                current_event_id=open_ev.id if open_ev else None,
                open_time=open_ev.open_time if open_ev else None,
                elapsed_minutes=elapsed_mins,
                alarm_level=alarm_lvl,
            )
        )

    if db_changed:
        await db.commit()

    return BccExecutionDashboard(
        bcc_id=bcc.id,
        bcc_name=bcc.name,
        target_mw=round(target_mw, 1),
        actual_mw=round(actual_mw, 1),
        gap_mw=gap_mw,
        open_feeders_count=len(open_events),
        feeders=items,
        order_id=active_order.id if active_order else None,
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
        feeder.history.last_shed_end = None

    # Record in cryptographic audit trail
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="FEEDER_OPENED",
        entity_type="feeder",
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
    await ws_manager.broadcast({
        "type": "MONITORING_SUMMARY",
        "data": summary.model_dump(mode="json"),
    })

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
        entity_type="feeder",
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
    await ws_manager.broadcast({
        "type": "MONITORING_SUMMARY",
        "data": summary.model_dump(mode="json"),
    })

    return event


async def restore_feeder_by_id(
    db: AsyncSession, feeder_id: str, req: ConfirmCloseRequest, user: User
) -> dict:
    """
    Direct restoration by feeder ID.
    If an open ShedEvent exists, delegates to confirm_restoration.
    If no open event exists, heals feeder status to CLOSED and updates history.
    """
    open_ev = (await db.execute(
        select(ShedEvent)
        .where(ShedEvent.feeder_id == feeder_id, ShedEvent.status == EventStatus.OPEN)
        .order_by(ShedEvent.id.desc())
        .limit(1)
    )).scalar_one_or_none()

    if open_ev:
        ev = await confirm_restoration(db, event_id=open_ev.id, req=req, user=user)
        return {
            "status": "ok",
            "event_id": ev.id,
            "feeder_id": ev.feeder_id,
            "state": ev.status.value,
            "duration_min": ev.duration_min,
            "ens_mwh": ev.ens_mwh,
            "close_time": ev.close_time.isoformat() if ev.close_time else None,
        }

    feeder = (await db.execute(
        select(Feeder)
        .options(selectinload(Feeder.history))
        .where(Feeder.id == feeder_id)
        .with_for_update()
    )).scalar_one_or_none()

    if not feeder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Feeder '{feeder_id}' not found")

    if user.role == UserRole.BCC_OPERATOR and user.scope_id != feeder.bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Out of scope: cannot restore feeder belonging to {feeder.bcc_id}",
        )

    now = datetime.now(timezone.utc)
    close_time = req.close_time or now

    feeder.status = FeederStatus.CLOSED
    if feeder.history and not feeder.history.last_shed_end:
        feeder.history.last_shed_end = close_time

    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="FEEDER_RESTORED",
        entity_type="feeder",
        entity_id=feeder.id,
        payload={"feeder_id": feeder.id, "reconciled": True},
    )

    await db.commit()

    summary = await monitoring_service.get_monitoring_summary(db)
    await ws_manager.broadcast({
        "type": "MONITORING_SUMMARY",
        "data": summary.model_dump(mode="json"),
    })

    return {
        "status": "ok",
        "event_id": None,
        "feeder_id": feeder.id,
        "state": feeder.status.value,
        "duration_min": 0,
        "ens_mwh": 0.0,
        "close_time": close_time.isoformat(),
    }


async def execute_emergency_auto_shed(
    db: AsyncSession,
    req: EmergencyAutoShedRequest,
    user: User,
) -> EmergencyAutoShedResponse:
    """
    Emergency Automated Load Shedding:
    Triggered when grid frequency is endangered or real-time deficit is critical.
    With zero manual delay:
    1. Sets up the REAL_TIME deficit plan and slot for today with requested deficit MW.
    2. Runs full fair-share allocation across CRC Nord/Sud and all 7 BCCs (P5 -> P1, fairness scores, rest rules).
    3. Validates and activates the order immediately.
    4. Automatically opens breakers on all assigned feeders, cutting electricity instantaneously.
    5. Broadcasts live WebSocket alerts and returns the full operational summary.
    """
    deficit_mw = max(10.0, round(req.deficit_mw, 1))
    now = datetime.now(timezone.utc)
    plan_date = now.date()

    # 1. Find or create REAL_TIME plan
    plan_query = (
        select(DeficitPlan)
        .options(selectinload(DeficitPlan.slots), selectinload(DeficitPlan.order))
        .where(DeficitPlan.date == plan_date, DeficitPlan.mode == OrderType.REAL_TIME)
    )
    plan = (await db.execute(plan_query)).scalar_one_or_none()

    slot_start = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=30)

    if not plan:
        plan = DeficitPlan(
            date=plan_date,
            mode=OrderType.REAL_TIME,
            status=DeficitPlanStatus.VALIDATED,
            created_by=user.id,
            validated_by=user.id,
            validated_at=now,
            slots=[],
        )
        db.add(plan)
        await db.flush()

        slot = DeficitSlot(
            plan_id=plan.id,
            slot_start=slot_start,
            slot_end=slot_end,
            demand_mw=3950.0 + deficit_mw,
            generation_mw=3800.0,
            imports_mw=200.0,
            margin_mw=50.0,
            deficit_mw=deficit_mw,
        )
        db.add(slot)
        await db.flush()
    else:
        # Update existing plan slot
        if not plan.slots:
            slot = DeficitSlot(
                plan_id=plan.id,
                slot_start=slot_start,
                slot_end=slot_end,
                demand_mw=3950.0 + deficit_mw,
                generation_mw=3800.0,
                imports_mw=200.0,
                margin_mw=50.0,
                deficit_mw=deficit_mw,
            )
            db.add(slot)
        else:
            slot = plan.slots[0]
            slot.deficit_mw = deficit_mw
            slot.demand_mw = 3950.0 + deficit_mw
        plan.status = DeficitPlanStatus.VALIDATED
        await db.flush()

    # 2. Setup or reuse order
    if plan.order:
        order = plan.order
        # Clean previous allocation nodes
        await db.execute(delete(AllocationNode).where(AllocationNode.order_id == order.id))
        order.status = OrderStatus.DRAFT
        order.total_deficit_mw = deficit_mw
        order.allocated_at = None
        order.validated_at = None
        order.activated_at = None
        order.completed_at = None
        order.cancelled_at = None
        await db.flush()
    else:
        order = ShedOrder(
            plan_id=plan.id,
            status=OrderStatus.DRAFT,
            total_deficit_mw=deficit_mw,
            created_by=user.id,
        )
        db.add(order)
        await db.flush()

    # 3. Run algorithmic allocation, validate & activate
    allocated_order = await order_service.run_allocation(db, order_id=order.id, actor=user)
    validated_order = await order_service.validate_order(db, order_id=order.id, actor=user)
    active_order = await order_service.activate_order(db, order_id=order.id, actor=user)

    # 4. Automatically cut the electricity on terrain for all assigned feeders
    fa_stmt = (
        select(FeederAssignment, Feeder, Substation, Bcc)
        .join(Feeder, FeederAssignment.feeder_id == Feeder.id)
        .join(Substation, Feeder.substation_id == Substation.id)
        .join(Bcc, Feeder.bcc_id == Bcc.id)
        .join(AllocationNode, FeederAssignment.node_id == AllocationNode.id)
        .where(AllocationNode.order_id == active_order.id)
        .order_by(Feeder.priority.desc())
    )
    assigned_rows = (await db.execute(fa_stmt)).all()

    cut_feeders: List[EmergencyCutFeederInfo] = []
    total_mw_cut = 0.0

    for assignment, feeder, substation, bcc in assigned_rows:
        # P0 feeders are strictly protected
        if feeder.priority == PriorityLevel.P0 or feeder.critical:
            continue

        mw_to_cut = assignment.assigned_mw or feeder.avg_mw

        # If not already open, create open event and open breaker
        if feeder.status != FeederStatus.OPEN:
            event = ShedEvent(
                order_id=active_order.id,
                feeder_id=feeder.id,
                bcc_id=feeder.bcc_id,
                open_time=now,
                mw_before=feeder.avg_mw,
                mw_actual=mw_to_cut,
                operator_id=user.id,
                status=EventStatus.OPEN,
            )
            db.add(event)
            feeder.status = FeederStatus.OPEN
            await db.execute(
                update(FeederHistory)
                .where(FeederHistory.feeder_id == feeder.id)
                .values(last_shed_start=now, last_shed_end=None)
            )

        total_mw_cut += mw_to_cut
        cut_feeders.append(
            EmergencyCutFeederInfo(
                feeder_id=feeder.id,
                feeder_name=feeder.name,
                bcc_id=bcc.id,
                bcc_name=bcc.name,
                priority=feeder.priority.value,
                mw_cut=round(mw_to_cut, 1),
            )
        )

    # 5. Log in cryptographic audit log
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="EMERGENCY_AUTO_SHED_EXECUTED",
        entity_type="shed_order",
        entity_id=str(active_order.id),
        payload={
            "order_id": active_order.id,
            "target_deficit_mw": deficit_mw,
            "total_mw_cut": round(total_mw_cut, 1),
            "cut_feeders_count": len(cut_feeders),
            "reason": req.reason,
        },
    )

    await db.commit()

    # 6. Broadcast telemetry to all connected clients
    summary = await monitoring_service.get_monitoring_summary(db)
    await ws_manager.broadcast({
        "type": "MONITORING_SUMMARY",
        "data": summary.model_dump(mode="json"),
    })
    await ws_manager.broadcast({
        "type": "EMERGENCY_SHED_TRIGGERED",
        "order_id": active_order.id,
        "mw_cut": round(total_mw_cut, 1),
        "cut_feeders_count": len(cut_feeders),
    })

    return EmergencyAutoShedResponse(
        status="ok",
        order_id=active_order.id,
        plan_id=plan.id,
        total_deficit_mw=deficit_mw,
        total_mw_cut=round(total_mw_cut, 1),
        cut_feeders_count=len(cut_feeders),
        cut_feeders=cut_feeders,
        message=f"Délestage d'urgence exécuté : {len(cut_feeders)} départs coupés immédiatement ({round(total_mw_cut, 1)} MW soulagés). Réseau protégé du blackout.",
        executed_at=now.isoformat(),
    )

