"""
User Management Endpoints
Handles user profiles and access control
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging
from typing import List

from app.database import get_db
from app import models, schemas
from app.services.security import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    tags=["Users"]
)
async def create_user(
    user_create: schemas.UserCreate,
    db: Session = Depends(get_db)
) -> schemas.UserResponse:
    """
    Create a new user account
    Password-based registration (without face)
    """
    try:
        # Check if user already exists
        existing_user = db.query(models.User).filter(
            models.User.username == user_create.username
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Username already exists"
            )
        
        # Create new user
        hashed_password = hash_password(user_create.password)
        
        user = models.User(
            username=user_create.username,
            full_name=user_create.full_name,
            hashed_password=hashed_password,
            role=user_create.role,
            is_active=True
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(f"User '{user_create.username}' created successfully")
        
        return schemas.UserResponse(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"User creation failed: {str(e)}")


@router.get(
    "/{user_id}",
    response_model=schemas.UserResponse,
    summary="Get user profile",
    tags=["Users"]
)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db)
) -> schemas.UserResponse:
    """
    Get user profile by ID
    """
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with ID {user_id} not found"
            )
        
        return schemas.UserResponse(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve user: {str(e)}")


@router.get(
    "",
    response_model=List[schemas.UserResponse],
    summary="List all users",
    tags=["Users"]
)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> List[schemas.UserResponse]:
    """
    List all users with pagination
    """
    try:
        users = db.query(models.User).offset(skip).limit(limit).all()
        
        return [
            schemas.UserResponse(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.put(
    "/{user_id}",
    response_model=schemas.UserResponse,
    summary="Update user profile",
    tags=["Users"]
)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db)
) -> schemas.UserResponse:
    """
    Update user profile information
    """
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with ID {user_id} not found"
            )
        
        # Update fields if provided
        if user_update.full_name is not None:
            user.full_name = user_update.full_name
        
        if user_update.role is not None:
            user.role = user_update.role
        
        if user_update.is_active is not None:
            user.is_active = user_update.is_active
        
        db.commit()
        db.refresh(user)
        
        logger.info(f"User '{user.username}' updated")
        
        return schemas.UserResponse(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"User update failed: {str(e)}")


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    tags=["Users"]
)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
) -> None:
    """
    Delete user account and associated data
    """
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with ID {user_id} not found"
            )
        
        username = user.username
        db.delete(user)
        db.commit()
        
        logger.info(f"User '{username}' deleted")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=f"User deletion failed: {str(e)}")
