from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.users import User
from app.schemas.rotation import RotationProposal, ExecuteRotationRequest, ExecuteRotationResponse
from app.services import rotation as rotation_service

router = APIRouter(prefix="/api/rotation", tags=["rotation"])


@router.get("/proposals", response_model=List[RotationProposal])
async def get_rotation_proposals(
    bcc_id: Optional[str] = Query(None, description="Optional BCC filter"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    UC6: Retrieve feeders needing rotation (duration >= 80% / 36 min)
    along with recommended replacement candidates in the same BCC.
    """
    return await rotation_service.get_active_rotation_proposals(db, bcc_id=bcc_id, user=user)


@router.post("/execute", response_model=ExecuteRotationResponse)
async def execute_rotation(
    body: ExecuteRotationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    UC6: 1-Click Safe Sequence Rotation.
    Atomically opens the replacement feeder first, then restores the outgoing feeder.
    """
    return await rotation_service.execute_rotation(db, req=body, user=user)
