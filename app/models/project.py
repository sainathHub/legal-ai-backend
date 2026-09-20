import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.thread import Thread


class Project(Base):
    """
    Projects (Cases) table.
    A lawyer works on multiple cases. Each case gets its own project.
    Matches schema:
    - id UUID PRIMARY KEY DEFAULT gen_random_uuid()
    - user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
    - title VARCHAR(255) NOT NULL
    - description TEXT
    - created_at / updated_at TIMESTAMP WITH TIME ZONE
    - INDEX idx_projects_user_id ON projects(user_id)
    """
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # Corresponds to idx_projects_user_id
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
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
    user: Mapped["User"] = relationship(
        "User",
        back_populates="projects",
    )
    threads: Mapped[List["Thread"]] = relationship(
        "Thread",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} title={self.title} user_id={self.user_id}>"
