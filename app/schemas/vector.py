from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DocumentChunkCreate(BaseModel):
    doc_id: str = Field(..., description="Unique ID of the parent document")
    chunk_index: int = Field(0, description="Sequential index of the chunk")
    title: Optional[str] = Field(None, description="Document title or section heading")
    content: str = Field(..., min_length=1, description="Text body of the chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata (tags, author, jurisdiction, date)")
    vector: Optional[List[float]] = Field(None, description="Optional custom embedding vector")


class DocumentChunkResponse(BaseModel):
    id: str
    doc_id: str
    chunk_index: int
    title: Optional[str] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VectorSearchQuery(BaseModel):
    query: Optional[str] = Field(None, description="Text search query for hybrid or semantic search")
    vector: Optional[List[float]] = Field(None, description="Raw embedding vector for near-vector search")
    limit: int = Field(5, ge=1, le=100, description="Number of results to retrieve")
    alpha: float = Field(0.5, ge=0.0, le=1.0, description="Weight for hybrid search: 0 = pure BM25 keyword, 1 = pure vector")
    filter_doc_id: Optional[str] = Field(None, description="Filter results to a specific document ID")


class VectorSearchResultItem(BaseModel):
    id: str
    doc_id: Optional[str] = None
    chunk_index: Optional[int] = None
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    distance: Optional[float] = None


class VectorSearchResponse(BaseModel):
    total_results: int
    query: Optional[str] = None
    results: List[VectorSearchResultItem]
