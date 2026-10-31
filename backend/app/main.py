"""
FastAPI Application Entry Point
Face Recognition Camera System Backend
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

from app import models, database
from app.api.v1.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables
try:
    models.Base.metadata.create_all(bind=database.engine)
    logger.info("Database tables created/verified successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {str(e)}")

# Initialize FastAPI app
app = FastAPI(
    title="Face Recognition Camera System API",
    description="Backend API for Face Recognition Access Control System using YOLO and Machine Learning",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (configure as needed for production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_router)


@app.get("/", tags=["Root"])
def read_root():
    """
    Root endpoint - Returns API information
    """
    return {
        "message": "Welcome to Face Recognition Camera System API",
        "status": "online",
        "version": "1.0.0",
        "documentation": "/docs",
        "redoc": "/redoc"
    }


@app.get("/api/health", tags=["Health"])
def quick_health_check():
    """Quick health check endpoint"""
    return {
        "status": "healthy",
        "service": "Face Recognition API",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
