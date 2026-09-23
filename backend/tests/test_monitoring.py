"""Unit tests for M6 real-time monitoring and shed event calculations."""
from datetime import datetime, timezone, timedelta
import pytest

from app.models.event import ShedEvent
from app.models.enums import AlarmLevel, EventStatus


def test_alarm_level_thresholds():
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    
    # 1. Event opened 15 minutes ago (<36 min -> GREEN)
    ev_green = ShedEvent(
        order_id=1, feeder_id="F-101", bcc_id="BCC1",
        open_time=now - timedelta(minutes=15),
        mw_actual=10.0, status=EventStatus.OPEN
    )
    assert ev_green.compute_duration(now) == 15.0
    assert ev_green.get_alarm_level(max_duration_min=45.0, now=now) == AlarmLevel.GREEN

    # 2. Event opened 38 minutes ago (36 <= d < 45 min -> AMBER / 80% rotation threshold)
    ev_amber = ShedEvent(
        order_id=1, feeder_id="F-125", bcc_id="BCC1",
        open_time=now - timedelta(minutes=38),
        mw_actual=12.0, status=EventStatus.OPEN
    )
    assert ev_amber.compute_duration(now) == 38.0
    assert ev_amber.get_alarm_level(max_duration_min=45.0, now=now) == AlarmLevel.AMBER

    # 3. Event opened 46 minutes ago (>=45 min -> RED / 100% breach threshold)
    ev_red = ShedEvent(
        order_id=1, feeder_id="F-130", bcc_id="BCC1",
        open_time=now - timedelta(minutes=46),
        mw_actual=14.0, status=EventStatus.OPEN
    )
    assert ev_red.compute_duration(now) == 46.0
    assert ev_red.get_alarm_level(max_duration_min=45.0, now=now) == AlarmLevel.RED


def test_ens_calculation_formula():
    """Verify Energy Not Supplied: E = (P * delta_t) / 60 MWh."""
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    ev = ShedEvent(
        order_id=1, feeder_id="F-101", bcc_id="BCC1",
        open_time=now - timedelta(minutes=30),
        close_time=now,
        mw_actual=12.0,
        status=EventStatus.CLOSED
    )
    duration = ev.compute_duration()
    assert duration == 30.0
    # 12 MW shed for 30 minutes = 6.0 MWh
    ens = round(ev.mw_actual * duration / 60.0, 3)
    assert ens == 6.0
