from datetime import datetime
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, LargeBinary, DateTime, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    role = Column(String, nullable=True)
    thumbnail = Column(Text, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    encodings = relationship("FaceEncoding", back_populates="user", cascade="all, delete-orphan")


class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    encoding_data = Column(LargeBinary)  # 128-d float64 numpy array bytes
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="encodings")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, index=True)
    faces_count = Column(Integer, default=1)
    matched_users = Column(Text, nullable=True)  # Comma-separated names
    telegram_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

