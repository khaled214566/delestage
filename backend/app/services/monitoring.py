from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import ShedEvent
from app.models.enums import EventStatus, AlarmLevel, OrderStatus, AllocationLevel
from app.models.hierarchy import Feeder, Bcc, Crc
from app.models.order import ShedOrder, AllocationNode
from app.models.parameters import Parameters
from app.schemas.monitoring import MonitoringSummary, RegionalSummary, ShedEventOut
from app.core.websocket import ws_manager


async def get_monitoring_summary(db: AsyncSession, order_id: Optional[int] = None) -> MonitoringSummary:
    now = datetime.now(timezone.utc)

    # 1. Determine target order (explicit or latest active/validated)
    target_order: Optional[ShedOrder] = None
    if order_id:
        target_order = await db.get(ShedOrder, order_id)
    else:
        order_query = (
            select(ShedOrder)
            .where(ShedOrder.status.in_([OrderStatus.ACTIVE, OrderStatus.VALIDATED, OrderStatus.ALLOCATED]))
            .order_by(ShedOrder.id.desc())
            .limit(1)
        )
        target_order = (await db.execute(order_query)).scalar_one_or_none()

    # Load parameters for thresholds
    params = await db.get(Parameters, 1)
    max_duration_min = params.max_duration_min if params else 45.0

    # 2. Query open events with relationships
    events_query = (
        select(ShedEvent)
        .options(selectinload(ShedEvent.feeder), selectinload(ShedEvent.bcc))
        .where(ShedEvent.status == EventStatus.OPEN)
        .order_by(ShedEvent.open_time.asc())
    )
    open_events = list((await db.execute(events_query)).scalars().all())

    # Build event output list and calculate metrics
    total_actual_mw = 0.0
    max_duration = 0.0
    amber_alarms = 0
    red_alarms = 0
    actual_by_bcc: Dict[str, float] = {}
    event_outs: List[ShedEventOut] = []

    for ev in open_events:
        duration = ev.compute_duration(now)
        alarm = ev.get_alarm_level(max_duration_min, now)
        total_actual_mw += ev.mw_actual
        if duration > max_duration:
            max_duration = duration

        if alarm == AlarmLevel.AMBER:
            amber_alarms += 1
        elif alarm == AlarmLevel.RED:
            red_alarms += 1

        actual_by_bcc[ev.bcc_id] = actual_by_bcc.get(ev.bcc_id, 0.0) + ev.mw_actual

        event_outs.append(
            ShedEventOut(
                id=ev.id,
                order_id=ev.order_id,
                feeder_id=ev.feeder_id,
                feeder_name=ev.feeder.name if ev.feeder else ev.feeder_id,
                bcc_id=ev.bcc_id,
                open_time=ev.open_time,
                close_time=ev.close_time,
                mw_actual=round(ev.mw_actual, 2),
                duration_min=duration,
                ens_mwh=round(ev.ens_mwh + (ev.mw_actual * duration / 60.0), 3),
                status=ev.status.value,
                alarm_level=alarm.value,
            )
        )

    # 3. Query total cumulative ENS across all events (including closed)
    ens_query = select(func.coalesce(func.sum(ShedEvent.ens_mwh), 0.0))
    total_historical_ens = float((await db.execute(ens_query)).scalar() or 0.0)
    current_running_ens = sum(ev.mw_actual * ev.compute_duration(now) / 60.0 for ev in open_events)
    total_ens_mwh = round(total_historical_ens + current_running_ens, 2)

    # 4. Target MW from active order
    target_mw = target_order.total_deficit_mw if target_order else 0.0
    gap_mw = round(target_mw - total_actual_mw, 2)

    # 5. Regional CRC and BCC breakdown
    crcs = list((await db.execute(select(Crc))).scalars().all())
    bccs = list((await db.execute(select(Bcc))).scalars().all())

    # Fetch allocation targets if order exists
    target_by_entity: Dict[str, float] = {}
    if target_order:
        nodes = list((await db.execute(
            select(AllocationNode).where(AllocationNode.order_id == target_order.id)
        )).scalars().all())
        for n in nodes:
            target_by_entity[n.entity_id] = n.target_mw

    bcc_summaries: List[RegionalSummary] = []
    actual_by_crc: Dict[str, float] = {}

    for b in bccs:
        act = actual_by_bcc.get(b.id, 0.0)
        tgt = target_by_entity.get(b.id, 0.0)
        actual_by_crc[b.crc_id] = actual_by_crc.get(b.crc_id, 0.0) + act
        bcc_summaries.append(
            RegionalSummary(
                entity_id=b.id,
                name=b.name,
                target_mw=round(tgt, 1),
                actual_mw=round(act, 1),
                gap_mw=round(tgt - act, 1),
                open_feeders=sum(1 for ev in open_events if ev.bcc_id == b.id),
            )
        )

    crc_summaries: List[RegionalSummary] = []
    for c in crcs:
        act = actual_by_crc.get(c.id, 0.0)
        tgt = target_by_entity.get(c.id, 0.0)
        crc_summaries.append(
            RegionalSummary(
                entity_id=c.id,
                name=c.name,
                target_mw=round(tgt, 1),
                actual_mw=round(act, 1),
                gap_mw=round(tgt - act, 1),
                open_feeders=sum(1 for ev in open_events if ev.bcc.crc_id == c.id),
            )
        )

    return MonitoringSummary(
        timestamp=now,
        order_id=target_order.id if target_order else None,
        target_mw=round(target_mw, 2),
        actual_mw=round(total_actual_mw, 2),
        gap_mw=gap_mw,
        open_feeders_count=len(open_events),
        active_bccs_count=len(actual_by_bcc),
        max_duration_min=round(max_duration, 1),
        total_ens_mwh=total_ens_mwh,
        amber_alarms_count=amber_alarms,
        red_alarms_count=red_alarms,
        crc_breakdown=crc_summaries,
        bcc_breakdown=bcc_summaries,
        active_events=event_outs,
    )


async def simulate_event_toggle(
    db: AsyncSession, feeder_id: str, open_state: bool, operator_id: Optional[int] = None
) -> ShedEvent:
    """Helper to simulate breaker opening / closing and broadcast the new telemetry."""
    now = datetime.now(timezone.utc)
    feeder = await db.get(Feeder, feeder_id)
    if not feeder:
        raise ValueError(f"Feeder '{feeder_id}' not found")

    existing_event = (await db.execute(
        select(ShedEvent)
        .where(ShedEvent.feeder_id == feeder_id, ShedEvent.status == EventStatus.OPEN)
    )).scalar_one_or_none()

    if open_state:
        if existing_event:
            return existing_event  # already open

        # Find or create an active order if none exists
        order_query = select(ShedOrder).order_by(ShedOrder.id.desc()).limit(1)
        order = (await db.execute(order_query)).scalar_one_or_none()
        if not order:
            from app.models.deficit import DeficitPlan
            from datetime import date
            from app.models.enums import DeficitPlanStatus, OrderType
            plan = (await db.execute(select(DeficitPlan).order_by(DeficitPlan.id.desc()).limit(1))).scalar_one_or_none()
            if not plan:
                plan = DeficitPlan(date=date.today(), mode=OrderType.REAL_TIME, status=DeficitPlanStatus.VALIDATED, created_by=1)
                db.add(plan)
                await db.flush()
            order = ShedOrder(
                plan_id=plan.id,
                status=OrderStatus.ACTIVE,
                total_deficit_mw=300.0,
                created_by=1,
            )
            db.add(order)
            await db.flush()
        order_id = order.id

        new_event = ShedEvent(
            order_id=order_id,
            feeder_id=feeder.id,
            bcc_id=feeder.bcc_id,
            open_time=now,
            mw_before=feeder.avg_mw,
            mw_actual=feeder.avg_mw,
            status=EventStatus.OPEN,
            operator_id=operator_id,
        )
        db.add(new_event)
        await db.commit()
        await db.refresh(new_event)
        target_ev = new_event
    else:
        if not existing_event:
            raise ValueError(f"Feeder '{feeder_id}' is not currently open")
        existing_event.close_time = now
        duration = (now - existing_event.open_time).total_seconds() / 60.0
        existing_event.duration_min = round(duration, 1)
        existing_event.ens_mwh = round(existing_event.mw_actual * duration / 60.0, 3)
        existing_event.status = EventStatus.CLOSED
        await db.commit()
        await db.refresh(existing_event)
        target_ev = existing_event

    # Broadcast updated telemetry to all live WebSocket dashboards
    summary = await get_monitoring_summary(db)
    await ws_manager.broadcast(summary.model_dump(mode="json"))
    return target_ev
