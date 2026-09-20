from typing import Any, Dict
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.vector.weaviate_client import weaviate_manager

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Liveness probe: verifies that the web service is alive."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/ready", tags=["Health"])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Readiness probe: verifies downstream database connections (PostgreSQL and Weaviate).
    Used by Render and orchestrators to determine if the container can receive traffic.
    """
    checks = {
        "postgres": "unknown",
        "weaviate": "unknown",
    }
    all_ready = True

    # 1. Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "connected"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"
        all_ready = False

    # 2. Check Weaviate
    if not settings.WEAVIATE_URL:
        checks["weaviate"] = "unconfigured (skipped)"
    elif weaviate_manager.is_connected():
        checks["weaviate"] = "connected"
    else:
        checks["weaviate"] = "disconnected"
        # We don't fail overall readiness if Weaviate is optional/reconnecting, but we report it.

    http_status = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if all_ready else "degraded",
            "checks": checks,
        },
    )
