"""M4+M5: shed orders and allocations

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    orderstatus = postgresql.ENUM("DRAFT", "ALLOCATED", "VALIDATED", "ACTIVE", "COMPLETED", "CANCELLED", name="orderstatus", create_type=True)
    orderstatus.create(op.get_bind(), checkfirst=True)

    allocationlevel = postgresql.ENUM("NATIONAL", "CRC", "BCC", name="allocationlevel", create_type=True)
    allocationlevel.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "shed_order",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("deficit_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("DRAFT", "ALLOCATED", "VALIDATED", "ACTIVE", "COMPLETED", "CANCELLED", name="orderstatus", create_type=False),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("total_deficit_mw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("plan_id", name="uq_shed_order_plan_id"),
    )

    op.create_table(
        "allocation_node",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("shed_order.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("deficit_slot.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("allocation_node.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "level",
            postgresql.ENUM("NATIONAL", "CRC", "BCC", name="allocationlevel", create_type=False),
            nullable=False,
        ),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("target_mw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("achieved_mw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("shortfall_mw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("order_id", "slot_id", "level", "entity_id", name="uq_allocation_node_entity"),
    )
    op.create_index("ix_allocation_node_order_id", "allocation_node", ["order_id"])
    op.create_index("ix_allocation_node_slot_id", "allocation_node", ["slot_id"])
    op.create_index("ix_allocation_node_parent_id", "allocation_node", ["parent_id"])

    op.create_table(
        "feeder_assignment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("allocation_node.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feeder_id", sa.String(), sa.ForeignKey("feeder.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("deficit_slot.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_mw", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fairness_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("node_id", "feeder_id", name="uq_feeder_assignment_node"),
        sa.UniqueConstraint("slot_id", "feeder_id", name="uq_feeder_assignment_slot"),
    )
    op.create_index("ix_feeder_assignment_node_id", "feeder_assignment", ["node_id"])
    op.create_index("ix_feeder_assignment_feeder_id", "feeder_assignment", ["feeder_id"])
    op.create_index("ix_feeder_assignment_slot_id", "feeder_assignment", ["slot_id"])

def downgrade() -> None:
    op.drop_index("ix_feeder_assignment_slot_id", table_name="feeder_assignment")
    op.drop_index("ix_feeder_assignment_feeder_id", table_name="feeder_assignment")
    op.drop_index("ix_feeder_assignment_node_id", table_name="feeder_assignment")
    op.drop_table("feeder_assignment")

    op.drop_index("ix_allocation_node_parent_id", table_name="allocation_node")
    op.drop_index("ix_allocation_node_slot_id", table_name="allocation_node")
    op.drop_index("ix_allocation_node_order_id", table_name="allocation_node")
    op.drop_table("allocation_node")

    op.drop_table("shed_order")

    sa.Enum(name="allocationlevel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="orderstatus").drop(op.get_bind(), checkfirst=True)
