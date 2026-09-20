"""Schema and seed tests against a real PostgreSQL (skipped if unreachable).

Each test runs in a rolled-back transaction: your dev data is never modified.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from seed.generate import build_network, write_network

pytestmark = pytest.mark.db


@pytest.fixture()
def seeded(db):
    net = build_network()
    write_network(db, net)
    return net


def snapshot(db):
    q = lambda sql: db.execute(text(sql)).all()
    return (q("select * from feeder order by id"), q("select * from feeder_history order by id"),
            q("select * from substation order by id"), q("select * from parameters"))


def rejected(db, sql, **params):
    """True if the statement violates a database constraint."""
    try:
        with db.begin_nested():
            db.execute(text(sql), params)
    except IntegrityError:
        return True
    return False


# --- seed -----------------------------------------------------------------
def test_seed_matches_the_generator(db, seeded):
    assert db.scalar(text("select count(*) from feeder")) == len(seeded.feeders)
    assert db.scalar(text("select count(*) from feeder_history")) == len(seeded.feeders)
    assert db.scalar(text("select count(*) from bcc")) == 7
    assert db.scalar(text("select count(*) from parameters")) == 1


def test_seeding_twice_gives_identical_tables(db, seeded):
    first = snapshot(db)
    write_network(db, build_network())
    assert snapshot(db) == first


# --- v_sheddable_feeders ---------------------------------------------------
def test_view_contains_exactly_the_sheddable_feeders(db, seeded):
    expected = {f["id"] for f in seeded.feeders if f["priority"] != "P0" and f["status"] not in ("MAINTENANCE", "UNAVAILABLE")}
    # Join back to `feeder` so priority/critical/status are checked independently of the view's own columns.
    rows = db.execute(text("select v.id, f.priority, f.critical, f.status, v.avg_mw from v_sheddable_feeders v "
                           "join feeder f on f.id = v.id")).all()
    assert {r.id for r in rows} == expected
    assert not any(r.priority == "P0" or r.critical or r.status in ("MAINTENANCE", "UNAVAILABLE") for r in rows)
    assert sum(r.avg_mw for r in rows) > 300


def test_view_follows_status_changes(db, seeded):
    fid = next(f["id"] for f in seeded.feeders if f["priority"] == "P3" and f["status"] == "CLOSED")
    count = lambda: db.scalar(text("select count(*) from v_sheddable_feeders where id = :i"), {"i": fid})
    assert count() == 1
    db.execute(text("update feeder set status = 'MAINTENANCE' where id = :i"), {"i": fid})
    assert count() == 0
    db.execute(text("update feeder set status = 'OPEN' where id = :i"), {"i": fid})
    assert count() == 1          # OPEN feeders stay part of the sheddable capacity


# --- constraints ----------------------------------------------------------
INSERT_FEEDER = ("insert into feeder (id, name, substation_id, bcc_id, priority, critical, avg_mw, zone_id, status) "
                 "values ('F-TEST', 't', :ss, :bcc, :prio, :crit, :mw, 'Z-TEST-1', 'CLOSED')")


def test_valid_feeder_is_accepted(db, seeded):
    assert not rejected(db, INSERT_FEEDER, ss="SS-101", bcc="BCC1", prio="P4", crit=False, mw=10.0)


def test_p0_feeder_must_be_critical(db, seeded):
    assert rejected(db, INSERT_FEEDER, ss="SS-101", bcc="BCC1", prio="P0", crit=False, mw=10.0)
    assert not rejected(db, INSERT_FEEDER, ss="SS-101", bcc="BCC1", prio="P0", crit=True, mw=10.0)


@pytest.mark.parametrize("mw", [0, -3.5])
def test_feeder_power_must_be_positive(db, seeded, mw):
    assert rejected(db, INSERT_FEEDER, ss="SS-101", bcc="BCC1", prio="P4", crit=False, mw=mw)


def test_feeder_bcc_must_match_its_substation(db, seeded):
    """SS-101 belongs to BCC1: declaring the feeder under BCC2 must be impossible."""
    assert rejected(db, INSERT_FEEDER, ss="SS-101", bcc="BCC2", prio="P4", crit=False, mw=10.0)


def test_feeder_needs_an_existing_substation(db, seeded):
    assert rejected(db, INSERT_FEEDER, ss="SS-999", bcc="BCC1", prio="P4", crit=False, mw=10.0)


def test_only_one_parameters_row(db, seeded):
    assert rejected(db, "insert into parameters (id) values (2)")


@pytest.mark.parametrize("column,value", [
    ("rotation_warn_pct", 120), ("rotation_warn_pct", 0), ("slot_size_min", 20),
    ("max_duration_min", 0), ("rest_time_min", -1),
])
def test_parameter_ranges_are_enforced(db, seeded, column, value):
    assert rejected(db, f"update parameters set {column} = :v", v=value)


def test_history_window_must_be_ordered(db, seeded):
    sql = ("update feeder_history set last_shed_start = :s, last_shed_end = :e "
           "where feeder_id = (select id from feeder where priority = 'P4' limit 1)")
    assert rejected(db, sql, s="2026-09-19T10:00:00Z", e="2026-09-19T09:00:00Z")
    assert not rejected(db, sql, s="2026-09-19T09:00:00Z", e="2026-09-19T10:00:00Z")


def test_deleting_a_bcc_cascades_to_its_feeders(db, seeded):
    db.execute(text("delete from bcc where id = 'BCC7'"))
    assert db.scalar(text("select count(*) from feeder where bcc_id = 'BCC7'")) == 0
    assert db.scalar(text("select count(*) from feeder_history h where not exists "
                          "(select 1 from feeder f where f.id = h.feeder_id)")) == 0
