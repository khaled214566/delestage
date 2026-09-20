from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ReplacementCandidate(BaseModel):
    feeder_id: str
    feeder_name: str
    substation_name: str
    priority: str
    avg_mw: float
    delta_mw: float  # Difference relative to outgoing feeder MW: candidate.avg_mw - outgoing.avg_mw
    fairness_score: float
    cumulative_minutes: int
    rest_time_left_min: Optional[float] = None
    is_eligible: bool = True
    ineligibility_reason: Optional[str] = None


class RotationProposal(BaseModel):
    outgoing_event_id: int
    outgoing_feeder_id: str
    outgoing_feeder_name: str
    substation_name: str
    bcc_id: str
    bcc_name: str
    open_time: datetime
    elapsed_minutes: float
    max_duration_minutes: float
    elapsed_ratio: float
    alarm_level: str  # "AMBER" (>=80%) or "RED" (>=100%)
    outgoing_mw: float
    recommended_replacement: Optional[ReplacementCandidate] = None
    alternatives: List[ReplacementCandidate] = Field(default_factory=list)


class ExecuteRotationRequest(BaseModel):
    outgoing_event_id: int
    replacement_feeder_id: str
    replacement_mw: Optional[float] = None
    justification: Optional[str] = None


class ExecuteRotationResponse(BaseModel):
    status: str = "SUCCESS"
    outgoing_feeder_id: str
    replacement_feeder_id: str
    opened_event_id: int
    restored_event_id: int
    outgoing_mw: float
    replacement_mw: float
    delta_mw: float
    ens_mwh: float
    duration_min: float
    rotations_count: int
    message: str
