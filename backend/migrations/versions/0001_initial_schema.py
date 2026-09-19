"""Initial schema - M1: hierarchy tables, feeder history, parameters

Revision ID: 0001
Revises: 
Create Date: 2026-09-19

Tables created (in dependency order):
  crc -> bcc -> substation -> feeder -> feeder_history
  parameters
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # PostgreSQL native ENUM types
    # ------------------------------------------------------------------
    priority_level = postgresql.ENUM(
        "P0", "P1", "P2", "P3", "P4", "P5",
        name="prioritylevel",
        create_type=True,
    )
    feeder_status = postgresql.ENUM(
        "CLOSED", "OPEN", "MAINTENANCE", "UNAVAILABLE",
        name="feederstatus",
        create_type=True,
    )
    priority_level.create(op.get_bind(), checkfirst=True)
    feeder_status.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # crc
    # ------------------------------------------------------------------
    op.create_table(
        "crc",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("share_key", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "share_key > 0 AND share_key < 1",
            name="ck_crc_share_key_range",
        ),
    )

    # ------------------------------------------------------------------
    # bcc
    # ------------------------------------------------------------------
    op.create_table(
        "bcc",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "crc_id",
            sa.String(20),
            sa.ForeignKey("crc.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("managed_load_mw", sa.Float(), nullable=False),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.CheckConstraint("managed_load_mw > 0", name="ck_bcc_managed_load_positive"),
        sa.CheckConstraint("area_km2 > 0", name="ck_bcc_area_positive"),
    )
    op.create_index("ix_bcc_crc_id", "bcc", ["crc_id"])

    # ------------------------------------------------------------------
    # substation
    # ------------------------------------------------------------------
    op.create_table(
        "substation",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "bcc_id",
            sa.String(20),
            sa.ForeignKey("bcc.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_substation_bcc_id", "substation", ["bcc_id"])

    # ------------------------------------------------------------------
    # feeder
    # ------------------------------------------------------------------
    op.create_table(
        "feeder",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "substation_id",
            sa.String(20),
            sa.ForeignKey("substation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalized FK to bcc for fast per-BCC queries
        sa.Column(
            "bcc_id",
            sa.String(20),
            sa.ForeignKey("bcc.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("P0", "P1", "P2", "P3", "P4", "P5", name="prioritylevel", create_type=False),
            nullable=False,
            server_default="P3",
        ),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("avg_mw", sa.Float(), nullable=False),
        sa.Column("zone_id", sa.String(30), nullable=False),
        sa.Column(
            "status",
            sa.Enum("CLOSED", "OPEN", "MAINTENANCE", "UNAVAILABLE", name="feederstatus", create_type=False),
            nullable=False,
            server_default="CLOSED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("avg_mw > 0", name="ck_feeder_avg_mw_positive"),
    )
    op.create_index("ix_feeder_bcc_id", "feeder", ["bcc_id"])
    op.create_index("ix_feeder_priority", "feeder", ["priority"])
    op.create_index("ix_feeder_status", "feeder", ["status"])
    op.create_index("ix_feeder_zone_id", "feeder", ["zone_id"])

    # ------------------------------------------------------------------
    # feeder_history  (one row per feeder, 1-to-1)
    # ------------------------------------------------------------------
    op.create_table(
        "feeder_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "feeder_id",
            sa.String(20),
            sa.ForeignKey("feeder.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "cumulative_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("rotations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_shed_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_shed_end", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "cumulative_minutes >= 0",
            name="ck_fh_cum_minutes_non_negative",
        ),
        sa.CheckConstraint("rotations >= 0", name="ck_fh_rotations_non_negative"),
    )
    op.create_index("ix_feeder_history_feeder_id", "feeder_history", ["feeder_id"])

    # ------------------------------------------------------------------
    # parameters  (single-row configuration table)
    # ------------------------------------------------------------------
    op.create_table(
        "parameters",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("max_duration_min", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("rest_time_min", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("slot_size_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("rotation_warn_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column(
            "regional_key",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default='{"CRC_N": 0.67, "CRC_S": 0.33}',
        ),
    )


def downgrade() -> None:
    op.drop_table("parameters")
    op.drop_index("ix_feeder_history_feeder_id", table_name="feeder_history")
    op.drop_table("feeder_history")
    op.drop_index("ix_feeder_zone_id", table_name="feeder")
    op.drop_index("ix_feeder_status", table_name="feeder")
    op.drop_index("ix_feeder_priority", table_name="feeder")
    op.drop_index("ix_feeder_bcc_id", table_name="feeder")
    op.drop_table("feeder")
    op.drop_index("ix_substation_bcc_id", table_name="substation")
    op.drop_table("substation")
    op.drop_index("ix_bcc_crc_id", table_name="bcc")
    op.drop_table("bcc")
    op.drop_table("crc")

    # Drop PostgreSQL enum types
    sa.Enum(name="feederstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="prioritylevel").drop(op.get_bind(), checkfirst=True)
