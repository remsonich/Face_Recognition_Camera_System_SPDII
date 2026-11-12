import pytest
from fastapi import HTTPException, BackgroundTasks
from app.main import list_registered_faces, register_face, recognize_face
from app import database, schemas

def test_list_faces():
    db = database.SessionLocal()
    try:
        res = list_registered_faces(db=db)
        assert isinstance(res, list)
    finally:
        db.close()

def test_register_face_empty_validation():
    db = database.SessionLocal()
    try:
        req = schemas.FaceRegisterRequest(name="Test", role="QA", images=["invalid_b64"])
        with pytest.raises(HTTPException):
            register_face(req, db=db)
    finally:
        db.close()

def test_recognize_invalid_image():
    db = database.SessionLocal()
    try:
        req = schemas.RecognitionRequest(image="invalid_data")
        with pytest.raises(HTTPException) as exc:
            recognize_face(req, background_tasks=BackgroundTasks(), db=db)
        assert exc.value.status_code == 400
    finally:
        db.close()
