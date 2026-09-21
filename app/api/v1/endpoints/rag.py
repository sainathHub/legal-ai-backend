import logging
from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_active_user, get_db
from app.models.project import Project
from app.models.thread import Thread
from app.models.user import User
from app.schemas.rag import LegalRAGRequest, LegalRAGResponse
from app.services.rag_service import legal_rag_service

logger = logging.getLogger("legal_ai.api.rag")

router = APIRouter()


async def _verify_thread_access(
    thread_id: Any, user_id: Any, db: AsyncSession
) -> None:
    """Ensure the chat thread exists and belongs to the authenticated user's project."""
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == user_id)
    )
    res = await db.execute(query)
    if not res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied.",
        )


@router.post("/query", response_model=LegalRAGResponse)
async def query_legal_rag(
    req: LegalRAGRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> LegalRAGResponse:
    """
    Execute Indian Legal Precedent Retrieval & LLM Advisory Opinion.
    
    1. Loads prior thread messages from PostgreSQL (if thread_id provided).
    2. Contextualizes follow-up inquiries into standalone legal queries via LangChain.
    3. Scans Weaviate Cloud LegalChunk collection (22,500+ Indian court precedents).
    4. Synthesizes an authoritative legal opinion via ChatGroq (Qwen 3.8-27B).
    5. Persists conversation turn and cited precedents back to PostgreSQL.
    """
    if req.thread_id:
        await _verify_thread_access(req.thread_id, current_user.id, db)

    try:
        return await legal_rag_service.execute_rag(req, db=db)
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
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream Indian Legal RAG opinion tokens via Server-Sent Events (SSE).
    
    Yields:
    - event: status (dialogue contextualization / vector search stage)
    - event: precedents (retrieved case citations, scores, and standalone query)
    - event: token (generated opinion chunks)
    - event: done (completion stats)
    """
    if req.thread_id:
        await _verify_thread_access(req.thread_id, current_user.id, db)

    return StreamingResponse(
        legal_rag_service.stream_rag_opinion(req, db=db),
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
