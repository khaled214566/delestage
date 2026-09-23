from datetime import datetime, UTC
from sqlalchemy import Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional

from app.core.database import Base
from app.models.enums import OrderStatus, AllocationLevel

class ShedOrder(Base):
    __tablename__ = "shed_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("deficit_plan.id", ondelete="CASCADE"), unique=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="orderstatus"), default=OrderStatus.DRAFT)
    total_deficit_mw: Mapped[float] = mapped_column(Float, default=0.0)
    
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    validated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    cancelled_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    plan: Mapped["DeficitPlan"] = relationship("DeficitPlan", back_populates="order")
    allocation_nodes: Mapped[List["AllocationNode"]] = relationship("AllocationNode", back_populates="order", cascade="all, delete-orphan", passive_deletes=True)


class AllocationNode(Base):
    __tablename__ = "allocation_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("shed_order.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("deficit_slot.id", ondelete="CASCADE"))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("allocation_node.id", ondelete="CASCADE"), nullable=True)
    level: Mapped[AllocationLevel] = mapped_column(Enum(AllocationLevel, name="allocationlevel"))
    entity_id: Mapped[str] = mapped_column(String)
    
    target_mw: Mapped[float] = mapped_column(Float, default=0.0)
    achieved_mw: Mapped[float] = mapped_column(Float, default=0.0)
    shortfall_mw: Mapped[float] = mapped_column(Float, default=0.0)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)

    order: Mapped["ShedOrder"] = relationship("ShedOrder", back_populates="allocation_nodes")
    slot: Mapped["DeficitSlot"] = relationship("DeficitSlot")
    parent: Mapped[Optional["AllocationNode"]] = relationship("AllocationNode", remote_side=[id], back_populates="children")
    children: Mapped[List["AllocationNode"]] = relationship("AllocationNode", back_populates="parent", cascade="all, delete-orphan", passive_deletes=True)
    feeder_assignments: Mapped[List["FeederAssignment"]] = relationship("FeederAssignment", back_populates="node", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("order_id", "slot_id", "level", "entity_id", name="uq_allocation_node_entity"),
    )


class FeederAssignment(Base):
    __tablename__ = "feeder_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("allocation_node.id", ondelete="CASCADE"))
    feeder_id: Mapped[str] = mapped_column(ForeignKey("feeder.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("deficit_slot.id", ondelete="CASCADE"))
    
    assigned_mw: Mapped[float] = mapped_column(Float, default=0.0)
    fairness_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    assigned_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    node: Mapped["AllocationNode"] = relationship("AllocationNode", back_populates="feeder_assignments")
    feeder: Mapped["Feeder"] = relationship("Feeder")
    slot: Mapped["DeficitSlot"] = relationship("DeficitSlot")

    __table_args__ = (
        UniqueConstraint("node_id", "feeder_id", name="uq_feeder_assignment_node"),
        UniqueConstraint("slot_id", "feeder_id", name="uq_feeder_assignment_slot"),
    )
