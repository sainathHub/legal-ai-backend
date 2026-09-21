import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.vector import VectorSearchResultItem


class LegalRAGRequest(BaseModel):
    """Request payload for Indian Legal Precedent Retrieval & LLM Advisory Opinion."""

    query: str = Field(
        ...,
        min_length=2,
        description="Legal question, case facts, or statutory inquiry (e.g. 'Bail under Section 438 CrPC')",
    )
    limit: int = Field(
        4,
        ge=1,
        le=20,
        description="Number of precedent chunks to retrieve (default: 4)",
    )
    case_type: Optional[str] = Field(
        None,
        description="Optional filter by case category (e.g. 'Criminal', 'Constitutional', 'Civil')",
    )
    min_year: int = Field(
        0,
        ge=0,
        le=2100,
        description="Optional filter for judgments delivered on or after this year (0 = all years)",
    )
    search_mode: str = Field(
        "hybrid",
        description="Retrieval strategy: 'hybrid' (vector + keyword), 'vector' (semantic near-vector), or 'bm25' (keyword)",
    )
    model: Optional[str] = Field(
        None,
        description="Groq LLM model name (defaults to GROQ_DEFAULT_MODEL in server config)",
    )
    max_tokens: int = Field(
        850,
        ge=100,
        le=4096,
        description="Maximum generation tokens (default: 850, optimizes response latency & rate limits)",
    )
    thread_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional ID of the chat thread to link this consultation to",
    )


class LegalRAGResponse(BaseModel):
    """Response payload containing generated legal opinion and cited precedents."""

    query: str
    answer: str = Field(..., description="Structured judicial advisory opinion formatted by the LLM")
    model_used: str = Field(..., description="Groq LLM model used for synthesis")
    precedents_count: int = Field(..., description="Number of precedent citations retrieved")
    precedents: List[VectorSearchResultItem] = Field(
        default_factory=list,
        description="List of landmark Indian case precedents retrieved from Weaviate Cloud",
    )
    search_mode_used: str = Field(..., description="Actual retrieval mode employed (e.g., 'hybrid', 'bm25')")
    standalone_query: Optional[str] = Field(
        None,
        description="Standalone legal search query synthesized from conversation history by LangChain",
    )
    execution_time_ms: float = Field(..., description="Total pipeline latency in milliseconds")
