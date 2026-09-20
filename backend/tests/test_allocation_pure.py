"""Pure tests for the allocation engine: no database needed.

Tests the CRC split, BCC largest-remainder, fairness scoring,
eligibility rules, and greedy feeder selection against the
documented specifications.
"""
from datetime import datetime, UTC, timedelta
import pytest

from app.engine.allocator import CrcShare, BccWeight, allocate_to_crcs, allocate_to_bccs
from app.engine.rules import (
    FeederCandidate, PRIORITY_WEIGHT, compute_fairness_score, is_eligible,
)
from app.engine.selector_greedy import select_feeders, SelectionResult
from app.models.enums import PriorityLevel, FeederStatus


# --- CRC allocation ---

def test_crc_split_300mw():
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(300, shares)
    assert result["CRC_N"] == 201.0
    assert result["CRC_S"] == 99.0
    assert sum(result.values()) == 300.0


def test_crc_split_350mw():
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(350, shares)
    assert round(sum(result.values()), 2) == 350.0


def test_crc_split_zero():
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(0, shares)
    assert result["CRC_N"] == 0.0
    assert result["CRC_S"] == 0.0


@pytest.mark.parametrize("deficit", [100.0, 201.0, 350.0, 500.0])
def test_crc_split_sum_conservation(deficit):
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(deficit, shares)
    assert round(sum(result.values()), 2) == deficit


# --- BCC allocation (largest remainder) ---

def test_bcc_largest_remainder_basic():
    weights = [
        BccWeight(bcc_id="BCC1", managed_load_mw=420.0),
        BccWeight(bcc_id="BCC2", managed_load_mw=180.0),
        BccWeight(bcc_id="BCC3", managed_load_mw=250.0),
        BccWeight(bcc_id="BCC4", managed_load_mw=150.0),
    ]
    result = allocate_to_bccs(201, weights)
    assert sum(result.values()) == 201


@pytest.mark.parametrize("target", [10, 55, 123, 201, 1000])
def test_bcc_sum_conservation(target):
    weights = [
        BccWeight(bcc_id="BCC1", managed_load_mw=420.0),
        BccWeight(bcc_id="BCC2", managed_load_mw=180.0),
        BccWeight(bcc_id="BCC3", managed_load_mw=250.0),
        BccWeight(bcc_id="BCC4", managed_load_mw=150.0),
    ]
    result = allocate_to_bccs(target, weights)
    assert sum(result.values()) == round(target)


def test_bcc_zero_target():
    weights = [BccWeight(bcc_id="BCC1", managed_load_mw=420.0)]
    result = allocate_to_bccs(0, weights)
    assert result["BCC1"] == 0


def test_bcc_single_bcc():
    weights = [BccWeight(bcc_id="BCC1", managed_load_mw=420.0)]
    result = allocate_to_bccs(100, weights)
    assert result["BCC1"] == 100


def test_bcc_deterministic():
    weights = [
        BccWeight(bcc_id="BCC1", managed_load_mw=420.0),
        BccWeight(bcc_id="BCC2", managed_load_mw=180.0),
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
    assert score_p5 == 0.0
    assert score_p1 == 0.0


def test_fairness_score_after_shedding():
    # P5 weight is 1 -> score = 30 / 1 = 30
    # P3 weight is 3 -> score = 30 / 3 = 10
    score_p5 = compute_fairness_score(30, PriorityLevel.P5)
    score_p3 = compute_fairness_score(30, PriorityLevel.P3)
    assert score_p3 < score_p5


# --- Eligibility rules ---

def test_p0_never_eligible():
    now = datetime.now(UTC)
    assert not is_eligible(
        priority=PriorityLevel.P0,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_critical_never_eligible():
    now = datetime.now(UTC)
    assert not is_eligible(
        priority=PriorityLevel.P3,
        critical=True,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_open_feeder_not_eligible():
    now = datetime.now(UTC)
    assert not is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.OPEN,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_maintenance_not_eligible():
    now = datetime.now(UTC)
    assert not is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.MAINTENANCE,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_closed_feeder_eligible():
    now = datetime.now(UTC)
    assert is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_rest_time_enforced():
    now = datetime.now(UTC)
    last_end = now - timedelta(minutes=60)
    assert not is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=last_end,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_rest_time_met():
    now = datetime.now(UTC)
    last_end = now - timedelta(minutes=200)
    assert is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=last_end,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


def test_already_assigned_not_eligible():
    now = datetime.now(UTC)
    assert not is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids={"F1"},
        feeder_id="F1",
    )


def test_no_history_eligible():
    now = datetime.now(UTC)
    assert is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F1",
    )


# --- Greedy selector ---

def _fc(feeder_id: str, avg_mw: float, score: float = 0.0) -> FeederCandidate:
    return FeederCandidate(
        feeder_id=feeder_id,
        name=f"Feeder {feeder_id}",
        bcc_id="BCC1",
        avg_mw=avg_mw,
        priority=PriorityLevel.P3,
        cumulative_minutes=score,
        priority_weight=3,
        fairness_score=score,
        zone_id="Z1",
    )


def test_greedy_meets_target():
    feeders = [_fc("F1", 10.0), _fc("F2", 15.0), _fc("F3", 20.0), _fc("F4", 5.0)]
    result = select_feeders(target_mw=50.0, eligible=feeders, max_overshoot_pct=0.10)
    assert sum(f.avg_mw for f in result.selected) == 50.0
    assert not result.is_partial


def test_greedy_overshoot_tolerance():
    feeders = [_fc("F1", 54.0)]
    result = select_feeders(target_mw=50.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.selected[0].avg_mw == 54.0
    assert not result.is_partial


def test_greedy_shortfall():
    feeders = [_fc("F1", 60.0)]
    result = select_feeders(target_mw=100.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.is_partial
    assert result.shortfall_mw == 40.0


def test_greedy_zero_target():
    feeders = [_fc("F1", 10.0)]
    result = select_feeders(target_mw=0.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 0


def test_greedy_fairness_ordering():
    feeders = [_fc("F1", 30.0, score=100.0), _fc("F2", 30.0, score=10.0), _fc("F3", 30.0, score=50.0)]
    result = select_feeders(target_mw=30.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.selected[0].feeder_id == "F2"


def test_greedy_deterministic():
    feeders = [_fc("F1", 10.0), _fc("F2", 20.0), _fc("F3", 30.0)]
    res1 = select_feeders(target_mw=40.0, eligible=feeders, max_overshoot_pct=0.10)
    res2 = select_feeders(target_mw=40.0, eligible=feeders, max_overshoot_pct=0.10)
    assert [f.feeder_id for f in res1.selected] == [f.feeder_id for f in res2.selected]
