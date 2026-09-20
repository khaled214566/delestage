"""Pure tests of compute_deficit(): no database needed.

The five values here are the exact worked example from the documentation,
section 12, use case 1 — this is the M3 "done when" criterion.
"""
import pytest

from app.services.deficit import compute_deficit


@pytest.mark.parametrize("demand,generation,imports,margin,expected", [
    (4350, 3800, 200, 50, 300),
    (4400, 3800, 200, 50, 350),
    (4300, 3800, 200, 50, 250),
    (4150, 3800, 200, 50, 100),
    (4000, 3800, 200, 50, 0),     # raw result is -50, floored at 0
])
def test_documented_worked_example(demand, generation, imports, margin, expected):
    assert compute_deficit(demand, generation, imports, margin) == expected


def test_never_negative():
    assert compute_deficit(0, 1000, 1000, 1000) == 0


def test_real_time_import_edit():
    """19:00 slot: imports drop from 200 to 150 -> deficit goes 300 -> 350."""
    before = compute_deficit(4350, 3800, 200, 50)
    after = compute_deficit(4350, 3800, 150, 50)
    assert before == 300
    assert after == 350
