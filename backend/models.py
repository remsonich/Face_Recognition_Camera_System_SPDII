from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, LargeBinary
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    encoding_data = Column(LargeBinary) # Store numpy array bytes
