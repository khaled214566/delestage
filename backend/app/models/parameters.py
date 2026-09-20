from sqlalchemy import JSON, CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Parameters(Base):
    """System-wide configuration parameters. Single-row table (id is always 1)."""
    __tablename__ = "parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    rest_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    slot_size_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    rotation_warn_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    regional_key: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: {"CRC_N": 0.67, "CRC_S": 0.33}
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_parameters_singleton"),
        CheckConstraint("max_duration_min > 0", name="ck_parameters_max_duration_positive"),
        CheckConstraint("rest_time_min >= 0", name="ck_parameters_rest_time_non_negative"),
        CheckConstraint("slot_size_min IN (15, 30)", name="ck_parameters_slot_size"),
        CheckConstraint("rotation_warn_pct BETWEEN 1 AND 100", name="ck_parameters_warn_pct_range"),
    )
