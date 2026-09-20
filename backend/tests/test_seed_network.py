"""Pure tests of the synthetic grid generator: no database needed."""
from datetime import timedelta

import pytest

from seed.generate import (
    BCCS,
    REFERENCE_TIME,
    apportion,
    build_network,
    feeder_count,
)

SEEDS = [42, 1, 7, 99, 2026, 31337]


@pytest.fixture(scope="module")
def net():
    return build_network(seed=42)


# --- determinism ----------------------------------------------------------
def test_same_seed_gives_identical_data():
    a, b = build_network(seed=42), build_network(seed=42)
    assert a == b
    assert a.fingerprint() == b.fingerprint()


def test_different_seed_gives_different_data():
    assert build_network(seed=42).fingerprint() != build_network(seed=43).fingerprint()


def test_no_wall_clock_leaks_into_data(net):
    """Everything time-based is anchored on REFERENCE_TIME, never on now()."""
    stamps = [h["last_shed_end"] for h in net.histories if h["last_shed_end"]]
    stamps += [f["created_at"] for f in net.feeders]
    assert stamps and all(s <= REFERENCE_TIME for s in stamps)


def test_values_are_native_python_types(net):
    """NumPy scalars leaking into rows is what broke the first seed ('Pr' for 'P4')."""
    f = net.feeders[0]
    assert type(f["priority"]) is str and type(f["avg_mw"]) is float and type(f["critical"]) is bool
    h = next(h for h in net.histories if h["rotations"])
    assert type(h["cumulative_minutes"]) is int and type(h["rotations"]) is int


# --- topology -------------------------------------------------------------
def test_topology_matches_the_documentation(net):
    assert len(net.crcs) == 2 and len(net.bccs) == 7 and len(net.substations) == 21
    assert sum(b["managed_load_mw"] for b in net.bccs) == 1830
    assert sum(c["share_key"] for c in net.crcs) == pytest.approx(1.0)
    assert net.parameters["regional_key"] == {c["id"]: c["share_key"] for c in net.crcs}
    assert net.parameters["max_duration_min"] == 45 and net.parameters["rest_time_min"] == 180


# --- the two "done when" criteria of M1 -----------------------------------
def test_sheddable_mw_is_well_above_300(net):
    sheddable = sum(f["avg_mw"] for f in net.feeders if f["priority"] != "P0")
    assert sheddable > 1000     # order of magnitude above the 300 MW demo deficit


# --- invariants that must hold for ANY seed --------------------------------
@pytest.mark.parametrize("seed", SEEDS)
def test_invariants(seed):
    n = build_network(seed=seed)
    ids = [f["id"] for f in n.feeders]
    assert len(ids) == len(set(ids))
    assert 150 <= len(n.feeders) <= 190

    p0 = sum(f["priority"] == "P0" for f in n.feeders)
    assert 0.06 <= p0 / len(n.feeders) <= 0.10

    subs = {s["id"]: s["bcc_id"] for s in n.substations}
    for b in n.bccs:
        fs = [f for f in n.feeders if f["bcc_id"] == b["id"]]
        assert len(fs) == feeder_count(b["managed_load_mw"])
        assert sum(f["avg_mw"] for f in fs) == pytest.approx(b["managed_load_mw"], abs=0.05)
        assert any(f["priority"] == "P0" for f in fs), f"{b['id']} has no P0 feeder"

    for f in n.feeders:
        assert 5.0 <= f["avg_mw"] <= 20.0
        assert f["critical"] == (f["priority"] == "P0")
        assert subs[f["substation_id"]] == f["bcc_id"]          # denormalised bcc_id is consistent
        assert len(f["zone_id"]) <= 30 and f["zone_id"].startswith("Z-")

    assert sorted(h["feeder_id"] for h in n.histories) == sorted(ids)   # exactly one history each


@pytest.mark.parametrize("seed", SEEDS)
def test_histories_are_consistent(seed):
    n = build_network(seed=seed)
    prio = {f["id"]: f["priority"] for f in n.feeders}
    for h in n.histories:
        if prio[h["feeder_id"]] == "P0":
            assert h["cumulative_minutes"] == 0 and h["rotations"] == 0 and h["last_shed_end"] is None
        if h["rotations"] == 0:
            assert h["cumulative_minutes"] == 0 and h["last_shed_end"] is None
        else:
            assert 15 * h["rotations"] <= h["cumulative_minutes"] <= 45 * h["rotations"]
            assert h["last_shed_start"] < h["last_shed_end"] <= REFERENCE_TIME


def test_histories_are_varied_and_rest_time_is_demonstrable(net):
    non_p0 = [h for h in net.histories if h["rotations"] > 0]
    assert len({h["cumulative_minutes"] for h in non_p0}) > 30
    assert any(h["rotations"] == 0 for h in net.histories if h["feeder_id"] in
               {f["id"] for f in net.feeders if f["priority"] != "P0"})       # some never shed
    in_rest = [h for h in net.histories if h["last_shed_end"]
               and REFERENCE_TIME - h["last_shed_end"] < timedelta(minutes=180)]
    assert in_rest, "no feeder inside its rest time: the rest-time rule could not be demoed"


def test_special_statuses_exercise_the_view(net):
    special = {f["id"]: f["status"] for f in net.feeders if f["status"] != "CLOSED"}
    assert sorted(special.values()) == ["MAINTENANCE", "UNAVAILABLE"]
    assert all(next(f for f in net.feeders if f["id"] == i)["priority"] != "P0" for i in special)


# --- largest-remainder apportionment (shared with the M5 allocator) --------
def test_apportion_reproduces_the_documented_example():
    """Use case 3: 201 MW split over managed loads 420/360/240/180 -> 71/60/40/30."""
    assert apportion(201, {"BCC1": 420, "BCC2": 360, "BCC3": 240, "BCC4": 180}) == {
        "BCC1": 71, "BCC2": 60, "BCC3": 40, "BCC4": 30,
    }


@pytest.mark.parametrize("total", [0, 1, 7, 100, 201, 300, 999])
def test_apportion_always_sums_exactly(total):
    weights = {b["id"]: b["managed_load_mw"] for b in BCCS}
    shares = apportion(total, weights)
    assert sum(shares.values()) == total and all(v >= 0 for v in shares.values())
