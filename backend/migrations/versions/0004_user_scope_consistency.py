"""M2 hardening: role/scope_type/scope_id must agree

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20

Without this, nothing stops inserting e.g. a BCC_OPERATOR with
scope_type='national' and scope_id=NULL. Today that fails closed
(check_bcc_scope locks them out of everything) rather than granting
excess access, but it's a silent misconfiguration with no constraint
catching it at write time — this closes that gap at the database level,
independent of whatever validation M9's admin screen ends up doing.

The four existing demo accounts (admin, ahmed, crc_n, sana) already
satisfy this, so applying it is non-destructive.
"""
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

CONSTRAINT_SQL = """
    (role IN ('DISPATCHER', 'ADMIN') AND scope_type = 'national' AND scope_id IS NULL)
    OR (role = 'CRC_OPERATOR' AND scope_type = 'crc' AND scope_id IS NOT NULL)
    OR (role = 'BCC_OPERATOR' AND scope_type = 'bcc' AND scope_id IS NOT NULL)
"""


def upgrade() -> None:
    op.create_check_constraint("ck_users_scope_matches_role", "users", CONSTRAINT_SQL)


def downgrade() -> None:
    op.drop_constraint("ck_users_scope_matches_role", "users", type_="check")