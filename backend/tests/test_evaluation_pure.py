"""Unit tests for M12 evaluation & benchmark engine."""
from app.engine.evaluation import compute_gini_index, run_benchmark_simulation


def test_gini_index_perfect_equality():
    # When all values are equal, Gini is 0.0
    assert compute_gini_index([10.0, 10.0, 10.0, 10.0]) == 0.0
    assert compute_gini_index([0.0, 0.0]) == 0.0


def test_gini_index_extreme_inequality():
    # When one entity holds all value, Gini approaches 1.0
    values = [0.0] * 99 + [1000.0]
    gini = compute_gini_index(values)
    assert gini > 0.95


def test_benchmark_simulation_invariants():
    results = run_benchmark_simulation(days=7)
    assert len(results) == 3

    intelligent = results[0]
    naive = results[1]
    random = results[2]

    # Invariant 1: Intelligent engine MUST have exactly ZERO P0 violations
    assert intelligent.p0_violations == 0, "Intelligent engine violated P0 critical infrastructure!"

    # Invariant 2: Naive baseline without checks MUST produce P0 violations
    assert naive.p0_violations > 0

    # Invariant 3: Intelligent engine MUST be significantly fairer (lower Gini) than naive
    assert intelligent.gini_index < naive.gini_index
    assert intelligent.fairness_advantage_pct > 50.0

    # Invariant 4: Maximum duration cap respected (<= 45 min)
    assert intelligent.max_duration_min <= 45.0
