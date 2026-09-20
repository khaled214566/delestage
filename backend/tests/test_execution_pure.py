"""Unit tests for M7 BCC execution rules, P0 restrictions, and rest-time constraints."""
from datetime import datetime, timezone, timedelta
import pytest

from app.models.enums import PriorityLevel, FeederStatus
from app.engine.rules import is_eligible


def test_p0_refusal_absolute():
    """Verify that Priority P0 feeders can NEVER be shed."""
    now = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    # Feeder with P0 priority must always return False
    eligible = is_eligible(
        priority=PriorityLevel.P0,
        critical=True,
        status=FeederStatus.CLOSED,
        last_shed_end=None,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F-HOSPITAL",
    )
    assert eligible is False


def test_rest_time_strictness():
    """Verify rest time constraint: less than 180 min must be blocked without justification."""
    now = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    # Feeder shed 100 minutes ago (needs 180 min)
    last_end = now - timedelta(minutes=100)
    eligible = is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=last_end,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F-125",
    )
    assert eligible is False

    # After 181 minutes, it becomes eligible
    last_end_ok = now - timedelta(minutes=181)
    eligible_ok = is_eligible(
        priority=PriorityLevel.P3,
        critical=False,
        status=FeederStatus.CLOSED,
        last_shed_end=last_end_ok,
        slot_start=now,
        rest_time_minutes=180,
        assigned_feeder_ids=set(),
        feeder_id="F-125",
    )
    assert eligible_ok is True
