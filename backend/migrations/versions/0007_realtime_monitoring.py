"""M6: real-time monitoring and shed events (UC4)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    eventstatus = postgresql.ENUM("OPEN", "CLOSED", "OVER_LIMIT", name="eventstatus", create_type=True)
    eventstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "shed_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("feeder_id", sa.String(length=20), nullable=False),
        sa.Column("bcc_id", sa.String(length=20), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mw_before", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mw_actual", sa.Float(), nullable=False),
        sa.Column("duration_min", sa.Float(), nullable=True),
        sa.Column("ens_mwh", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("OPEN", "CLOSED", "OVER_LIMIT", name="eventstatus", create_type=False),
            nullable=False,
            server_default="OPEN",
        ),
        sa.CheckConstraint("mw_actual > 0", name="ck_shed_event_mw_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["shed_order.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feeder_id"], ["feeder.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bcc_id"], ["bcc.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_shed_event_order_status", "shed_event", ["order_id", "status"])
    op.create_index("ix_shed_event_bcc_status", "shed_event", ["bcc_id", "status"])

    # Create view for national real-time metrics
    op.execute("""
    CREATE OR REPLACE VIEW v_national_monitoring AS
    SELECT 
        COALESCE(SUM(se.mw_actual), 0.0) AS total_actual_mw,
        COUNT(se.id) AS open_feeders_count,
        COUNT(DISTINCT se.bcc_id) AS active_bccs_count,
        COALESCE(MAX(EXTRACT(EPOCH FROM (NOW() - se.open_time)) / 60.0), 0.0) AS max_duration_min,
        COALESCE(SUM(se.ens_mwh), 0.0) AS total_ens_mwh
    FROM shed_event se
    WHERE se.status = 'OPEN';
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_national_monitoring;")
    op.drop_index("ix_shed_event_bcc_status", table_name="shed_event")
    op.drop_index("ix_shed_event_order_status", table_name="shed_event")
    op.drop_table("shed_event")
    op.execute("DROP TYPE IF EXISTS eventstatus;")
