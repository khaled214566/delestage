"""
M10 — Public citizen router (no authentication required).

Rate-limited to protect operator API from public traffic.
Endpoints:
  GET /api/public/status          → current shedding view (all zones)
  GET /api/public/zone/{zone_id}  → single zone details
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.citizen import get_citizen_view

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/status")
async def citizen_status(db: AsyncSession = Depends(get_db)):
    """
    Public endpoint — no authentication required.
    Returns the current shedding status for all zones.
    Safe to cache (30-second TTL recommended).
    """
    return await get_citizen_view(db)


@router.get("/zone/{zone_id}")
async def citizen_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    """
    Single-zone view — no authentication required.
    Returns status and events for one BCC zone.
    """
    data = await get_citizen_view(db)
    zones = {z["zone_id"]: z for z in data["zones"]}
    if zone_id.upper() not in zones:
        raise HTTPException(404, f"Zone '{zone_id}' not found")
    zone = zones[zone_id.upper()]
    return {
        "generated_at": data["generated_at"],
        "zone": zone,
    }
