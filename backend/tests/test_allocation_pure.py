"""Pure tests for the allocation engine: no database needed.

Tests the CRC split, BCC largest-remainder, fairness scoring,
eligibility rules, and greedy feeder selection against the
documented specifications.
"""
import pytest
from datetime import datetime, timezone, timedelta

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
    assert sum(result.values()) == 350.0


def test_crc_split_zero():
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(0, shares)
    assert result["CRC_N"] == 0.0
    assert result["CRC_S"] == 0.0


@pytest.mark.parametrize("deficit", [100.0, 201.0, 350.0, 500.0])
def test_crc_split_sum_conservation(deficit):
    shares = [CrcShare(crc_id="CRC_N", share_key=0.67), CrcShare(crc_id="CRC_S", share_key=0.33)]
    result = allocate_to_crcs(deficit, shares)
    assert sum(result.values()) == deficit


# --- BCC allocation ---

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
    assert sum(result.values()) == target


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
    # Inverted priority weights: P5 (lowest cost, shed first) = 1, P1 (highest cost, protected) = 5
    assert PRIORITY_WEIGHT[PriorityLevel.P5] < PRIORITY_WEIGHT[PriorityLevel.P4]
    assert PRIORITY_WEIGHT[PriorityLevel.P4] < PRIORITY_WEIGHT[PriorityLevel.P3]
    assert PRIORITY_WEIGHT[PriorityLevel.P3] < PRIORITY_WEIGHT[PriorityLevel.P2]
    assert PRIORITY_WEIGHT[PriorityLevel.P2] < PRIORITY_WEIGHT[PriorityLevel.P1]


def test_fairness_score_fresh_feeders():
    score_p5 = compute_fairness_score(0.0, PriorityLevel.P5)
    score_p1 = compute_fairness_score(0.0, PriorityLevel.P1)
    assert score_p5 == 0.0
    assert score_p1 == 0.0


def test_fairness_score_after_shedding():
    # Lower score = shed first
    # After 30 min shed:
    # P5 score = 30 / 1 = 30
    # P3 score = 30 / 3 = 10 -> P3 would have a lower raw score if pure division,
    # but P5 has weight=1 so 30/1 = 30 vs 30/3 = 10.
    score_p5 = compute_fairness_score(30.0, PriorityLevel.P5)
    score_p3 = compute_fairness_score(30.0, PriorityLevel.P3)
    assert score_p3 < score_p5


# --- Eligibility rules ---

def test_p0_never_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P0, critical=False, status=FeederStatus.CLOSED,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert not eligible


def test_critical_never_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=True, status=FeederStatus.CLOSED,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert not eligible


def test_open_feeder_not_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.OPEN,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert not eligible


def test_maintenance_not_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.MAINTENANCE,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert not eligible


def test_closed_feeder_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.CLOSED,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert eligible


def test_rest_time_enforced():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    last_end = now - timedelta(minutes=60)  # Only 60 min rest, requires 180 min
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.CLOSED,
        last_shed_end=last_end, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert not eligible


def test_rest_time_met():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    last_end = now - timedelta(minutes=200)  # 200 min rest > 180 min
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.CLOSED,
        last_shed_end=last_end, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids=set(), feeder_id="F-101"
    )
    assert eligible


def test_already_assigned_not_eligible():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    eligible = is_eligible(
        priority=PriorityLevel.P3, critical=False, status=FeederStatus.CLOSED,
        last_shed_end=None, slot_start=now, rest_time_minutes=180,
        assigned_feeder_ids={"F-101"}, feeder_id="F-101"
    )
    assert not eligible


# --- Greedy selector ---

def _fc(feeder_id: str, avg_mw: float, score: float = 0.0) -> FeederCandidate:
    return FeederCandidate(
        feeder_id=feeder_id,
        name=f"Feeder-{feeder_id}",
        bcc_id="BCC1",
        avg_mw=avg_mw,
        priority=PriorityLevel.P3,
        cumulative_minutes=score,
        priority_weight=3,
        fairness_score=score / 3.0,
        zone_id="Z-TEST-1",
    )


def test_greedy_meets_target():
    feeders = [_fc("F-1", 10.0), _fc("F-2", 15.0), _fc("F-3", 25.0)]
    result = select_feeders(target_mw=50.0, eligible=feeders, max_overshoot_pct=0.10)
    assert result.achieved_mw == 50.0
    assert not result.is_partial


def test_greedy_overshoot_tolerance():
    feeders = [_fc("F-1", 54.0)]
    result = select_feeders(target_mw=50.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.achieved_mw == 54.0
    assert not result.is_partial


def test_greedy_shortfall():
    feeders = [_fc("F-1", 60.0)]
    result = select_feeders(target_mw=100.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.is_partial
    assert result.shortfall_mw == 40.0


def test_greedy_zero_target():
    feeders = [_fc("F-1", 10.0)]
    result = select_feeders(target_mw=0.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 0


def test_greedy_fairness_ordering():
    # Lower fairness score is selected first!
    feeders = [_fc("F-1", 30.0, score=100.0), _fc("F-2", 30.0, score=10.0), _fc("F-3", 30.0, score=50.0)]
    result = select_feeders(target_mw=30.0, eligible=feeders, max_overshoot_pct=0.10)
    assert len(result.selected) == 1
    assert result.selected[0].feeder_id == "F-2"


def test_greedy_deterministic():
    feeders = [_fc("F-1", 10.0), _fc("F-2", 20.0), _fc("F-3", 30.0)]
    res1 = select_feeders(target_mw=40.0, eligible=feeders, max_overshoot_pct=0.10)
    res2 = select_feeders(target_mw=40.0, eligible=feeders, max_overshoot_pct=0.10)
    assert [f.feeder_id for f in res1.selected] == [f.feeder_id for f in res2.selected]


def test_greedy_p5_selected_before_higher_priority():
    # P5 feeder has been shed before (score = 50.0)
    # P3 feeder is fresh (score = 0.0)
    # P5 must be selected FIRST before P3 despite having a higher fairness score!
    p5_feeder = FeederCandidate(
        feeder_id="F-P5",
        name="Feeder-P5",
        bcc_id="BCC1",
        avg_mw=20.0,
        priority=PriorityLevel.P5,
        cumulative_minutes=50.0,
        priority_weight=1,
        fairness_score=50.0,
        zone_id="Z-1",
    )
    p3_feeder = FeederCandidate(
        feeder_id="F-P3",
        name="Feeder-P3",
        bcc_id="BCC1",
        avg_mw=20.0,
        priority=PriorityLevel.P3,
        cumulative_minutes=0.0,
        priority_weight=3,
        fairness_score=0.0,
        zone_id="Z-2",
    )
    result = select_feeders(target_mw=20.0, eligible=[p3_feeder, p5_feeder])
    assert len(result.selected) == 1
    assert result.selected[0].feeder_id == "F-P5"


def test_greedy_cascading_when_p5_insufficient():
    # P5 has 15 MW, but target is 30 MW. Must select P5 first, then cascade to P4.
    p5 = FeederCandidate(
        feeder_id="F-P5",
        name="Feeder-P5",
        bcc_id="BCC1",
        avg_mw=15.0,
        priority=PriorityLevel.P5,
        cumulative_minutes=10.0,
        priority_weight=1,
        fairness_score=10.0,
        zone_id="Z-1",
    )
    p4 = FeederCandidate(
        feeder_id="F-P4",
        name="Feeder-P4",
        bcc_id="BCC1",
        avg_mw=15.0,
        priority=PriorityLevel.P4,
        cumulative_minutes=0.0,
        priority_weight=2,
        fairness_score=0.0,
        zone_id="Z-2",
    )
    p3 = FeederCandidate(
        feeder_id="F-P3",
        name="Feeder-P3",
        bcc_id="BCC1",
        avg_mw=15.0,
        priority=PriorityLevel.P3,
        cumulative_minutes=0.0,
        priority_weight=3,
        fairness_score=0.0,
        zone_id="Z-3",
    )
    result = select_feeders(target_mw=30.0, eligible=[p3, p4, p5])
    assert len(result.selected) == 2
    selected_ids = [f.feeder_id for f in result.selected]
    assert selected_ids == ["F-P5", "F-P4"]


def test_greedy_prefers_rested_over_resting_candidate():
    # P5 feeder is currently resting (60 min left)
    # P4 feeder is fully rested (0 min left)
    # The rested P4 feeder must be selected over the resting P5 feeder to plan rotation!
    p5_resting = FeederCandidate(
        feeder_id="F-P5-RESTING",
        name="Feeder-P5-Resting",
        bcc_id="BCC1",
        avg_mw=10.0,
        priority=PriorityLevel.P5,
        cumulative_minutes=30.0,
        priority_weight=1,
        fairness_score=30.0,
        zone_id="Z-1",
        rest_time_left_min=60.0,
    )
    p4_rested = FeederCandidate(
        feeder_id="F-P4-RESTED",
        name="Feeder-P4-Rested",
        bcc_id="BCC1",
        avg_mw=10.0,
        priority=PriorityLevel.P4,
        cumulative_minutes=0.0,
        priority_weight=2,
        fairness_score=0.0,
        zone_id="Z-2",
        rest_time_left_min=0.0,
    )
    result = select_feeders(target_mw=10.0, eligible=[p5_resting, p4_rested])
    assert len(result.selected) == 1
    assert result.selected[0].feeder_id == "F-P4-RESTED"


def test_greedy_resting_fallback_picks_longest_rested():
    # When all candidates are in rest window, pick the one that has rested the longest
    # (smallest rest_time_left_min)
    cand_short_rest = FeederCandidate(
        feeder_id="F-1",
        name="Feeder-1",
        bcc_id="BCC1",
        avg_mw=10.0,
        priority=PriorityLevel.P5,
        cumulative_minutes=30.0,
        priority_weight=1,
        fairness_score=30.0,
        zone_id="Z-1",
        rest_time_left_min=150.0,  # rested only 30 min out of 180
    )
    cand_long_rest = FeederCandidate(
        feeder_id="F-2",
        name="Feeder-2",
        bcc_id="BCC1",
        avg_mw=10.0,
        priority=PriorityLevel.P5,
        cumulative_minutes=30.0,
        priority_weight=1,
        fairness_score=30.0,
        zone_id="Z-2",
        rest_time_left_min=60.0,  # rested 120 min out of 180
    )
    result = select_feeders(target_mw=10.0, eligible=[cand_short_rest, cand_long_rest])
    assert len(result.selected) == 1
    assert result.selected[0].feeder_id == "F-2"


def test_two_slot_rotation_selection():
    # Slot 1: F1 and F2 (P5) are selected.
    # In Slot 2 (after 30 min): F1 and F2 cannot be selected because they just shed
    # for 30 min (would exceed 45 min continuous shed) and are resting.
    # Slot 2 must rotate to F3 and F4 (P4).
    f1 = FeederCandidate("F1", "F1", "BCC1", 10.0, PriorityLevel.P5, 0.0, 1, 0.0, "Z1", rest_time_left_min=0.0)
    f2 = FeederCandidate("F2", "F2", "BCC1", 10.0, PriorityLevel.P5, 0.0, 1, 0.0, "Z1", rest_time_left_min=0.0)
    f3 = FeederCandidate("F3", "F3", "BCC1", 10.0, PriorityLevel.P4, 0.0, 2, 0.0, "Z2", rest_time_left_min=0.0)
    f4 = FeederCandidate("F4", "F4", "BCC1", 10.0, PriorityLevel.P4, 0.0, 2, 0.0, "Z2", rest_time_left_min=0.0)

    # Slot 1 selection
    slot1_res = select_feeders(20.0, eligible=[f1, f2, f3, f4])
    assert [f.feeder_id for f in slot1_res.selected] == ["F1", "F2"]

    # Slot 2 candidates: F1 and F2 are now resting, F3 and F4 are rested
    f1_slot2 = FeederCandidate("F1", "F1", "BCC1", 10.0, PriorityLevel.P5, 30.0, 1, 30.0, "Z1", rest_time_left_min=180.0)
    f2_slot2 = FeederCandidate("F2", "F2", "BCC1", 10.0, PriorityLevel.P5, 30.0, 1, 30.0, "Z1", rest_time_left_min=180.0)
    f3_slot2 = FeederCandidate("F3", "F3", "BCC1", 10.0, PriorityLevel.P4, 0.0, 2, 0.0, "Z2", rest_time_left_min=0.0)
    f4_slot2 = FeederCandidate("F4", "F4", "BCC1", 10.0, PriorityLevel.P4, 0.0, 2, 0.0, "Z2", rest_time_left_min=0.0)

    slot2_res = select_feeders(20.0, eligible=[f1_slot2, f2_slot2, f3_slot2, f4_slot2])
    # Must rotate to F3 and F4!
    assert [f.feeder_id for f in slot2_res.selected] == ["F3", "F4"]

