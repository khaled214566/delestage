from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.users import User
from app.schemas.execution import (
    ConfirmOpenRequest, ConfirmCloseRequest, BccExecutionDashboard,
    EmergencyAutoShedRequest, EmergencyAutoShedResponse,
)
from app.services import execution as execution_service

router = APIRouter(prefix="/api/execution", tags=["execution"])


@router.get("/bcc/{bcc_id}", response_model=BccExecutionDashboard)
async def get_bcc_dashboard(
    bcc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve operational dashboard for a BCC operator with live feeder statuses."""
    return await execution_service.get_bcc_dashboard(db, bcc_id=bcc_id, user=user)


@router.post("/open", response_model=dict, status_code=status.HTTP_201_CREATED)
async def confirm_opening(
    body: ConfirmOpenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """UC5: Confirm manual opening of a feeder breaker."""
    ev = await execution_service.confirm_opening(db, req=body, user=user)
    return {
        "status": "ok",
        "event_id": ev.id,
        "feeder_id": ev.feeder_id,
        "state": ev.status.value,
        "mw_actual": ev.mw_actual,
        "open_time": ev.open_time.isoformat(),
    }


@router.post("/events/{event_id}/close", response_model=dict)
async def confirm_restoration(
    event_id: int,
    body: ConfirmCloseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """UC7: Confirm re-energization / restoration of a feeder."""
    ev = await execution_service.confirm_restoration(db, event_id=event_id, req=body, user=user)
    return {
        "status": "ok",
        "event_id": ev.id,
        "feeder_id": ev.feeder_id,
        "state": ev.status.value,
        "duration_min": ev.duration_min,
        "ens_mwh": ev.ens_mwh,
        "close_time": ev.close_time.isoformat() if ev.close_time else None,
    }


@router.post("/feeders/{feeder_id}/restore", response_model=dict)
async def restore_feeder_by_id(
    feeder_id: str,
    body: ConfirmCloseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Directly restore a feeder by feeder ID."""
    return await execution_service.restore_feeder_by_id(db, feeder_id=feeder_id, req=body, user=user)



@router.post("/emergency-auto-shed", response_model=EmergencyAutoShedResponse)
async def emergency_auto_shed(
    body: EmergencyAutoShedRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Emergency Automated Load Shedding:
    Executes algorithmic fair-share allocation and instantaneous physical/virtual breaker cuts
    with zero human delay to protect national grid frequency from blackout.
    """
    return await execution_service.execute_emergency_auto_shed(db, req=body, user=user)
