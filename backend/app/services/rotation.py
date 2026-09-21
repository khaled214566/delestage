from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.event import ShedEvent
from app.models.enums import EventStatus, AlarmLevel, PriorityLevel, FeederStatus, UserRole
from app.models.hierarchy import Feeder, Bcc, Substation, FeederHistory
from app.models.parameters import Parameters
from app.models.users import User
from app.schemas.rotation import (
    ReplacementCandidate,
    RotationProposal,
    ExecuteRotationRequest,
    ExecuteRotationResponse,
)
from app.services import audit
from app.services import monitoring as monitoring_service
from app.core.websocket import ws_manager

from app.engine.rotation import PureRotationCandidate, rank_rotation_candidates


async def get_active_rotation_proposals(
    db: AsyncSession,
    bcc_id: Optional[str] = None,
    user: Optional[User] = None,
) -> List[RotationProposal]:
    """
    Scans currently OPEN events nearing or exceeding duration limits (warning at 80% = 36 min).
    Generates replacement proposals for each flagged feeder.
    """
    now = datetime.now(timezone.utc)

    # Fetch global parameters
    params = await db.get(Parameters, 1)
    max_duration_min = float(params.max_duration_min) if params else 45.0
    warn_pct = float(params.rotation_warn_pct) if params else 80.0
    rest_time_min = float(params.rest_time_min) if params else 180.0

    # Scope enforcement
    effective_bcc_id = bcc_id
    if user and user.role == UserRole.BCC_OPERATOR:
        effective_bcc_id = user.scope_id

    # Query currently OPEN events
    ev_query = (
        select(ShedEvent)
        .options(
            selectinload(ShedEvent.feeder).selectinload(Feeder.substation),
            selectinload(ShedEvent.bcc),
        )
        .where(ShedEvent.status == EventStatus.OPEN)
    )
    if effective_bcc_id:
        ev_query = ev_query.where(ShedEvent.bcc_id == effective_bcc_id)

    open_events = list((await db.execute(ev_query)).scalars().all())

    proposals: List[RotationProposal] = []

    for ev in open_events:
        elapsed = ev.compute_duration(now)
        ratio = elapsed / max_duration_min

        # Flag if at or above warning threshold (e.g. 80% = 36 min)
        if ratio >= (warn_pct / 100.0):
            alarm_level = "RED" if ratio >= 1.0 else "AMBER"

            # Query candidate feeders in the same BCC
            candidates_query = (
                select(Feeder)
                .options(selectinload(Feeder.substation), selectinload(Feeder.history))
                .where(
                    Feeder.bcc_id == ev.bcc_id,
                    Feeder.id != ev.feeder_id,
                    Feeder.priority != PriorityLevel.P0,
                    Feeder.critical == False,  # noqa: E712
                    Feeder.status == FeederStatus.CLOSED,
                )
            )
            bcc_feeders = list((await db.execute(candidates_query)).scalars().all())

            # Convert to PureRotationCandidate
            pure_candidates: List[PureRotationCandidate] = []
            for f in bcc_feeders:
                rest_left = 0.0
                if f.history and f.history.last_shed_end:
                    elapsed_rest = (now - f.history.last_shed_end).total_seconds() / 60.0
                    if elapsed_rest < rest_time_min:
                        rest_left = rest_time_min - elapsed_rest

                cum_mins = f.history.cumulative_minutes if f.history else 0
                pure_candidates.append(
                    PureRotationCandidate(
                        id=f.id,
                        name=f.name,
                        substation_name=f.substation.name if f.substation else "",
                        priority=f.priority.value,
                        avg_mw=f.avg_mw,
                        cumulative_minutes=cum_mins,
                        critical=f.critical,
                        status=f.status.value,
                        rest_time_left_min=rest_left,
                    )
                )

            ranked = rank_rotation_candidates(ev.mw_actual, pure_candidates, max_results=5)
            rec = ranked[0] if ranked else None
            alts = ranked[1:] if len(ranked) > 1 else []

            proposals.append(
                RotationProposal(
                    outgoing_event_id=ev.id,
                    outgoing_feeder_id=ev.feeder_id,
                    outgoing_feeder_name=ev.feeder.name if ev.feeder else ev.feeder_id,
                    substation_name=ev.feeder.substation.name if (ev.feeder and ev.feeder.substation) else "",
                    bcc_id=ev.bcc_id,
                    bcc_name=ev.bcc.name if ev.bcc else ev.bcc_id,
                    open_time=ev.open_time,
                    elapsed_minutes=elapsed,
                    max_duration_minutes=max_duration_min,
                    elapsed_ratio=round(ratio, 2),
                    alarm_level=alarm_level,
                    outgoing_mw=ev.mw_actual,
                    recommended_replacement=rec,
                    alternatives=alts,
                )
            )

    return proposals


async def execute_rotation(
    db: AsyncSession,
    req: ExecuteRotationRequest,
    user: User,
) -> ExecuteRotationResponse:
    """
    UC6: Safe Sequence Feeder Rotation.
    1. Lock outgoing event, outgoing feeder, and replacement feeder with SELECT FOR UPDATE.
    2. Step 1: Open replacement feeder first (new ShedEvent OPEN).
    3. Step 2: Restore outgoing feeder second (close ShedEvent, compute ENS and duration).
    4. Increment outgoing feeder's rotations counter.
    5. Record in cryptographic audit log with action 'FEEDER_ROTATED'.
    6. Commit atomic transaction and broadcast telemetry.
    """
    now = datetime.now(timezone.utc)

    # 1. Lock outgoing event
    ev_query = (
        select(ShedEvent)
        .where(ShedEvent.id == req.outgoing_event_id)
        .with_for_update()
    )
    outgoing_ev = (await db.execute(ev_query)).scalar_one_or_none()
    if not outgoing_ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shed event #{req.outgoing_event_id} not found",
        )

    if outgoing_ev.status != EventStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Shed event #{req.outgoing_event_id} is already closed",
        )

    # 2. Lock outgoing feeder
    out_f_query = (
        select(Feeder)
        .options(selectinload(Feeder.history))
        .where(Feeder.id == outgoing_ev.feeder_id)
        .with_for_update()
    )
    outgoing_feeder = (await db.execute(out_f_query)).scalar_one_or_none()
    if not outgoing_feeder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outgoing feeder '{outgoing_ev.feeder_id}' not found",
        )

    # 3. Lock replacement feeder
    in_f_query = (
        select(Feeder)
        .options(selectinload(Feeder.history))
        .where(Feeder.id == req.replacement_feeder_id)
        .with_for_update()
    )
    replacement_feeder = (await db.execute(in_f_query)).scalar_one_or_none()
    if not replacement_feeder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replacement feeder '{req.replacement_feeder_id}' not found",
        )

    # Scope verification
    if user.role == UserRole.BCC_OPERATOR and user.scope_id != outgoing_feeder.bcc_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: cannot operate feeders outside scope '{user.scope_id}'",
        )

    # Replacement feeder sanity checks
    if replacement_feeder.priority == PriorityLevel.P0 or replacement_feeder.critical:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot rotate to a P0 or critical infrastructure feeder",
        )

    if replacement_feeder.status == FeederStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Replacement feeder '{replacement_feeder.id}' is already OPEN",
        )

    # Check rest time for replacement
    params = await db.get(Parameters, 1)
    rest_time_min = params.rest_time_min if params else 180
    if replacement_feeder.history and replacement_feeder.history.last_shed_end:
        elapsed_rest = (now - replacement_feeder.history.last_shed_end).total_seconds() / 60.0
        if elapsed_rest < rest_time_min and not req.justification:
            rest_left = round(rest_time_min - elapsed_rest)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Replacement feeder is resting ({rest_left} min left). Written justification required.",
            )

    replacement_mw = req.replacement_mw or replacement_feeder.avg_mw

    # 4. SAFE SEQUENCE STEP 1: Open replacement feeder FIRST
    new_open_ev = ShedEvent(
        order_id=outgoing_ev.order_id,
        feeder_id=replacement_feeder.id,
        bcc_id=replacement_feeder.bcc_id,
        open_time=now,
        mw_before=replacement_feeder.avg_mw,
        mw_actual=replacement_mw,
        operator_id=user.id,
        status=EventStatus.OPEN,
    )
    db.add(new_open_ev)
    replacement_feeder.status = FeederStatus.OPEN
    if replacement_feeder.history:
        replacement_feeder.history.last_shed_start = now

    # 5. SAFE SEQUENCE STEP 2: Restore outgoing feeder SECOND
    duration_min = round((now - outgoing_ev.open_time).total_seconds() / 60.0, 1)
    ens_mwh = round(outgoing_ev.mw_actual * duration_min / 60.0, 3)

    outgoing_ev.close_time = now
    outgoing_ev.duration_min = duration_min
    outgoing_ev.ens_mwh = ens_mwh
    outgoing_ev.status = EventStatus.CLOSED

    outgoing_feeder.status = FeederStatus.CLOSED
    if outgoing_feeder.history:
        outgoing_feeder.history.cumulative_minutes += int(round(duration_min))
        outgoing_feeder.history.rotations += 1
        outgoing_feeder.history.last_shed_end = now

    delta_mw = round(replacement_mw - outgoing_ev.mw_actual, 2)
    rotations_total = outgoing_feeder.history.rotations if outgoing_feeder.history else 1

    # 6. Audit logging (single append-only log entry)
    await audit.log(
        db,
        actor_id=str(user.id),
        actor_name=user.name,
        action="FEEDER_ROTATED",
        entity_type="feeder",
        entity_id=outgoing_feeder.id,
        payload={
            "outgoing_feeder_id": outgoing_feeder.id,
            "outgoing_event_id": outgoing_ev.id,
            "replacement_feeder_id": replacement_feeder.id,
            "outgoing_mw": outgoing_ev.mw_actual,
            "replacement_mw": replacement_mw,
            "delta_mw": delta_mw,
            "duration_min": duration_min,
            "ens_mwh": ens_mwh,
            "rotations_count": rotations_total,
            "justification": req.justification,
        },
    )

    await db.commit()
    await db.refresh(new_open_ev)

    # 7. Broadcast updated telemetry
    summary = await monitoring_service.get_monitoring_summary(db)
    await ws_manager.broadcast(summary.model_dump(mode="json"))

    return ExecuteRotationResponse(
        status="SUCCESS",
        outgoing_feeder_id=outgoing_feeder.id,
        replacement_feeder_id=replacement_feeder.id,
        opened_event_id=new_open_ev.id,
        restored_event_id=outgoing_ev.id,
        outgoing_mw=outgoing_ev.mw_actual,
        replacement_mw=replacement_mw,
        delta_mw=delta_mw,
        ens_mwh=ens_mwh,
        duration_min=duration_min,
        rotations_count=rotations_total,
        message=f"Rotation executed: {outgoing_feeder.id} restored ({duration_min} min, {ens_mwh} MWh), {replacement_feeder.id} opened ({replacement_mw} MW).",
    )
