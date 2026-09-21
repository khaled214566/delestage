from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio
import logging

from app.core.database import get_db, AsyncSessionLocal
from app.core.websocket import ws_manager
from app.schemas.monitoring import MonitoringSummary
from app.services import monitoring as monitoring_service

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])
logger = logging.getLogger(__name__)


class SimulateToggleRequest(BaseModel):
    feeder_id: str
    open_state: bool


from app.services.live_telemetry import telemetry_engine, LiveTelemetrySnapshot


@router.get("/summary", response_model=MonitoringSummary)
async def get_summary(db: AsyncSession = Depends(get_db)):
    """Fetch current national and regional monitoring snapshot."""
    return await monitoring_service.get_monitoring_summary(db)


@router.get("/telemetry/live", response_model=LiveTelemetrySnapshot)
async def get_live_telemetry():
    """Fetch current high-frequency (1 Hz) stochastic grid telemetry point and rolling 60s history."""
    return telemetry_engine.get_snapshot()


@router.post("/simulate", response_model=dict)
async def simulate_toggle(body: SimulateToggleRequest, db: AsyncSession = Depends(get_db)):
    """Dev simulation endpoint to trigger feeder open/close and broadcast real-time telemetry."""
    try:
        ev = await monitoring_service.simulate_event_toggle(
            db, feeder_id=body.feeder_id, open_state=body.open_state
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"status": "ok", "event_id": ev.id, "feeder_id": ev.feeder_id, "state": ev.status.value}


@router.websocket("/ws")
async def websocket_monitoring(websocket: WebSocket):
    """
    Real-time telemetry WebSocket streaming endpoint.
    Sends initial snapshots, then keeps connection alive and receives incoming messages/pings.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial monitoring summary snapshot
        async with AsyncSessionLocal() as session:
            summary = await monitoring_service.get_monitoring_summary(session)
            await ws_manager.send_message(websocket, {
                "type": "MONITORING_SUMMARY",
                "data": summary.model_dump(mode="json"),
            })

        # Send initial live telemetry snapshot
        latest_pt = telemetry_engine.history[-1] if telemetry_engine.history else None
        if latest_pt:
            await ws_manager.send_message(websocket, {
                "type": "LIVE_TELEMETRY_TICK",
                "data": latest_pt.model_dump(mode="json"),
            })

        # Heartbeat loop: periodically refresh summary every 4s, safely using per-connection lock
        while True:
            await asyncio.sleep(4.0)
            async with AsyncSessionLocal() as session:
                summary = await monitoring_service.get_monitoring_summary(session)
                await ws_manager.send_message(websocket, {
                    "type": "MONITORING_SUMMARY",
                    "data": summary.model_dump(mode="json"),
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client error: {e}")
        ws_manager.disconnect(websocket)
