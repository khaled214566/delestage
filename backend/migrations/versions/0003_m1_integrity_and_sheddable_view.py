"""M1: integrity constraints and the v_sheddable_feeders view

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20

What this migration does:
  1. parameters: single-row guarantee (id = 1) and range checks, so that a bad
     value is refused by the database even if an API validation is forgotten.
  2. feeder: a P0 feeder must be flagged critical.
  3. feeder.bcc_id is denormalised for fast per-BCC queries. A composite foreign
     key (substation_id, bcc_id) -> substation(id, bcc_id) now makes it
     impossible for it to disagree with the substation's BCC.
  4. feeder_history: last_shed_end cannot precede last_shed_start.
  5. Drops a redundant index (the UNIQUE constraint on feeder_id already indexes it).
  6. Creates the view v_sheddable_feeders (the seed used to create it, which meant
     it did not exist after `alembic upgrade head`).
"""
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

# OPEN feeders are deliberately included: they are being shed right now but are
# still part of the sheddable capacity (M4 compares an order's target to
# SUM(avg_mw) of this view). Whether a feeder may be shed *again* is decided by
# the rules engine (M5), not by this view.
VIEW_SQL = """
CREATE OR REPLACE VIEW v_sheddable_feeders AS
SELECT f.id,
       f.name,
       f.substation_id,
       f.bcc_id,
       f.zone_id,
       f.priority,
       f.avg_mw,
       f.status,
       fh.cumulative_minutes,
       fh.rotations,
       fh.last_shed_start,
       fh.last_shed_end
FROM feeder f
JOIN feeder_history fh ON fh.feeder_id = f.id
WHERE f.priority <> 'P0'
  AND NOT f.critical
  AND f.status NOT IN ('MAINTENANCE', 'UNAVAILABLE')
"""


def upgrade() -> None:
    # 1. parameters
    op.create_check_constraint("ck_parameters_singleton", "parameters", "id = 1")
    op.create_check_constraint("ck_parameters_max_duration_positive", "parameters", "max_duration_min > 0")
    op.create_check_constraint("ck_parameters_rest_time_non_negative", "parameters", "rest_time_min >= 0")
    op.create_check_constraint("ck_parameters_slot_size", "parameters", "slot_size_min IN (15, 30)")
    op.create_check_constraint("ck_parameters_warn_pct_range", "parameters", "rotation_warn_pct BETWEEN 1 AND 100")

    # 2. P0 => critical
    op.create_check_constraint("ck_feeder_p0_is_critical", "feeder", "priority <> 'P0' OR critical")

    # 3. feeder.bcc_id must match its substation's bcc_id.
    #    The composite FK replaces the single-column FK on substation_id.
    op.create_unique_constraint("uq_substation_id_bcc_id", "substation", ["id", "bcc_id"])
    op.drop_constraint("feeder_substation_id_fkey", "feeder", type_="foreignkey")
    op.create_foreign_key(
        "fk_feeder_substation_bcc", "feeder", "substation",
        ["substation_id", "bcc_id"], ["id", "bcc_id"], ondelete="CASCADE",
    )

    # 4. feeder_history window ordering
    op.create_check_constraint(
        "ck_fh_shed_window_ordered", "feeder_history",
        "last_shed_start IS NULL OR last_shed_end IS NULL OR last_shed_end >= last_shed_start",
    )

    # 5. redundant index
    op.drop_index("ix_feeder_history_feeder_id", table_name="feeder_history")

    # 6. view
    op.execute(VIEW_SQL)
    op.execute("COMMENT ON VIEW v_sheddable_feeders IS "
               "'Feeders that may ever be shed: not P0, not critical, not MAINTENANCE/UNAVAILABLE. Includes OPEN ones.'")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_sheddable_feeders")

    op.create_index("ix_feeder_history_feeder_id", "feeder_history", ["feeder_id"])
    op.drop_constraint("ck_fh_shed_window_ordered", "feeder_history", type_="check")

    op.drop_constraint("fk_feeder_substation_bcc", "feeder", type_="foreignkey")
    op.create_foreign_key(
        "feeder_substation_id_fkey", "feeder", "substation",
        ["substation_id"], ["id"], ondelete="CASCADE",
    )
    op.drop_constraint("uq_substation_id_bcc_id", "substation", type_="unique")

    op.drop_constraint("ck_feeder_p0_is_critical", "feeder", type_="check")

    op.drop_constraint("ck_parameters_warn_pct_range", "parameters", type_="check")
    op.drop_constraint("ck_parameters_slot_size", "parameters", type_="check")
    op.drop_constraint("ck_parameters_rest_time_non_negative", "parameters", type_="check")
    op.drop_constraint("ck_parameters_max_duration_positive", "parameters", type_="check")
    op.drop_constraint("ck_parameters_singleton", "parameters", type_="check")
