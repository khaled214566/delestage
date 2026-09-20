"""M3: deficit computation (UC1).

deficit_plan   — one per (date, mode). mode reuses OrderType (J_1 / REAL_TIME):
                 a deficit plan's planning horizon is the exact same J-1-vs-
                 real-time distinction a shed order has, so we don't define a
                 second enum for the same concept.
deficit_slot   — one row per time slot inside a plan. demand/generation/
                 imports/margin are the dispatcher's inputs; deficit_mw is
                 computed by services.deficit.compute_deficit() and stored
                 (not a generated column) so historical rows never change
                 value if the formula's rounding ever changes.
deficit_revision — one row per EDIT to an existing slot (not per creation).
                 Kept separate from the generic audit_log so the dispatcher's
                 "show me every value this slot has ever had" view is a plain
                 indexed query, not a payload-filter over the whole system
                 log. Every edit is still ALSO sent through audit_log via
                 services.deficit, so the system-wide trail stays complete.
"""
from datetime import date as date_, datetime
from datetime import UTC

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import DeficitPlanStatus, OrderType


class DeficitPlan(Base):
    __tablename__ = "deficit_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    mode: Mapped[OrderType] = mapped_column(
        # OrderType.J_1's name ("J_1") differs from its value ("J-1") — the
        # DB enum type (see migration 0005) holds the values, so this must
        # too, or every write/read of this column raises at the DB.
        Enum(OrderType, name="ordertype", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    status: Mapped[DeficitPlanStatus] = mapped_column(
        Enum(DeficitPlanStatus, name="deficitplanstatus"),
        nullable=False,
        default=DeficitPlanStatus.DRAFT,
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    slots: Mapped[list["DeficitSlot"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", passive_deletes=True,
        order_by="DeficitSlot.slot_start",
    )

    __table_args__ = (
        UniqueConstraint("date", "mode", name="uq_deficit_plan_date_mode"),
    )


class DeficitSlot(Base):
    __tablename__ = "deficit_slot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("deficit_plan.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    imports_mw: Mapped[float] = mapped_column(Float, nullable=False)
    margin_mw: Mapped[float] = mapped_column(Float, nullable=False)
    deficit_mw: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    plan: Mapped["DeficitPlan"] = relationship(back_populates="slots")
    revisions: Mapped[list["DeficitRevision"]] = relationship(
        back_populates="slot", cascade="all, delete-orphan", passive_deletes=True,
        order_by="DeficitRevision.changed_at",
    )

    __table_args__ = (
        UniqueConstraint("plan_id", "slot_start", name="uq_deficit_slot_plan_start"),
        CheckConstraint("slot_end > slot_start", name="ck_deficit_slot_window_ordered"),
        CheckConstraint("demand_mw >= 0", name="ck_deficit_slot_demand_non_negative"),
        CheckConstraint("generation_mw >= 0", name="ck_deficit_slot_generation_non_negative"),
        CheckConstraint("imports_mw >= 0", name="ck_deficit_slot_imports_non_negative"),
        CheckConstraint("margin_mw >= 0", name="ck_deficit_slot_margin_non_negative"),
        CheckConstraint("deficit_mw >= 0", name="ck_deficit_slot_deficit_floored_at_zero"),
    )


class DeficitRevision(Base):
    __tablename__ = "deficit_revision"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("deficit_slot.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    old_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False)

    slot: Mapped["DeficitSlot"] = relationship(back_populates="revisions")
