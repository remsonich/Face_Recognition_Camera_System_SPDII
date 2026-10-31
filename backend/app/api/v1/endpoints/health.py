"""
Health Check Endpoint
System status monitoring
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import schemas

router = APIRouter()


@router.get(
    "",
    response_model=schemas.HealthResponse,
    summary="System health check",
    tags=["Health"]
)
def health_check(db: Session = Depends(get_db)) -> schemas.HealthResponse:
    """
    Check system health and database connection
    Returns status of API and database
    """
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    
    return schemas.HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
        service="Face Recognition API v1.0.0",
        version="1.0.0"
    )
