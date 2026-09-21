"""
Real-time 1 Hz High-Cadence Grid Telemetry Engine.

Generates realistic stochastic micro-fluctuations (Ornstein-Uhlenbeck process)
for National Demand, International Imports, Deficit and Grid Frequency.
Maintains a 60-second in-memory ring buffer (zero database writes) and
broadcasts ticks via WebSocket every second.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
from collections import deque
from datetime import datetime, timezone
from typing import Deque, List, Optional
from pydantic import BaseModel

from app.core.websocket import ws_manager

logger = logging.getLogger(__name__)


class LiveTelemetryPoint(BaseModel):
    timestamp: str
    time_label: str
    demand_mw: float
    generation_mw: float
    imports_mw: float
    margin_mw: float
    deficit_mw: float
    frequency_hz: float
    delta_demand_mw: float


class LiveTelemetrySnapshot(BaseModel):
    current: LiveTelemetryPoint
    history: List[LiveTelemetryPoint]


class LiveGridTelemetryEngine:
    def __init__(self, max_history: int = 60):
        self.max_history = max_history
        self.history: Deque[LiveTelemetryPoint] = deque(maxlen=max_history)
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

        # Base nominal operating points (based on national grid scale)
        self.base_demand: float = 4350.0
        self.base_generation: float = 3800.0
        self.base_imports: float = 200.0
        self.base_margin: float = 50.0

        # Current state
        self.current_demand: float = 4350.0
        self.current_imports: float = 200.0
        self.current_generation: float = 3800.0
        self.current_margin: float = 50.0
        self.prev_demand: float = 4350.0

        # Pre-seed history with 60 realistic points so frontend has a full sparkline immediately
        self._seed_initial_history()

    def _seed_initial_history(self):
        now = datetime.now(timezone.utc)
        for i in range(self.max_history, 0, -1):
            t = datetime.fromtimestamp(now.timestamp() - i, tz=timezone.utc)
            pt = self._generate_step(t)
            self.history.append(pt)

    def _generate_step(self, timestamp: datetime) -> LiveTelemetryPoint:
        # Ornstein-Uhlenbeck mean-reverting stochastic process for demand
        # dD = theta * (mu - D) * dt + sigma * dW
        theta_d = 0.09
        sigma_d = 4.2
        drift_d = theta_d * (self.base_demand - self.current_demand)
        shock_d = random.gauss(0.0, sigma_d)
        new_demand = round(max(3500.0, min(5200.0, self.current_demand + drift_d + shock_d)), 1)
        delta_d = round(new_demand - self.current_demand, 1)
        self.prev_demand = self.current_demand
        self.current_demand = new_demand

        # Micro-fluctuations for international imports (interconnections)
        theta_i = 0.08
        sigma_i = 1.2
        drift_i = theta_i * (self.base_imports - self.current_imports)
        shock_i = random.gauss(0.0, sigma_i)
        new_imports = round(max(150.0, min(260.0, self.current_imports + drift_i + shock_i)), 1)
        self.current_imports = new_imports

        # Generation micro-variance
        gen_shock = random.gauss(0.0, 0.4)
        new_gen = round(self.base_generation + gen_shock, 1)
        self.current_generation = new_gen

        # Compute real-time deficit: max(0, Demand - Generation - Imports - Margin)
        deficit = round(max(0.0, self.current_demand - new_gen - new_imports - self.base_margin), 1)

        # Grid frequency: tightly regulated primary control.
        # Strict user constraint: frequency variations must NOT exceed ±0.010 Hz from 50.000 Hz.
        # Under power imbalance: delta_power = (Gen + Imports) - Demand
        delta_p = (new_gen + new_imports) - self.current_demand
        # Scale to max ~0.006 Hz imbalance effect
        f_imbalance = max(-0.006, min(0.006, (delta_p / 1000.0) * 0.015))
        f_jitter = random.uniform(-0.003, 0.003)
        frequency = round(50.000 + f_imbalance + f_jitter, 3)
        # Strict hard clamp: exactly [49.990 Hz, 50.010 Hz]
        frequency = max(49.990, min(50.010, frequency))

        time_label = timestamp.strftime("%H:%M:%S")

        return LiveTelemetryPoint(
            timestamp=timestamp.isoformat(),
            time_label=time_label,
            demand_mw=self.current_demand,
            generation_mw=self.current_generation,
            imports_mw=self.current_imports,
            margin_mw=self.base_margin,
            deficit_mw=deficit,
            frequency_hz=frequency,
            delta_demand_mw=delta_d,
        )

    def tick(self) -> LiveTelemetryPoint:
        now = datetime.now(timezone.utc)
        point = self._generate_step(now)
        self.history.append(point)
        return point

    def get_snapshot(self) -> LiveTelemetrySnapshot:
        current = self.history[-1] if self.history else self._generate_step(datetime.now(timezone.utc))
        return LiveTelemetrySnapshot(
            current=current,
            history=list(self.history),
        )

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("LiveGridTelemetryEngine started (1 Hz tick cadence).")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LiveGridTelemetryEngine stopped.")

    async def _run_loop(self):
        while self.is_running:
            try:
                point = self.tick()
                # Broadcast lightweight payload to all connected clients
                await ws_manager.broadcast({
                    "type": "LIVE_TELEMETRY_TICK",
                    "data": point.model_dump(mode="json"),
                })
            except Exception as e:
                logger.warning(f"Error in LiveGridTelemetryEngine tick: {e}")
            await asyncio.sleep(1.0)


# Global singleton engine instance
telemetry_engine = LiveGridTelemetryEngine(max_history=60)
