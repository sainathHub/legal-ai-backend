import pytest
from httpx import AsyncClient
from app.schemas.vector import DocumentChunkCreate, VectorSearchQuery


@pytest.mark.asyncio
async def test_vector_status_endpoint(client: AsyncClient):
    """Test vector status endpoint when Weaviate is unconfigured/offline."""
    response = await client.get("/api/v1/vectors/status")
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "default_collection" in data
    assert data["default_collection"] == "LegalDocument"


@pytest.mark.asyncio
async def test_vector_ingestion_requires_auth(client: AsyncClient):
    """Verify that vector ingestion rejects unauthenticated calls."""
    chunk_payload = {
        "doc_id": "doc-001",
        "chunk_index": 0,
        "title": "Non-Disclosure Agreement Section 1",
        "content": "Confidential Information shall include all proprietary technical data...",
        "metadata": {"jurisdiction": "California", "year": 2026},
    }
    response = await client.post("/api/v1/vectors/chunks", json=chunk_payload)
    assert response.status_code == 401


def test_vector_schemas_validation():
    """Verify Pydantic schemas for vector ingestion and queries."""
    chunk = DocumentChunkCreate(
        doc_id="contract-123",
        chunk_index=1,
        title="Termination Clause",
        content="Either party may terminate this agreement with 30 days notice.",
        metadata={"category": "contract"},
        vector=[0.1, 0.2, 0.3],
    )
    assert chunk.doc_id == "contract-123"
    assert chunk.vector == [0.1, 0.2, 0.3]

    query = VectorSearchQuery(query="indemnity clause", limit=10, alpha=0.7)
    assert query.limit == 10
    assert query.alpha == 0.7
