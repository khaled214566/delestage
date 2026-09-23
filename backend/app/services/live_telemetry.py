"""
Real-time 1 Hz High-Cadence Grid Telemetry Engine.

Generates realistic stochastic micro-fluctuations (Ornstein-Uhlenbeck process)
for National Demand, International Imports, Deficit and Grid Frequency.
Maintains a 60-second in-memory ring buffer (zero database writes) and
broadcasts ticks via WebSocket every second.

Supports multi-scenario dynamic range:
- Deficit peaks up to ~800 MW (Pic de charge / Tension forte)
- Intermediate levels (~200 - 400 MW)
- Down to 0.0 MW (Équilibre nominal avec réserves)
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
from app.core.database import AsyncSessionLocal
from app.services.rotation import check_and_execute_auto_rotations

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
    scenario: str


class LiveTelemetrySnapshot(BaseModel):
    current: LiveTelemetryPoint
    history: List[LiveTelemetryPoint]
    scenario_mode: str


class LiveGridTelemetryEngine:
    def __init__(self, max_history: int = 60):
        self.max_history = max_history
        self.history: Deque[LiveTelemetryPoint] = deque(maxlen=max_history)
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._tick_counter: int = 0

        # Scenario mode: "AUTO" (cycles 0 -> 800 MW), "PEAK" (~800 MW), "BALANCED" (0 MW), "MODERATE" (~300 MW)
        self.scenario_mode: str = "AUTO"

        # Nominal operating points
        self.base_demand: float = 4350.0
        self.base_generation: float = 3800.0
        self.base_imports: float = 200.0
        self.base_margin: float = 50.0

        # Live state
        self.current_demand: float = 4350.0
        self.current_imports: float = 200.0
        self.current_generation: float = 3800.0
        self.prev_demand: float = 4350.0

        # Pre-seed history with 60 realistic points so frontend has a full sparkline immediately
        self._seed_initial_history()

    def set_scenario(self, mode: str):
        valid = {"AUTO", "PEAK", "BALANCED", "MODERATE"}
        if mode.upper() in valid:
            self.scenario_mode = mode.upper()
            logger.info(f"LiveGridTelemetry scenario changed to: {self.scenario_mode}")

    def _seed_initial_history(self):
        now = datetime.now(timezone.utc)
        for i in range(self.max_history, 0, -1):
            t = datetime.fromtimestamp(now.timestamp() - i, tz=timezone.utc)
            pt = self._generate_step(t)
            self.history.append(pt)

    def _generate_step(self, timestamp: datetime) -> LiveTelemetryPoint:
        t = timestamp.timestamp()

        # Determine target operating points based on scenario
        if self.scenario_mode == "PEAK":
            target_demand = 4820.0
            target_gen = 3740.0
            target_imports = 190.0
            scenario_name = "Pic Critique (~800 MW)"
        elif self.scenario_mode == "BALANCED":
            target_demand = 3940.0
            target_gen = 3850.0
            target_imports = 215.0
            scenario_name = "Équilibre (0 MW)"
        elif self.scenario_mode == "MODERATE":
            target_demand = 4400.0
            target_gen = 3800.0
            target_imports = 200.0
            scenario_name = "Déficit Temps Réel (~350 MW)"
        else:
            # AUTO mode: Smooth sinusoidal wave over 180s cycle (peaks ~800 MW, troughs at 0 MW)
            angle = (2 * math.pi * (t % 180.0)) / 180.0
            target_demand = 4370.0 + 460.0 * math.sin(angle)
            target_gen = 3800.0 - 50.0 * math.cos(angle)
            target_imports = 200.0 - 15.0 * math.sin(angle)

            # Descriptive scenario label based on current wave position
            raw_est = target_demand - target_gen - target_imports - self.base_margin
            if raw_est <= 20.0:
                scenario_name = "Cycle Auto : Équilibre (0 MW)"
            elif raw_est >= 600.0:
                scenario_name = "Cycle Auto : Pic Fort (700-800 MW)"
            else:
                scenario_name = f"Cycle Auto : Modéré ({int(round(raw_est))} MW)"

        # Ornstein-Uhlenbeck mean-reverting stochastic process for demand
        theta_d = 0.14
        sigma_d = 4.0
        drift_d = theta_d * (target_demand - self.current_demand)
        shock_d = random.gauss(0.0, sigma_d)
        new_demand = round(max(3500.0, min(5300.0, self.current_demand + drift_d + shock_d)), 1)
        delta_d = round(new_demand - self.current_demand, 1)
        self.prev_demand = self.current_demand
        self.current_demand = new_demand

        # Generation micro-variance
        theta_g = 0.12
        gen_shock = random.gauss(0.0, 0.6)
        drift_g = theta_g * (target_gen - self.current_generation)
        new_gen = round(max(3400.0, min(4200.0, self.current_generation + drift_g + gen_shock)), 1)
        self.current_generation = new_gen

        # International imports micro-fluctuations
        theta_i = 0.10
        sigma_i = 1.0
        drift_i = theta_i * (target_imports - self.current_imports)
        shock_i = random.gauss(0.0, sigma_i)
        new_imports = round(max(150.0, min(280.0, self.current_imports + drift_i + shock_i)), 1)
        self.current_imports = new_imports

        # Real-time deficit: max(0, Demand - Generation - Imports - Margin)
        deficit = round(max(0.0, self.current_demand - new_gen - new_imports - self.base_margin), 1)

        # Primary frequency regulation: tightly bounded within ±0.010 Hz around 50.000 Hz
        # delta_p = (Gen + Imports) - Demand
        delta_p = (new_gen + new_imports) - self.current_demand
        # Imbalance effect clamped to [-0.007, +0.007]
        f_imbalance = max(-0.007, min(0.007, (delta_p / 1000.0) * 0.012))
        f_jitter = random.uniform(-0.002, 0.002)
        frequency = round(50.000 + f_imbalance + f_jitter, 3)
        # Strict user constraint: strictly [49.990 Hz, 50.010 Hz]
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
            scenario=scenario_name,
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
            scenario_mode=self.scenario_mode,
        )

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("LiveGridTelemetryEngine started (1 Hz tick cadence, 0-800 MW dynamic range).")

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

            # Check for automatic rotations every 5 seconds (5 ticks)
            self._tick_counter += 1
            if self._tick_counter % 5 == 0:
                try:
                    async with AsyncSessionLocal() as session:
                        await check_and_execute_auto_rotations(session)
                except Exception as ex:
                    logger.debug(f"Auto-rotation background check error: {ex}")

            await asyncio.sleep(1.0)



# Global singleton engine instance
telemetry_engine = LiveGridTelemetryEngine(max_history=60)
