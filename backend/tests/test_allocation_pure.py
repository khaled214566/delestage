"""Pure tests for the allocation engine: no database needed.

Tests the CRC split, BCC largest-remainder, fairness scoring,
eligibility rules, and greedy feeder selection against the
documented specifications.
"""
import pytest
from datetime import datetime, UTC, timedelta

from app.engine.allocator import CrcShare, BccWeight, allocate_to_crcs, allocate_to_bccs
from app.engine.rules import (
    FeederCandidate, PRIORITY_WEIGHT, compute_fairness_score, is_eligible,
)
from app.engine.selector_greedy import select_feeders, SelectionResult
from app.models.enums import PriorityLevel, FeederStatus


# --- CRC allocation ---

def test_crc_split_300mw():
    shares = [CrcShare(crc_id=1, name="CRC_N", percentage=0.67), CrcShare(crc_id=2, name="CRC_S", percentage=0.33)]
    result = allocate_to_crcs(300, shares)
    assert result[1] == 201
    assert result[2] == 99
    assert sum(result.values()) == 300

def test_crc_split_350mw():
    shares = [CrcShare(crc_id=1, name="CRC_N", percentage=0.67), CrcShare(crc_id=2, name="CRC_S", percentage=0.33)]
    result = allocate_to_crcs(350, shares)
    assert sum(result.values()) == 350

def test_crc_split_zero():
    shares = [CrcShare(crc_id=1, name="CRC_N", percentage=0.67), CrcShare(crc_id=2, name="CRC_S", percentage=0.33)]
    result = allocate_to_crcs(0, shares)
    assert result[1] == 0
    assert result[2] == 0

@pytest.mark.parametrize("deficit", [100, 201, 350, 500])
def test_crc_split_sum_conservation(deficit):
    shares = [CrcShare(crc_id=1, name="CRC_N", percentage=0.67), CrcShare(crc_id=2, name="CRC_S", percentage=0.33)]
    result = allocate_to_crcs(deficit, shares)
    assert sum(result.values()) == deficit

# --- BCC allocation ---

def test_bcc_largest_remainder_basic():
    weights = [
        BccWeight(bcc_id=1, name="BCC1", total_managed_mw=420),
        BccWeight(bcc_id=2, name="BCC2", total_managed_mw=180),
        BccWeight(bcc_id=3, name="BCC3", total_managed_mw=250),
        BccWeight(bcc_id=4, name="BCC4", total_managed_mw=150),
    ]
    result = allocate_to_bccs(201, weights)
    assert sum(result.values()) == 201

@pytest.mark.parametrize("target", [10, 55, 123, 201, 1000])
def test_bcc_sum_conservation(target):
    weights = [
        BccWeight(bcc_id=1, name="BCC1", total_managed_mw=420),
        BccWeight(bcc_id=2, name="BCC2", total_managed_mw=180),
        BccWeight(bcc_id=3, name="BCC3", total_managed_mw=250),
        BccWeight(bcc_id=4, name="BCC4", total_managed_mw=150),
    ]
    result = allocate_to_bccs(target, weights)
    assert sum(result.values()) == round(target)

def test_bcc_zero_target():
    weights = [BccWeight(bcc_id=1, name="BCC1", total_managed_mw=420)]
    result = allocate_to_bccs(0, weights)
    assert result[1] == 0

def test_bcc_single_bcc():
    weights = [BccWeight(bcc_id=1, name="BCC1", total_managed_mw=420)]
    result = allocate_to_bccs(100, weights)
    assert result[1] == 100

def test_bcc_deterministic():
    weights = [
        BccWeight(bcc_id=1, name="BCC1", total_managed_mw=420),
        BccWeight(bcc_id=2, name="BCC2", total_managed_mw=180),
    ]
    result1 = allocate_to_bccs(100, weights)
    result2 = allocate_to_bccs(100, weights)
    assert result1 == result2

# --- Priority weights ---

def test_priority_weights_inverted():
    assert PRIORITY_WEIGHT[PriorityLevel.P5] < PRIORITY_WEIGHT[PriorityLevel.P4]
    assert PRIORITY_WEIGHT[PriorityLevel.P4] < PRIORITY_WEIGHT[PriorityLevel.P3]
    assert PRIORITY_WEIGHT[PriorityLevel.P3] < PRIORITY_WEIGHT[PriorityLevel.P2]
    assert PRIORITY_WEIGHT[PriorityLevel.P2] < PRIORITY_WEIGHT[PriorityLevel.P1]

def test_fairness_score_fresh_feeders():
    score_p5 = compute_fairness_score(0, PriorityLevel.P5)
    score_p1 = compute_fairness_score(0, PriorityLevel.P1)
    assert score_p5 == 0
    assert score_p1 == 0

def test_fairness_score_after_shedding():
    score_p5 = compute_fairness_score(30, PriorityLevel.P5)
    score_p3 = compute_fairness_score(30, PriorityLevel.P3)
    assert score_p3 < score_p5

# --- Eligibility rules ---

def test_p0_never_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P0, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=0, last_shed_end=None)
    assert not is_eligible(f, datetime.now(UTC), [], 180)

def test_critical_never_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=True, status=FeederStatus.CLOSED, cumulative_shed_minutes=0, last_shed_end=None)
    assert not is_eligible(f, datetime.now(UTC), [], 180)

def test_open_feeder_not_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.OPEN, cumulative_shed_minutes=0, last_shed_end=None)
    assert not is_eligible(f, datetime.now(UTC), [], 180)

def test_maintenance_not_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.MAINTENANCE, cumulative_shed_minutes=0, last_shed_end=None)
    assert not is_eligible(f, datetime.now(UTC), [], 180)

def test_closed_feeder_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=0, last_shed_end=None)
    assert is_eligible(f, datetime.now(UTC), [], 180)

def test_rest_time_enforced():
    now = datetime.now(UTC)
    last_end = now - timedelta(minutes=60)
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=30, last_shed_end=last_end)
    assert not is_eligible(f, now, [], 180)

def test_rest_time_met():
    now = datetime.now(UTC)
    last_end = now - timedelta(minutes=200)
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=30, last_shed_end=last_end)
    assert is_eligible(f, now, [], 180)

def test_already_assigned_not_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=0, last_shed_end=None)
    assert not is_eligible(f, datetime.now(UTC), [1], 180)

def test_no_history_eligible():
    f = FeederCandidate(id=1, name="F1", power_mw=10, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=0, last_shed_end=None)
    assert is_eligible(f, datetime.now(UTC), [], 180)

# --- Greedy selector ---

def _fc(id, power_mw, score=0):
    return FeederCandidate(id=id, name=f"F{id}", power_mw=power_mw, priority=PriorityLevel.P3, is_critical=False, status=FeederStatus.CLOSED, cumulative_shed_minutes=score, last_shed_end=None)

def test_greedy_meets_target():
    feeders = [_fc(1, 10), _fc(2, 15), _fc(3, 20), _fc(4, 25)]
    result = select_feeders(feeders, 50, tolerance_pct=0.1)
    assert sum(f.power_mw for f in result.selected) >= 50
    assert not result.is_partial

def test_greedy_overshoot_tolerance():
    feeders = [_fc(1, 54)]
    result = select_feeders(feeders, 50, tolerance_pct=0.1)
    assert len(result.selected) == 1
    assert result.selected[0].power_mw == 54
    assert not result.is_partial

def test_greedy_shortfall():
    feeders = [_fc(1, 60)]
    result = select_feeders(feeders, 100, tolerance_pct=0.1)
    assert len(result.selected) == 1
    assert result.is_partial
    assert result.shortfall_mw == 40

def test_greedy_zero_target():
    feeders = [_fc(1, 10)]
    result = select_feeders(feeders, 0, tolerance_pct=0.1)
    assert len(result.selected) == 0

def test_greedy_fairness_ordering():
    feeders = [_fc(1, 30, score=100), _fc(2, 30, score=10), _fc(3, 30, score=50)]
    result = select_feeders(feeders, 30, tolerance_pct=0.1)
    assert len(result.selected) == 1
    assert result.selected[0].id == 2

def test_greedy_deterministic():
    feeders = [_fc(1, 10), _fc(2, 20), _fc(3, 30)]
    res1 = select_feeders(feeders, 40, tolerance_pct=0.1)
    res2 = select_feeders(feeders, 40, tolerance_pct=0.1)
    assert [f.id for f in res1.selected] == [f.id for f in res2.selected]
