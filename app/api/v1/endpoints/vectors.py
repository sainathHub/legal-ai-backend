from typing import Annotated, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.vector import (
    DocumentChunkCreate,
    VectorSearchQuery,
    VectorSearchResponse,
)
from app.vector.weaviate_client import weaviate_manager

router = APIRouter()


@router.get("/status")
async def get_vector_status() -> Dict[str, Any]:
    """
    Check Weaviate connection status and default collection info.
    """
    is_ready = weaviate_manager.is_connected()
    collections_info = []

    if is_ready and weaviate_manager.client:
        try:
            collections = weaviate_manager.client.collections.list_all()
            collections_info = list(collections.keys())
        except Exception as e:
            collections_info = [f"error listing: {str(e)}"]

    return {
        "connected": is_ready,
        "configured_url": settings.WEAVIATE_URL or "Not configured",
        "default_collection": settings.DEFAULT_VECTOR_COLLECTION,
        "available_collections": collections_info,
    }


@router.post("/chunks", status_code=status.HTTP_201_CREATED)
async def ingest_document_chunk(
    chunk_in: DocumentChunkCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Dict[str, Any]:
    """
    Ingest a text chunk into Weaviate vector store with metadata.
    Automatically tags the chunk with the uploading user's ID.
    """
    if not weaviate_manager.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weaviate vector database is not connected or configured.",
        )

    # Attach user info to chunk metadata
    chunk_in.metadata["uploaded_by_user_id"] = current_user.id
    chunk_in.metadata["user_email"] = current_user.email

    try:
        uuid_str = weaviate_manager.insert_chunk(chunk_in)
        return {
            "status": "success",
            "message": "Chunk indexed in vector database",
            "weaviate_id": uuid_str,
            "doc_id": chunk_in.doc_id,
            "chunk_index": chunk_in.chunk_index,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest chunk into Weaviate: {str(e)}",
        )


@router.post("/search", response_model=VectorSearchResponse)
async def search_vectors(
    query_in: VectorSearchQuery,
    _: Annotated[User, Depends(get_current_active_user)],
) -> VectorSearchResponse:
    """
    Search vector database using hybrid search (keyword + semantic vector) or pure vector search.
    Requires user authentication.
    """
    if not weaviate_manager.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weaviate vector database is not connected or configured.",
        )

    if not query_in.query and not query_in.vector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'query' (text) or 'vector' (embedding list) must be provided.",
        )

    try:
        return weaviate_manager.search(query_in)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed in Weaviate: {str(e)}",
        )


@router.post("/initialize")
async def initialize_collections(
    _: Annotated[User, Depends(get_current_active_user)],
) -> Dict[str, str]:
    """
    Ensure required collections exist in Weaviate.
    """
    if not weaviate_manager.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weaviate vector database is not connected or configured.",
        )
    weaviate_manager.ensure_default_collections()
    return {"status": "ok", "message": f"Default collection '{settings.DEFAULT_VECTOR_COLLECTION}' verified."}
