import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock, patch

from app.schemas.rag import LegalRAGRequest, LegalRAGResponse
from app.schemas.vector import VectorSearchResultItem
from app.services.rag_service import legal_rag_service


def test_rag_schemas():
    """Verify LegalRAGRequest and LegalRAGResponse schema validations."""
    req = LegalRAGRequest(
        query="Anticipatory bail under Section 438 CrPC",
        limit=5,
        min_year=2000,
        search_mode="hybrid",
    )
    assert req.query == "Anticipatory bail under Section 438 CrPC"
    assert req.limit == 5
    assert req.min_year == 2000
    assert req.search_mode == "hybrid"

    item = VectorSearchResultItem(
        id="test-uuid-1",
        title="State of Haryana vs Bhajan Lal",
        content="Guidelines for quashing criminal FIR...",
        metadata={"court_name": "Supreme Court of India", "year": 1992},
        score=0.92,
    )

    resp = LegalRAGResponse(
        query=req.query,
        answer="The Supreme Court held that anticipatory bail...",
        model_used="qwen/qwen3.8-27b",
        precedents_count=1,
        precedents=[item],
        search_mode_used="hybrid",
        execution_time_ms=123.45,
    )
    assert resp.precedents_count == 1
    assert resp.precedents[0].title == "State of Haryana vs Bhajan Lal"
    assert resp.execution_time_ms == 123.45


def test_rag_format_context_block():
    """Verify formatting of retrieved precedents into LLM context."""
    precedents = [
        VectorSearchResultItem(
            id="1",
            title="Kesavananda Bharati v. State of Kerala",
            content="Basic structure doctrine holds that...",
            metadata={
                "court_name": "Supreme Court of India",
                "year": 1973,
                "case_type": "Constitutional",
                "influence_score": 100,
                "source_url": "https://indiankanoon.org/doc/257876/",
            },
        )
    ]
    block = legal_rag_service.format_context_block(precedents)
    assert "Kesavananda Bharati" in block
    assert "Supreme Court of India" in block
    assert "Basic structure doctrine" in block
    assert "1973" in block


@pytest.mark.asyncio
async def test_rag_requires_authentication(client: AsyncClient):
    """Verify that RAG endpoints strictly reject unauthenticated calls with 401."""
    payload = {"query": "Bail principles under PMLA"}
    
    # Query endpoint
    query_res = await client.post("/api/v1/rag/query", json=payload)
    assert query_res.status_code == 401

    # Stream endpoint
    stream_res = await client.post("/api/v1/rag/stream", json=payload)
    assert stream_res.status_code == 401

    # Models endpoint
    models_res = await client.get("/api/v1/rag/models")
    assert models_res.status_code == 401


@pytest.mark.asyncio
async def test_rag_models_endpoint_authenticated(client: AsyncClient):
    """Verify /api/v1/rag/models returns default model and list when authenticated."""
    # Register & login
    email = "advocate.rag@example.com"
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Advocate Legal RAG"},
    )
    login_res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get("/api/v1/rag/models", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "default_model" in data
    assert "supported_models" in data
    assert "qwen/qwen3.8-27b" in data["supported_models"]


@pytest.mark.asyncio
async def test_rag_query_endpoint_mocked(client: AsyncClient):
    """Test RAG query endpoint with authenticated user and mocked service response."""
    email = "advocate.query@example.com"
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Advocate Query Test"},
    )
    login_res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    mock_response = LegalRAGResponse(
        query="Article 21 privacy rights",
        answer="### Direct Legal Opinion\nPrivacy is a fundamental right under Article 21.",
        model_used="qwen/qwen3.8-27b",
        precedents_count=1,
        precedents=[
            VectorSearchResultItem(
                id="prec-1",
                title="K.S. Puttaswamy vs Union of India",
                content="Right to privacy is protected as an intrinsic part of the right to life.",
                metadata={"court_name": "Supreme Court of India", "year": 2017},
            )
        ],
        search_mode_used="hybrid",
        execution_time_ms=85.0,
    )

    with patch.object(legal_rag_service, "execute_rag", return_value=mock_response):
        res = await client.post(
            "/api/v1/rag/query",
            json={"query": "Article 21 privacy rights", "limit": 1},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "Article 21 privacy rights"
        assert "Puttaswamy" in data["precedents"][0]["title"]
        assert "Direct Legal Opinion" in data["answer"]
