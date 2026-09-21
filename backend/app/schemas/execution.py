from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ConfirmOpenRequest(BaseModel):
    order_id: int
    feeder_id: str
    open_time: Optional[datetime] = None
    mw_actual: float
    justification: Optional[str] = None


class ConfirmCloseRequest(BaseModel):
    close_time: Optional[datetime] = None


class FeederExecutionItem(BaseModel):
    feeder_id: str
    feeder_name: str
    substation_name: str
    priority: str
    is_critical: bool
    avg_mw: float
    status: str
    is_eligible: bool
    ineligibility_reason: Optional[str] = None
    rest_time_left_min: Optional[float] = None
    is_planned_in_order: bool = False
    current_event_id: Optional[int] = None
    open_time: Optional[datetime] = None
    elapsed_minutes: Optional[float] = None
    alarm_level: Optional[str] = None


class BccExecutionDashboard(BaseModel):
    bcc_id: str
    bcc_name: str
    target_mw: float
    actual_mw: float
    gap_mw: float
    open_feeders_count: int
    feeders: List[FeederExecutionItem]
    order_id: Optional[int] = None
