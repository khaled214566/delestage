"""
M12 — Evaluation, Benchmark & Metrics Router.

Endpoints:
  GET /api/evaluation/benchmark?days=7  → 7-day comparative simulation (Intelligent vs Naive vs Random)
  GET /api/evaluation/metrics           → Real-time equity and Gini index of the active grid
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.hierarchy import Feeder, FeederHistory
from app.models.event import ShedEvent
from app.models.enums import PriorityLevel
from app.engine.evaluation import run_benchmark_simulation, compute_gini_index

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/benchmark")
async def get_benchmark(
    days: Annotated[int, Query(ge=1, le=30)] = 7,
):
    """
    Run 7-day comparative benchmark simulation.
    Compares:
      1. Intelligent Engine (Platform)
      2. Naive Baseline (Static first-come)
      3. Random Baseline
    Returns Gini index, P0 violations, ENS, and advantage percentages.
    """
    results = run_benchmark_simulation(days=days)
    return {
        "days_simulated": days,
        "scenarios": [
            {
                "engine_name": r.engine_name,
                "description": r.description,
                "gini_index": r.gini_index,
                "p0_violations": r.p0_violations,
                "max_duration_min": r.max_duration_min,
                "target_achievement_pct": r.target_achievement_pct,
                "ens_mwh": r.ens_mwh,
                "avg_rotations_per_feeder": r.avg_rotations_per_feeder,
                "fairness_advantage_pct": r.fairness_advantage_pct,
            }
            for r in results
        ],
    }


@router.get("/metrics")
async def get_grid_fairness_metrics(
    db: AsyncSession = Depends(get_db),
):
    """
    Compute live grid fairness metrics across all 170 feeders.
    Calculates live Gini index of cumulative outage minutes,
    total ENS, total rotations, and priority distribution.
    """
    # Fetch all feeder histories
    stmt = (
        select(Feeder.id, Feeder.bcc_id, Feeder.priority, FeederHistory.cumulative_minutes, FeederHistory.rotations)
        .join(FeederHistory, Feeder.id == FeederHistory.feeder_id)
    )
    rows = (await db.execute(stmt)).all()

    minutes_list = [float(r.cumulative_minutes) for r in rows if r.priority != PriorityLevel.P0]
    live_gini = compute_gini_index(minutes_list)

    # Total historical ENS
    ens_query = select(func.coalesce(func.sum(ShedEvent.ens_mwh), 0.0))
    total_ens = float((await db.execute(ens_query)).scalar() or 0.0)

    # Rotations sum
    total_rotations = sum(r.rotations for r in rows)

    # Breakdown by BCC
    bcc_stats: dict[str, dict] = {}
    for r in rows:
        bcc = r.bcc_id
        if bcc not in bcc_stats:
            bcc_stats[bcc] = {"feeders": 0, "total_minutes": 0, "rotations": 0}
        bcc_stats[bcc]["feeders"] += 1
        bcc_stats[bcc]["total_minutes"] += r.cumulative_minutes
        bcc_stats[bcc]["rotations"] += r.rotations

    return {
        "total_feeders": len(rows),
        "live_gini_index": live_gini,
        "total_ens_mwh": round(total_ens, 2),
        "total_rotations": total_rotations,
        "p0_protected_count": sum(1 for r in rows if r.priority == PriorityLevel.P0),
        "bcc_breakdown": bcc_stats,
    }
