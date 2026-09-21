import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.message import Message


class Thread(Base):
    """
    Threads (Chat Sessions) table.
    A single case might have one thread for 'Drafting Bail' and another for 'Cross-Exam Prep'.
    Matches schema:
    - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    - project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE
    - title VARCHAR(255) NOT NULL
    - created_at / updated_at TIMESTAMP WITH TIME ZONE
    - INDEX idx_threads_project_id ON threads(project_id)
    """
    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Corresponds to idx_threads_project_id
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="threads",
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<Thread id={self.id} title={self.title} project_id={self.project_id}>"
