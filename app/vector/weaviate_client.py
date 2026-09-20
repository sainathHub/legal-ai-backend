import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.config import Property, DataType, Configure
from weaviate.classes.query import MetadataQuery, Filter

from app.core.config import settings
from app.schemas.vector import (
    DocumentChunkCreate,
    VectorSearchQuery,
    VectorSearchResultItem,
    VectorSearchResponse,
)

logger = logging.getLogger("legal_ai.vector")


class WeaviateClientManager:
    """Manager for Weaviate v4 client connection, schema lifecycle, and vector search."""

    def __init__(self) -> None:
        self.client: Optional[weaviate.WeaviateClient] = None
        self._connected: bool = False

    def connect(self) -> bool:
        """Establish connection to Weaviate Cloud (WCS) or local Weaviate instance."""
        url = settings.WEAVIATE_URL.strip() if settings.WEAVIATE_URL else ""
        if not url:
            logger.info("WEAVIATE_URL is not configured. Vector features will be disabled until configured.")
            self._connected = False
            return False

        headers: Dict[str, str] = {}
        if settings.OPENAI_API_KEY:
            headers["X-OpenAI-Api-Key"] = settings.OPENAI_API_KEY

        try:
            # Case 1: Weaviate Cloud (WCS)
            if "weaviate.network" in url or "weaviate.cloud" in url:
                auth = Auth.api_key(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=url,
                    auth_credentials=auth,
                    headers=headers if headers else None,
                )
            # Case 2: Localhost or Custom Host (Docker / Kubernetes)
            else:
                parsed = urlparse(url)
                host = parsed.hostname or "localhost"
                port = parsed.port or (443 if parsed.scheme == "https" else 8080)
                is_secure = parsed.scheme == "https"
                
                auth = Auth.api_key(settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None
                self.client = weaviate.connect_to_custom(
                    http_host=host,
                    http_port=port,
                    http_secure=is_secure,
                    grpc_host=host,
                    grpc_port=50051,
                    grpc_secure=is_secure,
                    auth_credentials=auth,
                    headers=headers if headers else None,
                )

            if self.client.is_ready():
                self._connected = True
                logger.info("Connected successfully to Weaviate at %s", url)
                self.ensure_default_collections()
                return True
            else:
                logger.warning("Weaviate server at %s responded but is not ready.", url)
                self._connected = False
                return False

        except Exception as e:
            logger.warning("Failed to connect to Weaviate at %s: %s", url, str(e))
            self.client = None
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close the Weaviate client connection."""
        if self.client:
            try:
                self.client.close()
                logger.info("Closed Weaviate client connection.")
            except Exception as e:
                logger.error("Error closing Weaviate client: %s", e)
            finally:
                self.client = None
                self._connected = False

    def is_connected(self) -> bool:
        """Check if Weaviate client is currently connected and healthy."""
        if not self._connected or not self.client:
            return False
        try:
            return self.client.is_ready()
        except Exception:
            return False

    def ensure_default_collections(self) -> None:
        """Ensure default collections (e.g. LegalDocument) exist with proper schema."""
        if not self.is_connected() or not self.client:
            return

        collection_name = settings.DEFAULT_VECTOR_COLLECTION
        try:
            if not self.client.collections.exists(collection_name):
                logger.info("Creating default Weaviate collection '%s'...", collection_name)
                self.client.collections.create(
                    name=collection_name,
                    properties=[
                        Property(name="doc_id", data_type=DataType.TEXT, index_filterable=True, index_searchable=True),
                        Property(name="chunk_index", data_type=DataType.INT),
                        Property(name="title", data_type=DataType.TEXT, index_searchable=True),
                        Property(name="content", data_type=DataType.TEXT, index_searchable=True),
                        Property(name="metadata_json", data_type=DataType.TEXT),
                    ],
                )
                logger.info("Collection '%s' created successfully.", collection_name)
        except Exception as e:
            logger.error("Error creating Weaviate collection '%s': %s", collection_name, e)

    def insert_chunk(self, chunk: DocumentChunkCreate, collection_name: Optional[str] = None) -> str:
        """Insert a document chunk into Weaviate with optional vector."""
        if not self.is_connected() or not self.client:
            raise RuntimeError("Weaviate is not connected or configured.")

        coll_name = collection_name or settings.DEFAULT_VECTOR_COLLECTION
        collection = self.client.collections.get(coll_name)

        properties = {
            "doc_id": chunk.doc_id,
            "chunk_index": chunk.chunk_index,
            "title": chunk.title or "",
            "content": chunk.content,
            "metadata_json": json.dumps(chunk.metadata),
        }

        uuid_result = collection.data.insert(
            properties=properties,
            vector=chunk.vector if chunk.vector else None,
        )
        return str(uuid_result)

    def search(self, query: VectorSearchQuery, collection_name: Optional[str] = None) -> VectorSearchResponse:
        """Perform semantic, keyword, or hybrid search across documents."""
        if not self.is_connected() or not self.client:
            raise RuntimeError("Weaviate is not connected or configured.")

        coll_name = collection_name or settings.DEFAULT_VECTOR_COLLECTION
        collection = self.client.collections.get(coll_name)

        filters = None
        if query.filter_doc_id:
            filters = Filter.by_property("doc_id").equal(query.filter_doc_id)

        items: List[VectorSearchResultItem] = []

        # 1. Hybrid Search (when query text is provided)
        if query.query:
            response = collection.query.hybrid(
                query=query.query,
                vector=query.vector,
                alpha=query.alpha,
                limit=query.limit,
                filters=filters,
                return_metadata=MetadataQuery(score=True, distance=True),
            )
            for obj in response.objects:
                meta = {}
                raw_meta = obj.properties.get("metadata_json")
                if raw_meta and isinstance(raw_meta, str):
                    try:
                        meta = json.loads(raw_meta)
                    except Exception:
                        meta = {"raw": raw_meta}

                items.append(
                    VectorSearchResultItem(
                        id=str(obj.uuid),
                        doc_id=obj.properties.get("doc_id"),
                        chunk_index=obj.properties.get("chunk_index"),
                        title=obj.properties.get("title"),
                        content=obj.properties.get("content"),
                        metadata=meta,
                        score=obj.metadata.score if obj.metadata else None,
                        distance=obj.metadata.distance if obj.metadata else None,
                    )
                )
        # 2. Pure Vector Search (when only vector is provided)
        elif query.vector:
            response = collection.query.near_vector(
                near_vector=query.vector,
                limit=query.limit,
                filters=filters,
                return_metadata=MetadataQuery(distance=True),
            )
            for obj in response.objects:
                meta = {}
                raw_meta = obj.properties.get("metadata_json")
                if raw_meta and isinstance(raw_meta, str):
                    try:
                        meta = json.loads(raw_meta)
                    except Exception:
                        meta = {"raw": raw_meta}

                items.append(
                    VectorSearchResultItem(
                        id=str(obj.uuid),
                        doc_id=obj.properties.get("doc_id"),
                        chunk_index=obj.properties.get("chunk_index"),
                        title=obj.properties.get("title"),
                        content=obj.properties.get("content"),
                        metadata=meta,
                        distance=obj.metadata.distance if obj.metadata else None,
                    )
                )

        return VectorSearchResponse(
            total_results=len(items),
            query=query.query,
            results=items,
        )


# Global singleton instance
weaviate_manager = WeaviateClientManager()
