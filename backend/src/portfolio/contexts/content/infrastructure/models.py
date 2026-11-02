from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from portfolio.platform.db import Base


class EntryRow(Base):
    __tablename__ = "content_entries"
    __table_args__ = (
        UniqueConstraint("kind", "slug"),
        # At most one profile, enforced by the database too, not only by the use case.
        Index(
            "uq_content_entries_singleton",
            "kind",
            unique=True,
            postgresql_where=text("kind = 'profile'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(10), index=True)
    version: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(JSONB)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    translations: Mapped[list["TranslationRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TranslationRow.lang"
    )
    skills: Mapped[list["EntrySkillRow"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="EntrySkillRow.entry_id",
        order_by="EntrySkillRow.position",
    )
    attachments: Mapped[list["AttachmentRow"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="AttachmentRow.position"
    )


class TranslationRow(Base):
    __tablename__ = "content_translations"

    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_entries.id", ondelete="CASCADE"), primary_key=True
    )
    lang: Mapped[str] = mapped_column(String(2), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)


class EntrySkillRow(Base):
    __tablename__ = "content_entry_skills"

    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_entries.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_entries.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer)


class AttachmentRow(Base):
    __tablename__ = "content_attachments"

    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_entries.id", ondelete="CASCADE"), primary_key=True
    )
    # RESTRICT: a file cannot be deleted while an entry offers it for download.
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("files_objects.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
