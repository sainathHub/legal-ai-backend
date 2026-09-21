import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.thread import Thread


class Message(Base):
    """
    Messages table.
    Stores individual conversation turns (User queries & Assistant answers) within a thread,
    including cited legal precedents in the sources JSON column.
    """
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    sources: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=False,
    )
    tokens_used: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    thread: Mapped["Thread"] = relationship(
        "Thread",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} thread_id={self.thread_id} role={self.role}>"
