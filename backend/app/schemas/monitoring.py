from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ShedEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    feeder_id: str
    feeder_name: str
    bcc_id: str
    open_time: datetime
    close_time: Optional[datetime] = None
    mw_actual: float
    duration_min: float
    ens_mwh: float
    status: str
    alarm_level: str


class RegionalSummary(BaseModel):
    entity_id: str
    name: str
    target_mw: float
    actual_mw: float
    gap_mw: float
    open_feeders: int


class MonitoringSummary(BaseModel):
    timestamp: datetime
    order_id: Optional[int] = None
    target_mw: float
    actual_mw: float
    gap_mw: float
    open_feeders_count: int
    active_bccs_count: int
    max_duration_min: float
    total_ens_mwh: float
    amber_alarms_count: int
    red_alarms_count: int
    crc_breakdown: List[RegionalSummary]
    bcc_breakdown: List[RegionalSummary]
    active_events: List[ShedEventOut]
