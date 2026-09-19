from sqlalchemy import Column, String, Integer, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Parameters(Base):
    """System-wide configuration parameters. Single row table."""
    __tablename__ = "parameters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    rest_time_min: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    slot_size_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    rotation_warn_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    regional_key: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: {"CRC_N": 0.67, "CRC_S": 0.33}
    )
