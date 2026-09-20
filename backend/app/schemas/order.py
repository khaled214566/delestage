from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.enums import OrderStatus, AllocationLevel

class ShedOrderCreate(BaseModel):
    plan_id: int

class AllocationSummary(BaseModel):
    slot_id: int
    slot_start: datetime
    slot_end: datetime
    deficit_mw: float
    achieved_mw: float
    shortfall_mw: float
    is_partial: bool

class FeederAssignmentOut(BaseModel):
    id: int
    feeder_id: str
    feeder_name: str
    assigned_mw: float
    priority: str
    fairness_score: float
    is_manual: bool
    assigned_at: datetime
    assigned_by: Optional[int]

    model_config = {"from_attributes": True}

class AllocationNodeOut(BaseModel):
    id: int
    level: AllocationLevel
    entity_id: str
    target_mw: float
    achieved_mw: float
    shortfall_mw: float
    is_partial: bool
    children: List["AllocationNodeOut"] = Field(default_factory=list)
    feeder_assignments: List[FeederAssignmentOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}

class ShedOrderOut(BaseModel):
    id: int
    plan_id: int
    status: OrderStatus
    total_deficit_mw: float
    created_by: int
    created_at: datetime
    allocated_at: Optional[datetime] = None
    validated_by: Optional[int] = None
    validated_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_by: Optional[int] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    allocation_nodes: List[AllocationNodeOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}

class OrderListItem(BaseModel):
    id: int
    plan_id: int
    plan_date: date
    plan_mode: str
    status: OrderStatus
    total_deficit_mw: float
    created_at: datetime
    shortfall_count: int

    model_config = {"from_attributes": True}

class CancelRequest(BaseModel):
    reason: str

class ManualFeederAdd(BaseModel):
    feeder_id: str

AllocationNodeOut.model_rebuild()
