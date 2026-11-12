import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger("database")

# Load environment variables from .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

raw_url = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db").strip()

# Check if user left placeholder text from the example
is_placeholder = any(
    token in raw_url for token in ["abcdefghijklm", "[PROJECT_REF]", "[YOUR-PASSWORD]", "[YOUR_PASSWORD]"]
)

if is_placeholder:
    print("ℹ️ Note: DATABASE_URL in .env has placeholder example text. Falling back to local SQLite database.")
    SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"
else:
    SQLALCHEMY_DATABASE_URL = raw_url

# Normalize PostgreSQL URI to use psycopg2 driver (installed in venv)
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif SQLALCHEMY_DATABASE_URL.startswith("postgresql://") and not SQLALCHEMY_DATABASE_URL.startswith("postgresql+"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
