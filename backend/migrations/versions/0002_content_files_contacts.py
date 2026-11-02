"""content, files, contacts and the platform tables (outbox, rate limits, job runs)

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("contact", sa.String(length=200), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("company", sa.String(length=120), nullable=True),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thanked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts_requests")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_contacts_requests_idempotency_key")),
    )
    op.create_index(
        op.f("ix_contacts_requests_created_at"), "contacts_requests", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_contacts_requests_status"), "contacts_requests", ["status"], unique=False
    )
    op.create_table(
        "content_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_entries")),
        sa.UniqueConstraint("kind", "slug", name=op.f("uq_content_entries_kind")),
    )
    op.create_index(op.f("ix_content_entries_kind"), "content_entries", ["kind"], unique=False)
    op.create_index(op.f("ix_content_entries_status"), "content_entries", ["status"], unique=False)
    op.create_index(
        "uq_content_entries_singleton",
        "content_entries",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("kind = 'profile'"),
    )
    op.create_table(
        "files_objects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files_objects")),
        sa.UniqueConstraint("key", name=op.f("uq_files_objects_key")),
    )
    op.create_table(
        "platform_job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_job_runs")),
    )
    op.create_index(op.f("ix_platform_job_runs_job"), "platform_job_runs", ["job"], unique=False)
    op.create_table(
        "platform_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_outbox")),
    )
    op.create_index(
        op.f("ix_platform_outbox_created_at"), "platform_outbox", ["created_at"], unique=False
    )
    op.create_table(
        "platform_rate_limits",
        sa.Column("bucket", sa.String(length=40), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "bucket", "key_hash", "window_start", name=op.f("pk_platform_rate_limits")
        ),
    )
    op.create_table(
        "content_attachments",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["content_entries.id"],
            name=op.f("fk_content_attachments_entry_id_content_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files_objects.id"],
            name=op.f("fk_content_attachments_file_id_files_objects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("entry_id", "file_id", name=op.f("pk_content_attachments")),
    )
    op.create_index(
        op.f("ix_content_attachments_file_id"), "content_attachments", ["file_id"], unique=False
    )
    op.create_table(
        "content_entry_skills",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["content_entries.id"],
            name=op.f("fk_content_entry_skills_entry_id_content_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["content_entries.id"],
            name=op.f("fk_content_entry_skills_skill_id_content_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id", "skill_id", name=op.f("pk_content_entry_skills")),
    )
    op.create_index(
        op.f("ix_content_entry_skills_skill_id"), "content_entry_skills", ["skill_id"], unique=False
    )
    op.create_table(
        "content_translations",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["content_entries.id"],
            name=op.f("fk_content_translations_entry_id_content_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id", "lang", name=op.f("pk_content_translations")),
    )


def downgrade() -> None:
    op.drop_table("content_translations")
    op.drop_index(op.f("ix_content_entry_skills_skill_id"), table_name="content_entry_skills")
    op.drop_table("content_entry_skills")
    op.drop_index(op.f("ix_content_attachments_file_id"), table_name="content_attachments")
    op.drop_table("content_attachments")
    op.drop_table("platform_rate_limits")
    op.drop_index(op.f("ix_platform_outbox_created_at"), table_name="platform_outbox")
    op.drop_table("platform_outbox")
    op.drop_index(op.f("ix_platform_job_runs_job"), table_name="platform_job_runs")
    op.drop_table("platform_job_runs")
    op.drop_table("files_objects")
    op.drop_index(op.f("ix_content_entries_kind"), table_name="content_entries")
    op.drop_index(op.f("ix_content_entries_status"), table_name="content_entries")
    op.drop_index(
        "uq_content_entries_singleton",
        table_name="content_entries",
        postgresql_where=sa.text("kind = 'profile'"),
    )
    op.drop_table("content_entries")
    op.drop_index(op.f("ix_contacts_requests_created_at"), table_name="contacts_requests")
    op.drop_index(op.f("ix_contacts_requests_status"), table_name="contacts_requests")
    op.drop_table("contacts_requests")
