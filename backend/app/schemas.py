from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    username: str
    role: Optional[str] = None


class UserCreate(UserBase):
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    name: str
    role: Optional[str] = None
    thumbnail: Optional[str] = None
    samples_count: int = 0
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class FaceRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=100)
    images: List[str] = Field(..., min_items=1)  # List of base64 images


class FaceRegisterResponse(BaseModel):
    status: str
    user_id: int
    name: str
    role: Optional[str] = None
    encodings_saved: int
    message: str


class RecognitionRequest(BaseModel):
    image: str  # Base64 encoded image string


class DetectedFaceInfo(BaseModel):
    box: List[int]  # [top, right, bottom, left]
    name: str
    role: Optional[str] = None
    matched: bool
    distance: float
    confidence: float


class RecognitionResponse(BaseModel):
    status: str
    faces_found: int
    alert: bool
    alert_type: Optional[str] = None
    matched_users: List[str] = []
    unknown_faces_count: int = 0
    faces: List[DetectedFaceInfo] = []
    scene_changed: bool = False
    person_changed: bool = False
    telegram_sent: bool = False
    message: str


class TelegramConfigRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: Optional[bool] = None


class TelegramConfigResponse(BaseModel):
    bot_token_masked: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False
    configured: bool = False


class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
