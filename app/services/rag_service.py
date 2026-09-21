import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import weaviate.classes.query as wq
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq

from app.core.config import settings
from app.models.message import Message
from app.schemas.rag import LegalRAGRequest, LegalRAGResponse
from app.schemas.vector import VectorSearchResultItem
from app.vector.weaviate_client import (
    _parse_weaviate_object_to_item,
    get_query_vector,
    weaviate_manager,
)

logger = logging.getLogger("legal_ai.rag")

CONTEXTUALIZE_Q_SYSTEM_PROMPT = (
    "Given a chat history and the latest user question which might reference context in the chat history, "
    "formulate a standalone legal question which can be understood without the chat history. "
    "Do NOT answer the question, just reformulate it if needed and otherwise return it as is."
)

LEGAL_QA_SYSTEM_PROMPT = (
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
    """Conversational Indian Legal RAG Service powered by LangChain, Weaviate Cloud, and PostgreSQL."""

    def __init__(self) -> None:
        self.collection_name = settings.DEFAULT_VECTOR_COLLECTION

    def _get_api_key(self) -> str:
        api_key = settings.GROQ_API_KEY.strip() if settings.GROQ_API_KEY else ""
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GROQ_API_KEY is not configured on the backend server. Please set it in .env.",
            )
        return api_key

    async def load_chat_history(
        self, thread_id: uuid.UUID, db: AsyncSession
    ) -> List[BaseMessage]:
        """Load prior conversation turns for a thread from PostgreSQL."""
        query = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.asc())
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        chat_history: List[BaseMessage] = []
        for r in rows:
            if r.role == "user":
                chat_history.append(HumanMessage(content=r.content))
            elif r.role == "assistant":
                chat_history.append(AIMessage(content=r.content))
            elif r.role == "system":
                chat_history.append(SystemMessage(content=r.content))
        return chat_history

    async def contextualize_question(
        self,
        query: str,
        chat_history: List[BaseMessage],
        model: str,
        api_key: str,
    ) -> str:
        """Reformulate follow-up queries using conversation history to make them standalone for Weaviate."""
        if not chat_history:
            return query

        try:
            condense_llm = ChatGroq(
                model=model,
                groq_api_key=api_key,
                temperature=0.0,
                max_tokens=150,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", CONTEXTUALIZE_Q_SYSTEM_PROMPT),
                    MessagesPlaceholder("chat_history"),
                    ("human", "{input}"),
                ]
            )
            chain = prompt | condense_llm | StrOutputParser()
            reformulated = await chain.ainvoke({"chat_history": chat_history, "input": query})
            cleaned = reformulated.strip().strip("\"'")
            return cleaned if cleaned else query
        except Exception as e:
            logger.warning("Query contextualization failed (%s), falling back to raw query.", e)
            return query

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

    def _prepare_clean_sources(
        self, precedents: List[VectorSearchResultItem]
    ) -> List[Dict[str, Any]]:
        """Normalize precedent items into serializable JSON sources for database persistence."""
        clean_sources = []
        for p in precedents:
            clean_sources.append(
                {
                    "case_title": p.title,
                    "court_name": p.metadata.get("court_name", "Indian Court"),
                    "decision_date": p.metadata.get("decision_date") or str(p.metadata.get("year", "")),
                    "case_type": p.metadata.get("case_type", "General"),
                    "influence_score": p.metadata.get("influence_score", 0),
                    "doc_url": p.metadata.get("source_url") or p.metadata.get("doc_url", ""),
                    "score": p.score,
                    "distance": p.distance,
                    "excerpt": (p.content or "")[:200],
                }
            )
        return clean_sources

    async def execute_rag(
        self, req: LegalRAGRequest, db: Optional[AsyncSession] = None
    ) -> LegalRAGResponse:
        """End-to-end Conversational Legal RAG turn with LangChain & PostgreSQL persistence."""
        t0 = time.time()
        api_key = self._get_api_key()
        model = req.model or settings.GROQ_DEFAULT_MODEL

        # 1. Load Conversation History from PostgreSQL if thread_id provided
        chat_history: List[BaseMessage] = []
        if req.thread_id and db:
            chat_history = await self.load_chat_history(req.thread_id, db)

        # 2. Contextualize user question using chat history
        standalone_query = req.query
        if chat_history:
            standalone_query = await self.contextualize_question(
                query=req.query,
                chat_history=chat_history,
                model=model,
                api_key=api_key,
            )

        # 3. Retrieve precedents from Weaviate Cloud using standalone query
        precedents, actual_mode = self.retrieve_precedents(
            query=standalone_query,
            limit=req.limit,
            case_type=req.case_type,
            min_year=req.min_year,
            search_mode=req.search_mode,
        )

        context_block = self.format_context_block(precedents)

        # 4. Synthesize Legal Advisory Opinion with LangChain ChatGroq
        try:
            llm = ChatGroq(
                model=model,
                groq_api_key=api_key,
                temperature=0.1,
                max_tokens=req.max_tokens,
            )
            qa_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", LEGAL_QA_SYSTEM_PROMPT),
                    MessagesPlaceholder("chat_history"),
                    ("human", "Query / Case Facts:\n{input}\n\nRetrieved Case Law Context:\n{context}"),
                ]
            )
            chain = qa_prompt | llm | StrOutputParser()
            answer = await chain.ainvoke(
                {
                    "chat_history": chat_history,
                    "input": req.query,
                    "context": context_block,
                }
            )
        except Exception as e:
            logger.error("LangChain Groq generation failed for model %s: %s", model, e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Groq LLM generation failed: {str(e)}",
            )

        # 5. Persist Conversation Turn into PostgreSQL if thread_id and db are present
        clean_sources = self._prepare_clean_sources(precedents)
        if req.thread_id and db:
            user_msg = Message(
                thread_id=req.thread_id,
                role="user",
                content=req.query,
                sources=[],
            )
            ai_msg = Message(
                thread_id=req.thread_id,
                role="assistant",
                content=answer,
                sources=clean_sources,
            )
            db.add_all([user_msg, ai_msg])
            await db.commit()

        elapsed_ms = round((time.time() - t0) * 1000, 2)

        return LegalRAGResponse(
            query=req.query,
            answer=answer,
            model_used=model,
            precedents_count=len(precedents),
            precedents=precedents,
            search_mode_used=actual_mode,
            standalone_query=standalone_query if standalone_query != req.query else None,
            execution_time_ms=elapsed_ms,
        )

    async def stream_rag_opinion(
        self, req: LegalRAGRequest, db: Optional[AsyncSession] = None
    ) -> AsyncGenerator[str, None]:
        """Stream SSE chunks for real-time drafting in the legal console with DB persistence."""
        t0 = time.time()
        api_key = self._get_api_key()
        model = req.model or settings.GROQ_DEFAULT_MODEL

        # 1. Load History
        chat_history: List[BaseMessage] = []
        if req.thread_id and db:
            chat_history = await self.load_chat_history(req.thread_id, db)

        # Status: contextualizing
        if chat_history:
            yield f"event: status\ndata: {json.dumps({'stage': 'contextualizing', 'message': 'Evaluating dialogue history...'})}\n\n"

        # 2. Contextualize query
        standalone_query = req.query
        if chat_history:
            standalone_query = await self.contextualize_question(
                query=req.query,
                chat_history=chat_history,
                model=model,
                api_key=api_key,
            )

        # Status: searching
        yield f"event: status\ndata: {json.dumps({'stage': 'searching', 'standalone_query': standalone_query})}\n\n"

        # 3. Retrieve precedents from Weaviate Cloud
        precedents, actual_mode = self.retrieve_precedents(
            query=standalone_query,
            limit=req.limit,
            case_type=req.case_type,
            min_year=req.min_year,
            search_mode=req.search_mode,
        )

        precedents_data = [p.model_dump() for p in precedents]
        init_event = {
            "type": "precedents",
            "search_mode": actual_mode,
            "precedents_count": len(precedents),
            "standalone_query": standalone_query,
            "precedents": precedents_data,
        }
        yield f"event: precedents\ndata: {json.dumps(init_event)}\n\n"

        context_block = self.format_context_block(precedents)

        # 4. Stream response tokens via LangChain ChatGroq
        try:
            llm = ChatGroq(
                model=model,
                groq_api_key=api_key,
                temperature=0.1,
                max_tokens=req.max_tokens,
                streaming=True,
            )
            qa_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", LEGAL_QA_SYSTEM_PROMPT),
                    MessagesPlaceholder("chat_history"),
                    ("human", "Query / Case Facts:\n{input}\n\nRetrieved Case Law Context:\n{context}"),
                ]
            )
            chain = qa_prompt | llm

            accumulated_tokens: List[str] = []
            async for chunk in chain.astream(
                {
                    "chat_history": chat_history,
                    "input": req.query,
                    "context": context_block,
                }
            ):
                content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                if content:
                    accumulated_tokens.append(content)
                    yield f"event: token\ndata: {json.dumps({'delta': content})}\n\n"

            full_answer = "".join(accumulated_tokens)

            # 5. Persist to PostgreSQL
            clean_sources = self._prepare_clean_sources(precedents)
            if req.thread_id and db:
                user_msg = Message(
                    thread_id=req.thread_id,
                    role="user",
                    content=req.query,
                    sources=[],
                )
                ai_msg = Message(
                    thread_id=req.thread_id,
                    role="assistant",
                    content=full_answer,
                    sources=clean_sources,
                )
                db.add_all([user_msg, ai_msg])
                await db.commit()

            elapsed_ms = round((time.time() - t0) * 1000, 2)
            done_event = {
                "type": "done",
                "model_used": model,
                "standalone_query": standalone_query if standalone_query != req.query else None,
                "execution_time_ms": elapsed_ms,
            }
            yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

        except Exception as e:
            logger.error("Error during LangChain Groq streaming: %s", e)
            error_event = {"type": "error", "error": str(e)}
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"


# Singleton instance
legal_rag_service = LegalRAGService()
