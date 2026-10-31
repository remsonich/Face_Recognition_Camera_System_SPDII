#!/usr/bin/env python3
"""
Database setup script - Creates database and tables for Face Recognition System
"""
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Database credentials
DB_USER = os.getenv("DATABASE_USER", "root")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "1362")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "3306")
DB_NAME = os.getenv("DATABASE_NAME", "face_recognition_db")

print("=" * 60)
print("Face Recognition System - Database Setup")
print("=" * 60)
print(f"\nConnecting to MySQL at {DB_HOST}:{DB_PORT}...")
print(f"Database: {DB_NAME}")
print(f"User: {DB_USER}\n")

# Step 1: Connect to MySQL server (without selecting a database)
try:
    engine_root = create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}",
        echo=False
    )
    connection = engine_root.connect()
    print("✓ Connected to MySQL server\n")
except OperationalError as e:
    print(f"✗ Failed to connect to MySQL: {e}")
    print("\nTroubleshooting:")
    print("1. Ensure MySQL is running: brew services start mysql")
    print("2. Check credentials in .env file")
    print("3. Verify port 3306 is open")
    sys.exit(1)

# Step 2: Drop existing database (if you want to reset)
# Uncomment the following lines to drop and recreate
# try:
#     connection.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME};"))
#     connection.commit()
#     print(f"✓ Dropped existing database '{DB_NAME}'\n")
# except Exception as e:
#     print(f"✗ Failed to drop database: {e}")

# Step 3: Create database if it doesn't exist
try:
    connection.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
    connection.commit()
    print(f"✓ Database '{DB_NAME}' created/verified\n")
except Exception as e:
    print(f"✗ Failed to create database: {e}")
    sys.exit(1)

# Step 4: Close root connection and connect to the database
connection.close()
engine_root.dispose()

try:
    engine_db = create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        echo=False
    )
    test_connection = engine_db.connect()
    print(f"✓ Connected to database '{DB_NAME}'\n")
    test_connection.close()
except OperationalError as e:
    print(f"✗ Failed to connect to database: {e}")
    sys.exit(1)

# Step 5: Create tables
try:
    from app.database import Base
    from app.models import User, FaceEncoding, AccessLog
    
    # Drop existing tables (optional - uncomment for fresh start)
    # Base.metadata.drop_all(bind=engine_db)
    # print("Dropped existing tables\n")
    
    Base.metadata.create_all(bind=engine_db)
    print("✓ Database tables created successfully!\n")
    print("Tables created:")
    print("  - users")
    print("  - face_encodings")
    print("  - access_logs\n")
except Exception as e:
    print(f"✗ Failed to create tables: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 6: Verify tables exist
try:
    connection = engine_db.connect()
    result = connection.execute(text("SHOW TABLES;"))
    tables = result.fetchall()
    
    print("=" * 60)
    print("✓ Setup Complete!")
    print("=" * 60)
    print(f"\nDatabase '{DB_NAME}' is ready with {len(tables)} tables:")
    for table in tables:
        print(f"  ✓ {table[0]}")
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. View in DBeaver:")
    print("   - Open DBeaver")
    print("   - Create new MySQL connection")
    print(f"   - Host: {DB_HOST}")
    print(f"   - Port: {DB_PORT}")
    print(f"   - Database: {DB_NAME}")
    print(f"   - Username: {DB_USER}")
    print(f"   - Password: ••••••\n")
    
    print("2. Start the API server:")
    print("   source venv/bin/activate")
    print("   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload\n")
    
    print("3. Access API documentation:")
    print("   http://127.0.0.1:8000/docs\n")
    
    print("4. Test endpoints:")
    print("   - GET http://127.0.0.1:8000/api/health")
    print("   - POST http://127.0.0.1:8000/api/v1/faces/register")
    print("   - POST http://127.0.0.1:8000/api/v1/faces/scan\n")
    
    connection.close()
except Exception as e:
    print(f"✗ Verification failed: {e}")
    sys.exit(1)

print("=" * 60)
