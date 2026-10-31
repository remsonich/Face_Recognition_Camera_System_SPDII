"""
API v1 Router
Combines all API endpoints into a unified router
"""
from fastapi import APIRouter
from app.api.v1.endpoints import faces, users, health

api_router = APIRouter(prefix="/api/v1")

# Include endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(faces.router, prefix="/faces", tags=["Faces"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
