from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, DateTime, ForeignKey, Enum, CheckConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EventStatus, AlarmLevel


class ShedEvent(Base):
    """
    Append-only record of a physical or simulated load shedding event.
    Tracks opening time, restoration time, instantaneous power shed, and ENS.
    """
    __tablename__ = "shed_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("shed_order.id", ondelete="CASCADE"), nullable=False)
    feeder_id: Mapped[str] = mapped_column(ForeignKey("feeder.id", ondelete="CASCADE"), nullable=False)
    bcc_id: Mapped[str] = mapped_column(ForeignKey("bcc.id", ondelete="CASCADE"), nullable=False)

    open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    mw_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mw_actual: Mapped[float] = mapped_column(Float, nullable=False)
    duration_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ens_mwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="eventstatus"), nullable=False, default=EventStatus.OPEN
    )

    # Relationships
    order = relationship("ShedOrder", backref="events")
    feeder = relationship("Feeder")
    bcc = relationship("Bcc")
    operator = relationship("User")

    __table_args__ = (
        CheckConstraint("mw_actual > 0", name="ck_shed_event_mw_positive"),
        Index("ix_shed_event_order_status", "order_id", "status"),
        Index("ix_shed_event_bcc_status", "bcc_id", "status"),
    )

    def compute_duration(self, now: Optional[datetime] = None) -> float:
        """Returns elapsed duration in minutes."""
        if self.close_time:
            return round((self.close_time - self.open_time).total_seconds() / 60.0, 1)
        ref_time = now or datetime.now(timezone.utc)
        return round(max(0.0, (ref_time - self.open_time).total_seconds() / 60.0), 1)

    def get_alarm_level(self, max_duration_min: float = 45.0, now: Optional[datetime] = None) -> AlarmLevel:
        """Calculates current alarm color: GREEN (<80%), AMBER (80-100%), RED (>100%)."""
        duration = self.compute_duration(now)
        ratio = duration / max_duration_min
        if ratio >= 1.0:
            return AlarmLevel.RED
        if ratio >= 0.8:
            return AlarmLevel.AMBER
        return AlarmLevel.GREEN
