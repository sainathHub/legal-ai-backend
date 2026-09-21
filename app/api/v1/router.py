from fastapi import APIRouter
from app.api.v1.endpoints import auth, health, projects, rag, threads, users, vectors

api_router = APIRouter()

# Register endpoint routers
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(projects.router, prefix="/projects", tags=["Cases / Projects"])
api_router.include_router(threads.router, prefix="", tags=["Chat Threads"])
api_router.include_router(vectors.router, prefix="/vectors", tags=["Vectors"])
api_router.include_router(rag.router, prefix="/rag", tags=["Legal RAG & Advisory"])
