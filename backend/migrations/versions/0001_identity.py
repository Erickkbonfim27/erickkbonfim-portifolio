"""identity: admin users and sessions

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_admin_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_admin_users")),
        sa.UniqueConstraint("email", name=op.f("uq_identity_admin_users_email")),
    )
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["identity_admin_users.id"],
            name=op.f("fk_identity_sessions_admin_id_identity_admin_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_identity_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_identity_sessions_admin_id"), "identity_sessions", ["admin_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_identity_sessions_admin_id"), table_name="identity_sessions")
    op.drop_table("identity_sessions")
    op.drop_table("identity_admin_users")
