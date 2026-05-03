"""Wiki document ORM models."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from codeask.db.base import Base, TimestampMixin


class WikiDocument(Base, TimestampMixin):
    __tablename__ = "wiki_documents"
    __table_args__ = (
        Index("ix_wiki_documents_node_id", "node_id", unique=True),
        Index("ix_wiki_documents_legacy_document_id", "legacy_document_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_nodes.id", ondelete="CASCADE"), nullable=False
    )
    legacy_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    broken_refs_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    provenance_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)


class WikiDocumentVersion(Base, TimestampMixin):
    __tablename__ = "wiki_document_versions"
    __table_args__ = (
        Index(
            "ix_wiki_document_versions_doc_version",
            "document_id",
            "version_no",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_subject_id: Mapped[str] = mapped_column(String(128), nullable=False)


class WikiDocumentDraft(Base, TimestampMixin):
    __tablename__ = "wiki_document_drafts"
    __table_args__ = (
        Index(
            "ix_wiki_document_drafts_doc_subject",
            "document_id",
            "subject_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("wiki_documents.id", ondelete="CASCADE"), nullable=False
    )
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
