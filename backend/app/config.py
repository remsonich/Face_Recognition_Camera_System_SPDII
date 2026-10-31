from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Database Configuration
    DATABASE_USER: str = "root"
    DATABASE_PASSWORD: str = "your_password"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 3306
    DATABASE_NAME: str = "face_recognition_db"
    
    # Construct MySQL URL
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
    
    # API Configuration
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    
    # Face Recognition Thresholds
    FACE_CONFIDENCE_THRESHOLD: float = 0.6
    FACE_MATCHING_THRESHOLD: float = 0.75
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
