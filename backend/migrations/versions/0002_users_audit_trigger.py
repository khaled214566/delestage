"""M2: users table, audit_log table, immutability trigger, default accounts

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19

What this migration does:
  1. Creates the 'userrole' PostgreSQL ENUM type.
  2. Creates the 'users' table.
  3. Creates the 'audit_log' table (BigInteger seq, hash-chained columns).
  4. Creates trigger function + trigger that blocks UPDATE and DELETE on
     audit_log at the database level — tamper-proof by design.
  5. Inserts 4 default demo accounts (password: delestage123).

Demo accounts inserted:
  admin   / delestage123  → ADMIN,        national
  ahmed   / delestage123  → DISPATCHER,   national
  crc_n   / delestage123  → CRC_OPERATOR, CRC_N
  sana    / delestage123  → BCC_OPERATOR, BCC1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

DEMO_PASSWORD = "delestage123"  # demo accounts only; change before any real deployment


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. PostgreSQL ENUM for user roles
    # ------------------------------------------------------------------
    userrole_enum = postgresql.ENUM(
        "DISPATCHER", "CRC_OPERATOR", "BCC_OPERATOR", "ADMIN",
        name="userrole",
        create_type=True,
    )
    userrole_enum.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. users table
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "DISPATCHER", "CRC_OPERATOR", "BCC_OPERATOR", "ADMIN",
                name="userrole",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(20), nullable=False, server_default="national"),
        sa.Column("scope_id", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_role", "users", ["role"])

    # ------------------------------------------------------------------
    # 3. audit_log table
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_id", sa.String(20), nullable=False),
        sa.Column("actor_name", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(50), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])

    # ------------------------------------------------------------------
    # 4. Immutability trigger: block UPDATE and DELETE on audit_log
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_immutable()
        RETURNS trigger
        LANGUAGE plpgsql AS
        $$
        BEGIN
            RAISE EXCEPTION
                'audit_log is append-only. Operation % on seq=% is forbidden.',
                TG_OP,
                COALESCE(OLD.seq::text, '?');
        END;
        $$;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_log_immutable
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW
        EXECUTE FUNCTION audit_log_immutable();
    """)

    # ------------------------------------------------------------------
    # 5. Default demo accounts (password: delestage123)
    #    The argon2id hash is computed here rather than hard-coded, so it is
    #    guaranteed to verify with the same passlib settings the API uses.
    # ------------------------------------------------------------------
    from passlib.context import CryptContext

    demo_hash = CryptContext(schemes=["argon2"], deprecated="auto").hash(DEMO_PASSWORD)
    users = sa.table(
        "users",
        sa.column("username", sa.String),
        sa.column("name", sa.String),
        sa.column("hashed_password", sa.String),
        sa.column("role", postgresql.ENUM(name="userrole", create_type=False)),
        sa.column("scope_type", sa.String),
        sa.column("scope_id", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    demo_accounts = [
        {"username": "admin", "name": "Administrator",   "role": "ADMIN",        "scope_type": "national", "scope_id": None},
        {"username": "ahmed", "name": "Ahmed B.",        "role": "DISPATCHER",   "scope_type": "national", "scope_id": None},
        {"username": "crc_n", "name": "Operateur CRC N", "role": "CRC_OPERATOR", "scope_type": "crc",      "scope_id": "CRC_N"},
        {"username": "sana",  "name": "Sana M.",         "role": "BCC_OPERATOR", "scope_type": "bcc",      "scope_id": "BCC1"},
    ]
    op.bulk_insert(users, [{**acct, "hashed_password": demo_hash, "is_active": True} for acct in demo_accounts])


def downgrade() -> None:
    # Drop trigger and function first
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable();")

    # Drop tables
    op.drop_index("ix_audit_log_entity_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    # Drop ENUM type
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
