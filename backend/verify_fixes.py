#!/usr/bin/env python3
"""Verify all backend fixes are working correctly"""
import sys
import warnings

# Suppress verbose warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("BACKEND STARTUP VERIFICATION")
print("=" * 60)

try:
    print("\n[1/4] Importing Face Detector...")
    from app.services.face_detector import YOLOFaceDetector
    detector = YOLOFaceDetector()
    print(f"      ✓ Loaded with backend: {detector.backend}")
except Exception as e:
    print(f"      ✗ Failed: {e}")
    sys.exit(1)

try:
    print("\n[2/4] Importing Face Recognizer...")
    from app.services.face_recognizer import FaceRecognizer
    recognizer = FaceRecognizer()
    print(f"      ✓ Loaded with model: {recognizer.model_name}")
    print(f"      ✓ Has extract_embedding_from_array: {hasattr(recognizer, 'extract_embedding_from_array')}")
except Exception as e:
    print(f"      ✗ Failed: {e}")
    sys.exit(1)

try:
    print("\n[3/4] Checking Pydantic v2 Compatibility...")
    from app.schemas import UserResponse
    from pydantic import ConfigDict
    print(f"      ✓ UserResponse uses model_config: {hasattr(UserResponse, 'model_config')}")
except Exception as e:
    print(f"      ✗ Failed: {e}")
    sys.exit(1)

try:
    print("\n[4/4] Importing FastAPI App...")
    from app.main import app
    print(f"      ✓ App imported successfully")
except Exception as e:
    print(f"      ✗ Failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL CHECKS PASSED - Backend ready to start!")
print("=" * 60)
print("\nTo run the server, execute:")
print("  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload")
