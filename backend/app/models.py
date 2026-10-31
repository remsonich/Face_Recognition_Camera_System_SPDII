from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, LargeBinary, DateTime, Float, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255))
    role = Column(String(50), default="Employee")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    face_encodings = relationship("FaceEncoding", back_populates="user", cascade="all, delete-orphan")
    access_logs = relationship("AccessLog", back_populates="user", cascade="all, delete-orphan")


class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    embedding_data = Column(JSON, nullable=False)  # Store embedding as JSON array
    encoding_bytes = Column(LargeBinary, nullable=True)  # Store numpy array bytes
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="face_encodings")


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    match_status = Column(String(50), nullable=False)  # SUCCESS, UNKNOWN, NO_FACE, FAILED
    confidence = Column(Float, nullable=True)
    bounding_box = Column(JSON, nullable=True)  # Store [x1, y1, x2, y2]
    image_data = Column(LargeBinary, nullable=True)  # Optional: store image for audit
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="access_logs")
