from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import FeederStatus, PriorityLevel


class Crc(Base):
    __tablename__ = "crc"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "CRC_N", "CRC_S"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    share_key: Mapped[float] = mapped_column(Float, nullable=False)  # e.g. 0.67 for North

    bccs: Mapped[list["Bcc"]] = relationship(back_populates="crc", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        CheckConstraint("share_key > 0 AND share_key < 1", name="ck_crc_share_key_range"),
    )


class Bcc(Base):
    __tablename__ = "bcc"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "BCC1"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "BCC Tunis"
    crc_id: Mapped[str] = mapped_column(ForeignKey("crc.id", ondelete="CASCADE"), nullable=False, index=True)
    managed_load_mw: Mapped[float] = mapped_column(Float, nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)

    crc: Mapped["Crc"] = relationship(back_populates="bccs")
    substations: Mapped[list["Substation"]] = relationship(
        back_populates="bcc", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("managed_load_mw > 0", name="ck_bcc_managed_load_positive"),
        CheckConstraint("area_km2 > 0", name="ck_bcc_area_positive"),
    )


class Substation(Base):
    __tablename__ = "substation"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "SS-101"
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Poste Source Lac"
    bcc_id: Mapped[str] = mapped_column(ForeignKey("bcc.id", ondelete="CASCADE"), nullable=False, index=True)

    bcc: Mapped["Bcc"] = relationship(back_populates="substations")
    feeders: Mapped[list["Feeder"]] = relationship(
        back_populates="substation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # Target of the composite FK from feeder: lets the DB check feeder.bcc_id == substation.bcc_id.
        UniqueConstraint("id", "bcc_id", name="uq_substation_id_bcc_id"),
    )


class Feeder(Base):
    __tablename__ = "feeder"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # e.g. "F-125"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    substation_id: Mapped[str] = mapped_column(String(20), nullable=False)  # FK: composite, see __table_args__
    bcc_id: Mapped[str] = mapped_column(  # denormalised for fast per-BCC queries; kept honest by the composite FK
        ForeignKey("bcc.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[PriorityLevel] = mapped_column(
        Enum(PriorityLevel, name="prioritylevel"), nullable=False, default=PriorityLevel.P3, index=True
    )
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avg_mw: Mapped[float] = mapped_column(Float, nullable=False)
    zone_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # e.g. "Z-TN1251" (CSV delegation pcode)
    status: Mapped[FeederStatus] = mapped_column(
        Enum(FeederStatus, name="feederstatus"), nullable=False, default=FeederStatus.CLOSED, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    substation: Mapped["Substation"] = relationship(back_populates="feeders")
    # Read-only: writes go through substation (composite FK) or the bcc_id column.
    bcc: Mapped["Bcc"] = relationship(viewonly=True)
    history: Mapped["FeederHistory"] = relationship(
        back_populates="feeder", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["substation_id", "bcc_id"], ["substation.id", "substation.bcc_id"],
            name="fk_feeder_substation_bcc", ondelete="CASCADE",
        ),
        CheckConstraint("avg_mw > 0", name="ck_feeder_avg_mw_positive"),
        CheckConstraint("priority <> 'P0' OR critical", name="ck_feeder_p0_is_critical"),
    )


class FeederHistory(Base):
    __tablename__ = "feeder_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feeder_id: Mapped[str] = mapped_column(ForeignKey("feeder.id", ondelete="CASCADE"), nullable=False, unique=True)
    cumulative_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rotations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_shed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_shed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    feeder: Mapped["Feeder"] = relationship(back_populates="history")

    __table_args__ = (
        CheckConstraint("cumulative_minutes >= 0", name="ck_fh_cum_minutes_non_negative"),
        CheckConstraint("rotations >= 0", name="ck_fh_rotations_non_negative"),
        CheckConstraint(
            "last_shed_start IS NULL OR last_shed_end IS NULL OR last_shed_end >= last_shed_start",
            name="ck_fh_shed_window_ordered",
        ),
    )
