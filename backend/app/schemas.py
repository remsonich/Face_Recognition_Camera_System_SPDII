from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
import json

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    role: str = "Employee"

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class FaceEncodingResponse(BaseModel):
    id: int
    user_id: int
    confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AccessLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    match_status: str
    confidence: Optional[float] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class RecognitionRequest(BaseModel):
    image: str  # Base64 encoded image

class RecognitionResponse(BaseModel):
    status: str
    faces_found: int
    recognized: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    confidence: Optional[float] = None
    bounding_boxes: Optional[List[List[int]]] = None
    message: str

class FaceRegistrationRequest(BaseModel):
    image: str  # Base64 encoded image
    username: str
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: str = "Employee"

class FaceRegistrationResponse(BaseModel):
    user_id: int
    username: str
    status: str
    message: str
    encoding_id: Optional[int] = None

class FaceDeletionResponse(BaseModel):
    status: str
    deleted_encodings: int
    message: str

class HealthResponse(BaseModel):
    status: str
    database: str
    service: str
    version: str

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    image: str  # Base64 encoded image

class LoginResponse(BaseModel):
    status: str
    success: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    message: str
