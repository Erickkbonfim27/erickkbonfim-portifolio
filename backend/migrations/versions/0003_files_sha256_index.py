"""index files by content hash, so an identical upload reuses the stored object

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_files_objects_sha256"), "files_objects", ["sha256"])


def downgrade() -> None:
    op.drop_index(op.f("ix_files_objects_sha256"), table_name="files_objects")
