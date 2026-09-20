import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ThreadBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Thread title (e.g., 'Bail Application Draft')")


class ThreadCreate(ThreadBase):
    pass


class ThreadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)


class ThreadRead(ThreadBase):
    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
