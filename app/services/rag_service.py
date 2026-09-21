import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import weaviate.classes.query as wq
from fastapi import HTTPException, status
from groq import Groq

from app.core.config import settings
from app.schemas.rag import LegalRAGRequest, LegalRAGResponse
from app.schemas.vector import VectorSearchResultItem
from app.vector.weaviate_client import (
    _parse_weaviate_object_to_item,
    get_query_vector,
    weaviate_manager,
)

logger = logging.getLogger("legal_ai.rag")

SYSTEM_LEGAL_PROMPT = (
    "You are an elite Indian Supreme Court and High Court Legal Advisory AI. "
    "Your role is to formulate precise, authoritative, and structured legal analysis for Indian lawyers.\n\n"
    "Guidelines:\n"
    "1. Base your legal reasoning strictly on the provided case precedents and Indian statutory law "
    "(IPC, CrPC, Bharatiya Nyaya Sanhita, CPC, Constitution of India, etc.).\n"
    "2. Explicitly cite the case title, court, and year from the provided context whenever discussing principles.\n"
    "3. Structure your response clearly into:\n"
    "   - 📋 **Direct Legal Opinion / Summary**\n"
    "   - 🏛️ **Judicial Precedents & Ratio Decidendi** (citing specific cases from the context)\n"
    "   - ⚖️ **Applicable Statutory Provisions**\n"
    "   - 💡 **Strategic Next Steps / Litigation Advice**\n"
    "4. If the provided context has gaps or does not fully answer the facts, candidly state the limitation."
)


class LegalRAGService:
    """Service to execute end-to-end Indian Legal RAG queries via Weaviate Cloud and Groq LLM."""

    def __init__(self) -> None:
        self.collection_name = settings.DEFAULT_VECTOR_COLLECTION

    def _get_groq_client(self) -> Groq:
        api_key = settings.GROQ_API_KEY.strip() if settings.GROQ_API_KEY else ""
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GROQ_API_KEY is not configured on the backend server. Please set it in .env.",
            )
        return Groq(api_key=api_key)

    def retrieve_precedents(
        self,
        query: str,
        limit: int = 4,
        case_type: Optional[str] = None,
        min_year: int = 0,
        search_mode: str = "hybrid",
    ) -> Tuple[List[VectorSearchResultItem], str]:
        """Retrieve relevant legal precedent chunks from Weaviate Cloud."""
        if not weaviate_manager.is_connected() or not weaviate_manager.client:
            connected = weaviate_manager.connect()
            if not connected or not weaviate_manager.client:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Weaviate Cloud vector database is offline or not configured.",
                )

        collection = weaviate_manager.client.collections.get(self.collection_name)

        filters = None
        if min_year > 0:
            filters = wq.Filter.by_property("year").greater_or_equal(min_year)
        if case_type and case_type.strip():
            type_filter = wq.Filter.by_property("case_type").equal(case_type.strip())
            filters = type_filter if filters is None else (filters & type_filter)

        query_vec: Optional[List[float]] = None
        normalized_mode = search_mode.lower().strip()

        if normalized_mode in ("vector", "hybrid"):
            query_vec = get_query_vector(query)

        items: List[VectorSearchResultItem] = []
        actual_mode = normalized_mode

        # Strategy 1: Hybrid Search
        if normalized_mode == "hybrid" and query_vec is not None:
            try:
                response = collection.query.hybrid(
                    query=query,
                    vector=query_vec,
                    alpha=0.5,
                    limit=limit,
                    filters=filters,
                    return_metadata=wq.MetadataQuery(score=True, distance=True),
                )
                items = [_parse_weaviate_object_to_item(obj) for obj in response.objects]
                actual_mode = "hybrid (vector + BM25)"
            except Exception as e:
                logger.warning("Weaviate hybrid query failed: %s. Falling back to BM25.", e)
                items = []

        # Strategy 2: Vector Search
        elif normalized_mode == "vector" and query_vec is not None:
            try:
                response = collection.query.near_vector(
                    near_vector=query_vec,
                    limit=limit,
                    filters=filters,
                    return_metadata=wq.MetadataQuery(distance=True),
                )
                items = [_parse_weaviate_object_to_item(obj) for obj in response.objects]
                actual_mode = "near_vector (MiniLM 384-d)"
            except Exception as e:
                logger.warning("Weaviate near_vector query failed: %s. Falling back to BM25.", e)
                items = []

        # Strategy 3: BM25 Keyword Search (default / fallback)
        if not items:
            search_props = (
                ["chunk_text", "case_title"]
                if self.collection_name == "LegalChunk"
                else ["content", "title"]
            )
            response = collection.query.bm25(
                query=query,
                query_properties=search_props,
                limit=limit,
                filters=filters,
                return_metadata=wq.MetadataQuery(score=True),
            )
            items = [_parse_weaviate_object_to_item(obj) for obj in response.objects]
            actual_mode = "BM25 keyword search"

        return items, actual_mode

    def format_context_block(self, precedents: List[VectorSearchResultItem]) -> str:
        """Format retrieved precedents into a clean, authoritative context block for the LLM."""
        if not precedents:
            return "No specific precedent records were retrieved from the Indian legal database for this query."

        formatted_parts = []
        for idx, p in enumerate(precedents, start=1):
            title = p.title or "Unknown Case"
            court = p.metadata.get("court_name", "Indian Court")
            date = p.metadata.get("decision_date") or str(p.metadata.get("year", "N/A"))
            case_type = p.metadata.get("case_type", "General")
            score = p.metadata.get("influence_score", 0)
            url = p.metadata.get("source_url") or p.metadata.get("doc_url", "")
            excerpt = (p.content or "").strip()

            part = (
                f"[Precedent {idx}]\n"
                f"Case Title: {title}\n"
                f"Court: {court}\n"
                f"Date/Year: {date}\n"
                f"Category: {case_type} | Citations Influence: {score}\n"
                f"Source: {url}\n"
                f"Judicial Excerpt:\n{excerpt}\n"
            )
            formatted_parts.append(part)

        return "\n" + ("=" * 50) + "\n" + "\n".join(formatted_parts)

    def execute_rag(self, req: LegalRAGRequest) -> LegalRAGResponse:
        """Synchronous end-to-end Legal RAG query returning full synthesis and citations."""
        t0 = time.time()

        precedents, actual_mode = self.retrieve_precedents(
            query=req.query,
            limit=req.limit,
            case_type=req.case_type,
            min_year=req.min_year,
            search_mode=req.search_mode,
        )

        context = self.format_context_block(precedents)
        user_prompt = f"Query / Case Facts:\n{req.query}\n\nRetrieved Case Law Context:\n{context}"

        model = req.model or settings.GROQ_DEFAULT_MODEL
        groq_client = self._get_groq_client()

        try:
            completion = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_LEGAL_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=req.max_tokens,
                stream=False,
            )
            answer = completion.choices[0].message.content or ""
        except Exception as e:
            logger.error("Groq generation failed for model %s: %s", model, e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Groq LLM generation failed: {str(e)}",
            )

        elapsed_ms = round((time.time() - t0) * 1000, 2)

        return LegalRAGResponse(
            query=req.query,
            answer=answer,
            model_used=model,
            precedents_count=len(precedents),
            precedents=precedents,
            search_mode_used=actual_mode,
            execution_time_ms=elapsed_ms,
        )

    async def stream_rag_opinion(
        self, req: LegalRAGRequest
    ) -> AsyncGenerator[str, None]:
        """Stream SSE chunks for real-time drafting in the legal console."""
        t0 = time.time()

        precedents, actual_mode = self.retrieve_precedents(
            query=req.query,
            limit=req.limit,
            case_type=req.case_type,
            min_year=req.min_year,
            search_mode=req.search_mode,
        )

        # First emit precedents metadata event
        precedents_data = [p.model_dump() for p in precedents]
        init_event = {
            "type": "precedents",
            "search_mode": actual_mode,
            "precedents_count": len(precedents),
            "precedents": precedents_data,
        }
        yield f"event: precedents\ndata: {json.dumps(init_event)}\n\n"

        context = self.format_context_block(precedents)
        user_prompt = f"Query / Case Facts:\n{req.query}\n\nRetrieved Case Law Context:\n{context}"

        model = req.model or settings.GROQ_DEFAULT_MODEL
        groq_client = self._get_groq_client()

        try:
            stream = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_LEGAL_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=req.max_tokens,
                stream=True,
            )

            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield f"event: token\ndata: {json.dumps({'delta': content})}\n\n"

            elapsed_ms = round((time.time() - t0) * 1000, 2)
            done_event = {
                "type": "done",
                "model_used": model,
                "execution_time_ms": elapsed_ms,
            }
            yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

        except Exception as e:
            logger.error("Error during Groq streaming: %s", e)
            error_event = {"type": "error", "error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"


# Singleton instance
legal_rag_service = LegalRAGService()
