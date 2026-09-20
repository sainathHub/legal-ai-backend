import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.thread import ThreadRead


class ProjectBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Case / project title (e.g., 'State vs. Reliance')")
    description: Optional[str] = Field(None, description="Detailed case notes, background, or brief")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ProjectRead(ProjectBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectDetail(ProjectRead):
    threads: List[ThreadRead] = Field(default_factory=list, description="All chat sessions belonging to this case project")
