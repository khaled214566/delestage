"""M5: Greedy feeder selector.

Sorts eligible feeders by fairness_score (ascending), picks greedily until
the BCC's target MW is approximately met. Handles overshoot tolerance and
shortfall detection.
"""
from dataclasses import dataclass, field
from app.models.enums import PriorityLevel
from app.engine.rules import FeederCandidate

# Shedding order: P5 first (tier 1), P4 next (tier 2), down to P1 (tier 5)
PRIORITY_SHED_ORDER: dict[PriorityLevel | str, int] = {
    PriorityLevel.P5: 1,
    "P5": 1,
    PriorityLevel.P4: 2,
    "P4": 2,
    PriorityLevel.P3: 3,
    "P3": 3,
    PriorityLevel.P2: 4,
    "P2": 4,
    PriorityLevel.P1: 5,
    "P1": 5,
}


def _priority_rank(priority: PriorityLevel | str) -> int:
    return PRIORITY_SHED_ORDER.get(priority, 99)


def _feeder_sort_key(f: FeederCandidate) -> tuple:
    """Sort key for feeder selection with rest compliance and priority tiering:
    1. Fully rested feeders (rest_time_left_min <= 0) always precede feeders in rest window.
    2. Among rested feeders: priority tier (P5 -> P1), then lowest fairness score, then id.
    3. Among resting feeders (fallback): longest rested first (smallest rest_time_left_min),
       then priority tier, then lowest fairness score, then id.
    """
    if f.rest_time_left_min <= 0:
        return (0, 0.0, _priority_rank(f.priority), f.fairness_score, f.feeder_id)
    else:
        return (1, f.rest_time_left_min, _priority_rank(f.priority), f.fairness_score, f.feeder_id)


@dataclass
class SelectionResult:
    """Result of the greedy feeder selection for one BCC in one slot."""
    selected: list[FeederCandidate] = field(default_factory=list)
    target_mw: float = 0.0
    achieved_mw: float = 0.0
    shortfall_mw: float = 0.0
    is_partial: bool = False


def select_feeders(
    target_mw: float,
    eligible: list[FeederCandidate],
    max_overshoot_pct: float = 0.10,
) -> SelectionResult:
    """Greedy feeder selection for a single BCC target.
    
    Algorithm:
    1. Sort eligible feeders:
       - Fully rested feeders (rest_time_left_min <= 0) first,
         sorted by priority tier (P5 -> P1), then fairness_score ascending
       - Resting feeders second, sorted by least remaining rest time (rested longest)
       - feeder_id for determinism
    2. Pick feeders one by one until target is met or exceeded within tolerance
    3. When adding a feeder would overshoot beyond tolerance, check if
       adding it brings us closer to the target than not adding it
    4. Report shortfall if target cannot be met
    
    Args:
        target_mw: The MW target for this BCC in this slot
        eligible: List of FeederCandidate objects, pre-filtered for eligibility
        max_overshoot_pct: Maximum acceptable overshoot as fraction (0.10 = 10%)
    
    Returns:
        SelectionResult with selected feeders, achieved MW, and shortfall info
    """
    if target_mw <= 0:
        return SelectionResult(target_mw=target_mw)
    
    sorted_feeders = sorted(eligible, key=_feeder_sort_key)
    
    selected: list[FeederCandidate] = []
    achieved = 0.0
    max_allowed = target_mw * (1 + max_overshoot_pct)
    
    for feeder in sorted_feeders:
        if achieved >= target_mw:
            break
        
        new_total = achieved + feeder.avg_mw
        
        if new_total <= max_allowed:
            # Within tolerance, always add
            selected.append(feeder)
            achieved = new_total
        else:
            # Would exceed tolerance — add if it brings us closer to target
            undershoot = target_mw - achieved
            overshoot = new_total - target_mw
            if overshoot <= undershoot:
                selected.append(feeder)
                achieved = new_total
            # else: skip this feeder, try smaller ones
            # But since we're sorted by fairness (not size), we continue
            # looking for smaller feeders that might fit
            continue
    
    shortfall = max(0.0, target_mw - achieved)
    
    return SelectionResult(
        selected=selected,
        target_mw=target_mw,
        achieved_mw=round(achieved, 2),
        shortfall_mw=round(shortfall, 2),
        is_partial=shortfall > 0,
    )
