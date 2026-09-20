"""Feeder eligibility rules and priority weight mapping for the allocation engine."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from app.models.enums import PriorityLevel, FeederStatus

# Inverted priority weights: P5 (first to shed) has lowest weight,
# P1 (most protected) has highest weight.
# Lower fairness_score = shed first.
# fairness_score = cumulative_minutes / priority_weight
PRIORITY_WEIGHT: dict[PriorityLevel, int] = {
    PriorityLevel.P1: 5,
    PriorityLevel.P2: 4,
    PriorityLevel.P3: 3,
    PriorityLevel.P4: 2,
    PriorityLevel.P5: 1,
}

@dataclass(frozen=True)
class FeederCandidate:
    """A feeder eligible for shedding, with precomputed fairness score."""
    feeder_id: str
    name: str
    bcc_id: str
    avg_mw: float
    priority: PriorityLevel
    cumulative_minutes: float  # includes virtual minutes from prior slots in the plan
    priority_weight: int
    fairness_score: float  # cumulative_minutes / priority_weight
    zone_id: str

def compute_fairness_score(cumulative_minutes: float, priority: PriorityLevel) -> float:
    weight = PRIORITY_WEIGHT[priority]
    return cumulative_minutes / weight

def is_eligible(
    priority: PriorityLevel,
    critical: bool,
    status: FeederStatus,
    last_shed_end: datetime | None,
    slot_start: datetime,
    rest_time_minutes: int,
    assigned_feeder_ids: set[str],  # feeders already assigned in this slot (cross-BCC)
    feeder_id: str,
) -> bool:
    """Return True if a feeder can be selected for shedding in a given slot.
    
    Filters (hard constraints):
    1. P0 feeders are never shed
    2. Critical feeders are never shed
    3. Only CLOSED feeders (energized, not already open/maintenance/unavailable) can be shed
    4. Must have rested at least rest_time_minutes since last_shed_end
    5. Must not already be assigned to another BCC in this slot
    """
    if priority == PriorityLevel.P0:
        return False
    if critical:
        return False
    if status != FeederStatus.CLOSED:
        return False
    if feeder_id in assigned_feeder_ids:
        return False
    if last_shed_end is not None:
        rest_deadline = last_shed_end + timedelta(minutes=rest_time_minutes)
        if slot_start < rest_deadline:
            return False
    return True
