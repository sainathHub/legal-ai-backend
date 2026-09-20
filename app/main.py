import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import engine
from app.vector.weaviate_client import weaviate_manager

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("legal_ai.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup connection initialization and graceful shutdown cleanup.
    """
    logger.info("Starting up %s (version %s)...", settings.PROJECT_NAME, settings.VERSION)

    # 1. Connect to Weaviate vector database (graceful: does not block boot if not ready)
    try:
        weaviate_manager.connect()
    except Exception as e:
        logger.warning("Weaviate connection initialization encountered an error: %s", e)

    yield

    # 2. Cleanup Weaviate connection
    try:
        weaviate_manager.disconnect()
    except Exception as e:
        logger.error("Error during Weaviate shutdown: %s", e)

    # 3. Dispose SQLAlchemy database connection pool
    try:
        await engine.dispose()
        logger.info("Disposed database connection pool.")
    except Exception as e:
        logger.error("Error disposing database engine: %s", e)

    logger.info("Application shutdown complete.")


# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade FastAPI boilerplate backend integrated with PostgreSQL "
        "(User authentication & relational data) and Weaviate (Vector database & semantic search)."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root endpoint welcoming visitors and directing to interactive documentation."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs": "/docs",
        "api_v1": settings.API_V1_STR,
    }


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
