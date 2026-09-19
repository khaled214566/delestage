from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Enum, ForeignKey,
    DateTime, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone
from app.core.database import Base
from app.models.enums import PriorityLevel, FeederStatus


class Crc(Base):
    __tablename__ = "crc"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "CRC_N", "CRC_S"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    share_key: Mapped[float] = mapped_column(Float, nullable=False)  # e.g. 0.67 for North

    # Relationships
    bccs: Mapped[list["Bcc"]] = relationship(back_populates="crc", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("share_key > 0 AND share_key < 1", name="ck_crc_share_key_range"),
    )


class Bcc(Base):
    __tablename__ = "bcc"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "BCC1"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "BCC Tunis"
    crc_id: Mapped[str] = mapped_column(ForeignKey("crc.id"), nullable=False)
    managed_load_mw: Mapped[float] = mapped_column(Float, nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    crc: Mapped["Crc"] = relationship(back_populates="bccs")
    substations: Mapped[list["Substation"]] = relationship(back_populates="bcc", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("managed_load_mw > 0", name="ck_bcc_managed_load_positive"),
        CheckConstraint("area_km2 > 0", name="ck_bcc_area_positive"),
    )


class Substation(Base):
    __tablename__ = "substation"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "SS-014"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Poste Source Lac"
    bcc_id: Mapped[str] = mapped_column(ForeignKey("bcc.id"), nullable=False)

    # Relationships
    bcc: Mapped["Bcc"] = relationship(back_populates="substations")
    feeders: Mapped[list["Feeder"]] = relationship(back_populates="substation", cascade="all, delete-orphan")


class Feeder(Base):
    __tablename__ = "feeder"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "F-125"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    substation_id: Mapped[str] = mapped_column(ForeignKey("substation.id"), nullable=False)
    bcc_id: Mapped[str] = mapped_column(ForeignKey("bcc.id"), nullable=False)  # Denormalized for fast queries
    priority: Mapped[PriorityLevel] = mapped_column(Enum(PriorityLevel), nullable=False, default=PriorityLevel.P3)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avg_mw: Mapped[float] = mapped_column(Float, nullable=False)
    zone_id: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "Z-LAC-2"
    status: Mapped[FeederStatus] = mapped_column(
        Enum(FeederStatus), nullable=False, default=FeederStatus.CLOSED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    substation: Mapped["Substation"] = relationship(back_populates="feeders")
    bcc: Mapped["Bcc"] = relationship()
    history: Mapped["FeederHistory"] = relationship(
        back_populates="feeder", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("avg_mw > 0", name="ck_feeder_avg_mw_positive"),
    )


class FeederHistory(Base):
    __tablename__ = "feeder_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(
        ForeignKey("feeder.id"), nullable=False, unique=True
    )
    cumulative_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rotations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_shed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_shed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    feeder: Mapped["Feeder"] = relationship(back_populates="history")

    __table_args__ = (
        CheckConstraint("cumulative_minutes >= 0", name="ck_fh_cum_minutes_non_negative"),
        CheckConstraint("rotations >= 0", name="ck_fh_rotations_non_negative"),
    )
