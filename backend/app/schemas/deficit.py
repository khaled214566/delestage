from datetime import date as date_, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DeficitPlanStatus, OrderType


class DeficitPlanCreate(BaseModel):
    date: date_
    mode: OrderType = OrderType.J_1


class DeficitSlotIn(BaseModel):
    """Manual create/edit of one slot. slot_end must be given explicitly
    (not derived from Parameters.slot_size_min) so a slot's width is never a
    silent side effect of a system-wide setting that could change later."""
    slot_start: datetime
    slot_end: datetime
    demand_mw: float = Field(ge=0)
    generation_mw: float = Field(ge=0)
    imports_mw: float = Field(ge=0)
    margin_mw: float = Field(ge=0)

    @model_validator(mode="after")
    def _window_ordered(self) -> "DeficitSlotIn":
        if self.slot_end <= self.slot_start:
            raise ValueError("slot_end must be after slot_start")
        return self


class DeficitSlotPatch(BaseModel):
    """PATCH: only the fields the dispatcher is actually changing."""
    demand_mw: float | None = Field(default=None, ge=0)
    generation_mw: float | None = Field(default=None, ge=0)
    imports_mw: float | None = Field(default=None, ge=0)
    margin_mw: float | None = Field(default=None, ge=0)


class DeficitSlotOut(BaseModel):
    id: int
    plan_id: int
    slot_start: datetime
    slot_end: datetime
    demand_mw: float
    generation_mw: float
    imports_mw: float
    margin_mw: float
    deficit_mw: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeficitPlanOut(BaseModel):
    id: int
    date: date_
    mode: OrderType
    status: DeficitPlanStatus
    created_by: int
    created_at: datetime
    validated_by: int | None
    validated_at: datetime | None
    slots: list[DeficitSlotOut] = []

    model_config = {"from_attributes": True}


class DeficitRevisionOut(BaseModel):
    id: int
    slot_id: int
    changed_by: int
    changed_at: datetime
    old_values: dict
    new_values: dict

    model_config = {"from_attributes": True}


class CsvImportResult(BaseModel):
    created: int
    updated: int
    slots: list[DeficitSlotOut]
