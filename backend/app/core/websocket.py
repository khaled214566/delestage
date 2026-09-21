import asyncio
import json
import logging
from typing import Any, Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket connection manager for real-time telemetry streaming.
    Thread-safe & asyncio-safe: uses per-connection asyncio.Lock to serialize sends
    and prevent concurrent send collisions that disconnect clients.
    """
    def __init__(self):
        self.active_connections: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = asyncio.Lock()
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def send_message(self, websocket: WebSocket, message: Any):
        """Safely send a JSON message to a specific connection using its lock."""
        lock = self.active_connections.get(websocket)
        if not lock:
            return
        payload = json.dumps(message) if not isinstance(message, str) else message
        try:
            async with lock:
                await websocket.send_text(payload)
        except Exception as e:
            logger.warning(f"Error sending message to websocket: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Any):
        """Safely broadcast JSON payload to all active subscribers without concurrent send collisions."""
        dead_connections = []
        payload = json.dumps(message) if not isinstance(message, str) else message
        # Copy items to iterate safely
        for ws, lock in list(self.active_connections.items()):
            try:
                async with lock:
                    await ws.send_text(payload)
            except Exception as e:
                logger.warning(f"Error broadcasting WebSocket message: {e}")
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ConnectionManager()
