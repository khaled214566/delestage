from dataclasses import dataclass
from typing import Optional, List, Dict

PRIORITY_WEIGHTS: Dict[str, int] = {
    "P5": 1,
    "P4": 2,
    "P3": 3,
    "P2": 4,
    "P1": 5,
}


@dataclass(frozen=True)
class PureRotationCandidate:
    id: str
    name: str
    substation_name: str
    priority: str
    avg_mw: float
    cumulative_minutes: int
    critical: bool
    status: str
    rest_time_left_min: float = 0.0


@dataclass(frozen=True)
class RotationReplacement:
    feeder_id: str
    feeder_name: str
    substation_name: str
    priority: str
    avg_mw: float
    delta_mw: float
    fairness_score: float
    cumulative_minutes: int
    rest_time_left_min: Optional[float]
    is_eligible: bool
    ineligibility_reason: Optional[str]


def rank_rotation_candidates(
    outgoing_mw: float,
    candidates: List[PureRotationCandidate],
    max_results: int = 5,
) -> List[RotationReplacement]:
    """
    Pure algorithmic function for UC6:
    Ranks replacement feeders to keep shed power constant while prioritizing fairness.

    Rules:
    1. Filter out P0, critical, and non-CLOSED feeders.
    2. Sort by:
       - Rest time satisfied first (rest_time_left_min == 0)
       - Minimum absolute difference to outgoing MW: |candidate.avg_mw - outgoing_mw|
       - Lowest fairness score: cumulative_minutes / weight
       - Deterministic ID
    """
    valid_candidates: List[PureRotationCandidate] = []
    for c in candidates:
        if c.priority == "P0" or c.critical:
            continue
        if c.status != "CLOSED":
            continue
        valid_candidates.append(c)

    def sort_key(c: PureRotationCandidate):
        has_rest_violation = 1 if c.rest_time_left_min > 0 else 0
        power_diff = round(abs(c.avg_mw - outgoing_mw), 2)
        weight = PRIORITY_WEIGHTS.get(c.priority, 1)
        fairness_score = c.cumulative_minutes / weight if weight > 0 else float("inf")
        return (has_rest_violation, power_diff, fairness_score, c.id)

    sorted_candidates = sorted(valid_candidates, key=sort_key)

    results: List[RotationReplacement] = []
    for c in sorted_candidates[:max_results]:
        weight = PRIORITY_WEIGHTS.get(c.priority, 1)
        score = round(c.cumulative_minutes / weight, 2)
        delta = round(c.avg_mw - outgoing_mw, 2)
        has_rest = c.rest_time_left_min > 0
        results.append(
            RotationReplacement(
                feeder_id=c.id,
                feeder_name=c.name,
                substation_name=c.substation_name,
                priority=c.priority,
                avg_mw=round(c.avg_mw, 2),
                delta_mw=delta,
                fairness_score=score,
                cumulative_minutes=c.cumulative_minutes,
                rest_time_left_min=round(c.rest_time_left_min, 1) if has_rest else None,
                is_eligible=not has_rest,
                ineligibility_reason=f"En repos ({round(c.rest_time_left_min, 1)} min restantes)" if has_rest else None,
            )
        )

    return results
