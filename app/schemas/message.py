import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., min_length=1, description="Body content of the message")
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Array of cited Indian legal precedents and metadata",
    )


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    id: uuid.UUID
    thread_id: uuid.UUID
    tokens_used: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
