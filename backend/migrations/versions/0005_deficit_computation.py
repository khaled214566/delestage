"""M3: deficit computation (UC1) — deficit_plan, deficit_slot, deficit_revision

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20

mode reuses the existing 'ordertype' enum (J-1 / REAL_TIME) created in 0001 —
same concept as a shed order's type, so no new enum type for it here.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    # 'ordertype' exists as a Python enum (app.models.enums.OrderType) since
    # 0001, but no migration has ever created the matching Postgres type —
    # ShedOrder (M4) doesn't exist yet, so deficit_plan.mode is its first
    # real consumer. checkfirst=True so a future M4 migration reusing this
    # same type for shed_order.type stays safe either way.
    ordertype = postgresql.ENUM("J-1", "REAL_TIME", name="ordertype", create_type=True)
    ordertype.create(op.get_bind(), checkfirst=True)

    deficitplanstatus = postgresql.ENUM(
        "DRAFT", "VALIDATED", name="deficitplanstatus", create_type=True,
    )
    deficitplanstatus.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # deficit_plan
    # ------------------------------------------------------------------
    op.create_table(
        "deficit_plan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM("J-1", "REAL_TIME", name="ordertype", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("DRAFT", "VALIDATED", name="deficitplanstatus", create_type=False),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("date", "mode", name="uq_deficit_plan_date_mode"),
    )

    # ------------------------------------------------------------------
    # deficit_slot
    # ------------------------------------------------------------------
    op.create_table(
        "deficit_slot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id", sa.Integer(), sa.ForeignKey("deficit_plan.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("demand_mw", sa.Float(), nullable=False),
        sa.Column("generation_mw", sa.Float(), nullable=False),
        sa.Column("imports_mw", sa.Float(), nullable=False),
        sa.Column("margin_mw", sa.Float(), nullable=False),
        sa.Column("deficit_mw", sa.Float(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("plan_id", "slot_start", name="uq_deficit_slot_plan_start"),
        sa.CheckConstraint("slot_end > slot_start", name="ck_deficit_slot_window_ordered"),
        sa.CheckConstraint("demand_mw >= 0", name="ck_deficit_slot_demand_non_negative"),
        sa.CheckConstraint("generation_mw >= 0", name="ck_deficit_slot_generation_non_negative"),
        sa.CheckConstraint("imports_mw >= 0", name="ck_deficit_slot_imports_non_negative"),
        sa.CheckConstraint("margin_mw >= 0", name="ck_deficit_slot_margin_non_negative"),
        sa.CheckConstraint("deficit_mw >= 0", name="ck_deficit_slot_deficit_floored_at_zero"),
    )
    op.create_index("ix_deficit_slot_plan_id", "deficit_slot", ["plan_id"])

    # ------------------------------------------------------------------
    # deficit_revision
    # ------------------------------------------------------------------
    op.create_table(
        "deficit_revision",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "slot_id", sa.Integer(), sa.ForeignKey("deficit_slot.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("old_values", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("new_values", postgresql.JSON(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_deficit_revision_slot_id", "deficit_revision", ["slot_id"])


def downgrade() -> None:
    op.drop_index("ix_deficit_revision_slot_id", table_name="deficit_revision")
    op.drop_table("deficit_revision")

    op.drop_index("ix_deficit_slot_plan_id", table_name="deficit_slot")
    op.drop_table("deficit_slot")

    op.drop_table("deficit_plan")

    sa.Enum(name="deficitplanstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="ordertype").drop(op.get_bind(), checkfirst=True)
