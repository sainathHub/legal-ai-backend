import logging
from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.rag import LegalRAGRequest, LegalRAGResponse
from app.services.rag_service import legal_rag_service

logger = logging.getLogger("legal_ai.api.rag")

router = APIRouter()


@router.post("/query", response_model=LegalRAGResponse)
async def query_legal_rag(
    req: LegalRAGRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LegalRAGResponse:
    """
    Execute Indian Legal Precedent Retrieval & LLM Advisory Opinion.
    
    1. Scans Weaviate Cloud LegalChunk collection (22,500+ Indian court precedents).
    2. Ranks precedents using hybrid / semantic / keyword vector scoring.
    3. Synthesizes an authoritative legal opinion via Groq LLM (Qwen 3.8-27B).
    """
    try:
        return legal_rag_service.execute_rag(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error executing Legal RAG query: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process legal inquiry: {str(e)}",
        )


@router.post("/stream")
async def stream_legal_rag(
    req: LegalRAGRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """
    Stream Indian Legal RAG opinion tokens via Server-Sent Events (SSE).
    
    Yields:
    - event: precedents (retrieved case citations & metadata)
    - event: token (generated opinion chunks)
    - event: done (completion stats)
    """
    return StreamingResponse(
        legal_rag_service.stream_rag_opinion(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
async def get_rag_model_info(
    _: Annotated[User, Depends(get_current_active_user)],
) -> Dict[str, Any]:
    """
    Get configured Groq LLM model and recommended alternatives.
    """
    return {
        "default_model": settings.GROQ_DEFAULT_MODEL,
        "supported_models": [
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ],
        "groq_configured": bool(settings.GROQ_API_KEY),
    }
