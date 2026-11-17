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
    is_spoof: bool = False
    spoof_reason: Optional[str] = None


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
    is_spoof: bool = False
    spoof_detected_count: int = 0
    log_id: Optional[int] = None
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


class AlertLogOut(BaseModel):
    id: int
    type: str
    faces: int
    matched: List[str] = []
    telegram: bool
    time: str

    class Config:
        from_attributes = True


class AlertLogCreate(BaseModel):
    type: str
    faces: int = 1
    matched: List[str] = []
    telegram: bool = False


class FrameCheckRequest(BaseModel):
    image: str  # Base64 image


class FrameCheckResponse(BaseModel):
    face_found: bool
    quality_ok: bool
    status: str
    message: str
    box: Optional[List[int]] = None
    centered: bool = False
    too_close: bool = False
    too_far: bool = False
    multiple_faces: bool = False


