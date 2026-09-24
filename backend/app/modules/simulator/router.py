"""
M11 — Demo Simulator router.

Endpoints (DISPATCHER or ADMIN only):
  POST /api/simulator/beat/1    → J-1 plan overview
  POST /api/simulator/beat/2    → Open 5 BCC1 feeders (+50 MW)
  POST /api/simulator/beat/3    → Backdate event to 37 min → AMBER alarm
  POST /api/simulator/beat/4    → Verify audit chain
  POST /api/simulator/reset     → Close all open events, restore feeders
  GET  /api/simulator/status    → Get current scenario state
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.users import User
from app.services import simulator as sim_svc

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


def _require_dispatcher_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.DISPATCHER, UserRole.ADMIN):
        raise HTTPException(403, "Dispatcher or Admin role required")
    return user


@router.post("/beat/1")
async def beat_1(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Beat 1: J-1 plan overview — informational."""
    return await sim_svc.run_beat1_j1_plan(db)


@router.post("/beat/2")
async def beat_2(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Beat 2: Simulate live deficit increase — open 5 BCC1 feeders."""
    try:
        return await sim_svc.run_beat2_live_increase(db)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/beat/3")
async def beat_3(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Beat 3: Trigger rotation alarm — backdate a BCC2 event to 37 min."""
    try:
        return await sim_svc.run_beat3_rotation(db)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/beat/4")
async def beat_4(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Beat 4: Verify SHA-256 audit chain integrity."""
    return await sim_svc.run_beat4_audit(db)


@router.post("/reset")
async def reset(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Reset: close all open events, restore feeders to CLOSED state."""
    return await sim_svc.reset_demo(db)


@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    _current: User = Depends(_require_dispatcher_or_admin),
):
    """Get current simulation state: open events count, last beat."""
    from sqlalchemy import select, func
    from app.models.event import ShedEvent
    from app.models.enums import EventStatus

    total_open = (await db.execute(
        select(func.count()).where(ShedEvent.status == EventStatus.OPEN)
    )).scalar_one()

    return {
        "open_events": total_open,
        "is_demo_running": total_open > 0,
        "message": (
            f"Démo en cours — {total_open} événements actifs"
            if total_open > 0
            else "Aucun délestage actif — prêt pour la démo"
        ),
    }


@router.post("/factory-reset")
async def factory_reset_sim(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(_require_dispatcher_or_admin),
):
    """Full factory reset: wipe all operational state and re-seed to day 1."""
    from app.services.admin import reset_database_to_factory
    return await reset_database_to_factory(
        db,
        actor_id=str(current.id),
        actor_name=current.name,
    )

