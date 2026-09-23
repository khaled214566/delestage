import pytest
from app.engine.rotation import (
    PureRotationCandidate,
    rank_rotation_candidates,
    PRIORITY_WEIGHTS,
)


def test_p0_and_critical_never_selected():
    """P0 and critical feeders must NEVER be proposed as rotation replacements."""
    candidates = [
        PureRotationCandidate(
            id="F_P0",
            name="Hospital Main Line",
            substation_name="Sub A",
            priority="P0",
            avg_mw=5.0,
            cumulative_minutes=0,
            critical=True,
            status="CLOSED",
        ),
        PureRotationCandidate(
            id="F_P5_CRIT",
            name="Water Pumping Station",
            substation_name="Sub A",
            priority="P5",
            avg_mw=5.0,
            cumulative_minutes=0,
            critical=True,
            status="CLOSED",
        ),
        PureRotationCandidate(
            id="F_VALID",
            name="Residential West",
            substation_name="Sub A",
            priority="P5",
            avg_mw=5.0,
            cumulative_minutes=10,
            critical=False,
            status="CLOSED",
        ),
    ]

    proposals = rank_rotation_candidates(outgoing_mw=5.0, candidates=candidates)
    assert len(proposals) == 1
    assert proposals[0].feeder_id == "F_VALID"


def test_only_closed_feeders_eligible():
    """Feeders that are OPEN, MAINTENANCE, or UNAVAILABLE must be rejected."""
    candidates = [
        PureRotationCandidate(
            id="F_OPEN",
            name="Feeder 1",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.0,
            cumulative_minutes=0,
            critical=False,
            status="OPEN",
        ),
        PureRotationCandidate(
            id="F_MAINT",
            name="Feeder 2",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.0,
            cumulative_minutes=0,
            critical=False,
            status="MAINTENANCE",
        ),
        PureRotationCandidate(
            id="F_OK",
            name="Feeder 3",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.0,
            cumulative_minutes=0,
            critical=False,
            status="CLOSED",
        ),
    ]

    proposals = rank_rotation_candidates(outgoing_mw=4.0, candidates=candidates)
    assert len(proposals) == 1
    assert proposals[0].feeder_id == "F_OK"


def test_closest_mw_picked_first_for_power_conservation():
    """UC6 requirement: rotation must maintain total shed MW constant, preferring closest MW match."""
    outgoing_mw = 4.2

    candidates = [
        PureRotationCandidate(
            id="F_FAR",
            name="Feeder Far",
            substation_name="Sub A",
            priority="P5",
            avg_mw=1.5,  # diff = 2.7
            cumulative_minutes=0,
            critical=False,
            status="CLOSED",
        ),
        PureRotationCandidate(
            id="F_CLOSE",
            name="Feeder Close",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.1,  # diff = 0.1
            cumulative_minutes=10,
            critical=False,
            status="CLOSED",
        ),
        PureRotationCandidate(
            id="F_MED",
            name="Feeder Medium",
            substation_name="Sub A",
            priority="P5",
            avg_mw=3.5,  # diff = 0.7
            cumulative_minutes=0,
            critical=False,
            status="CLOSED",
        ),
    ]

    proposals = rank_rotation_candidates(outgoing_mw=outgoing_mw, candidates=candidates)
    assert len(proposals) == 3
    assert proposals[0].feeder_id == "F_CLOSE"
    assert proposals[0].delta_mw == -0.1
    assert proposals[1].feeder_id == "F_MED"
    assert proposals[2].feeder_id == "F_FAR"


def test_tie_breaking_by_fairness_score():
    """When two candidates have the exact same MW difference, the one with lower fairness score is selected."""
    outgoing_mw = 3.0

    # Both candidates have avg_mw = 3.0 (diff = 0)
    # Candidate A: P5 (weight 1), cum_mins = 60 -> score = 60/1 = 60
    # Candidate B: P4 (weight 2), cum_mins = 60 -> score = 60/2 = 30
    candidates = [
        PureRotationCandidate(
            id="F_A",
            name="Feeder A",
            substation_name="Sub A",
            priority="P5",
            avg_mw=3.0,
            cumulative_minutes=60,
            critical=False,
            status="CLOSED",
        ),
        PureRotationCandidate(
            id="F_B",
            name="Feeder B",
            substation_name="Sub A",
            priority="P4",
            avg_mw=3.0,
            cumulative_minutes=60,
            critical=False,
            status="CLOSED",
        ),
    ]

    proposals = rank_rotation_candidates(outgoing_mw=outgoing_mw, candidates=candidates)
    assert len(proposals) == 2
    # Feeder B has fairness_score 30.0 < Feeder A (60.0), so Feeder B is first
    assert proposals[0].feeder_id == "F_B"
    assert proposals[0].fairness_score == 30.0
    assert proposals[1].feeder_id == "F_A"
    assert proposals[1].fairness_score == 60.0


def test_rest_time_compliance_prioritization():
    """Eligible feeders that met rest time come before feeders still in rest time."""
    outgoing_mw = 4.0

    candidates = [
        PureRotationCandidate(
            id="F_RESTING",
            name="Feeder Resting",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.0,  # perfect MW match
            cumulative_minutes=0,
            critical=False,
            status="CLOSED",
            rest_time_left_min=45.0,  # still in rest period
        ),
        PureRotationCandidate(
            id="F_RESTED",
            name="Feeder Rested",
            substation_name="Sub A",
            priority="P5",
            avg_mw=4.3,  # slightly higher MW
            cumulative_minutes=0,
            critical=False,
            status="CLOSED",
            rest_time_left_min=0.0,  # fully rested
        ),
    ]

    proposals = rank_rotation_candidates(outgoing_mw=outgoing_mw, candidates=candidates)
    assert len(proposals) == 2
    # The rested candidate must be recommended first
    assert proposals[0].feeder_id == "F_RESTED"
    assert proposals[0].is_eligible is True
    # The resting candidate is second and flagged as ineligible without override
    assert proposals[1].feeder_id == "F_RESTING"
    assert proposals[1].is_eligible is False
    assert proposals[1].rest_time_left_min == 45.0


def test_rotation_max_results_cap():
    """Verify max_results limits the number of proposed replacements."""
    outgoing_mw = 3.0
    candidates = [
        PureRotationCandidate(
            id=f"F_{i}",
            name=f"Feeder {i}",
            substation_name="Sub A",
            priority="P5",
            avg_mw=3.0 + (i * 0.1),
            cumulative_minutes=i * 10,
            critical=False,
            status="CLOSED",
        )
        for i in range(10)
    ]
    proposals = rank_rotation_candidates(outgoing_mw=outgoing_mw, candidates=candidates, max_results=3)
    assert len(proposals) == 3
    assert proposals[0].feeder_id == "F_0"
    assert proposals[1].feeder_id == "F_1"
    assert proposals[2].feeder_id == "F_2"

