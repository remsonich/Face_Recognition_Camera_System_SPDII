import pytest
from fastapi import HTTPException, BackgroundTasks
from app.main import list_registered_faces, register_face, recognize_face, biometric_cache
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

def test_biometric_cache():
    db = database.SessionLocal()
    try:
        biometric_cache.load_if_needed(db)
        assert biometric_cache.is_loaded is True
        assert isinstance(biometric_cache.known_encodings, list)
        assert isinstance(biometric_cache.user_map, dict)
    finally:
        db.close()


def test_alert_logs_lifecycle():
    from app.main import create_alert_log, get_alert_logs, delete_alert_log
    db = database.SessionLocal()
    try:
        # Create test log
        log_in = schemas.AlertLogCreate(
            type="unknown_person",
            faces=1,
            matched=[],
            telegram=True
        )
        created = create_alert_log(log_in, db=db)
        assert created["id"] > 0
        assert created["type"] == "unknown_person"
        assert created["telegram"] is True

        # Fetch logs
        logs = get_alert_logs(limit=10, db=db)
        assert isinstance(logs, list)
        assert any(l["id"] == created["id"] for l in logs)

        # Delete test log
        del_res = delete_alert_log(created["id"], db=db)
        assert del_res["status"] == "success"
    finally:
        db.close()


def test_check_face_frame_invalid():
    from app.main import check_face_frame
    req = schemas.FrameCheckRequest(image="invalid_base64")
    res = check_face_frame(req)
    assert res.face_found is False
    assert res.quality_ok is False


def test_check_liveness_and_spoof_detection():
    import numpy as np
    from app.main import check_liveness_and_spoof

    # Test 1: Empty / invalid image handles gracefully
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    is_spoof, reason, score, details = check_liveness_and_spoof(dummy_img, (10, 90, 90, 10))
    assert isinstance(is_spoof, bool)
    assert isinstance(score, float)

    # Test 2: Low-saturation, flat image with sharp borders (spoof simulation)
    spoof_canvas = np.full((300, 300, 3), 180, dtype=np.uint8)
    # Draw screen bezel rectangle
    import cv2
    cv2.rectangle(spoof_canvas, (40, 40), (260, 260), (30, 30, 30), 4)
    is_spoof_canvas, reason_canvas, score_canvas, _ = check_liveness_and_spoof(spoof_canvas, (60, 240, 240, 60))
    assert score_canvas > 30.0  # Should detect bezel borders / flat surface


def test_spoof_alert_log_lifecycle():
    from app.main import create_alert_log, get_alert_logs, delete_alert_log
    db = database.SessionLocal()
    try:
        log_in = schemas.AlertLogCreate(
            type="spoof_detected",
            faces=1,
            matched=["REM Sonich"],
            telegram=True
        )
        created = create_alert_log(log_in, db=db)
        assert created["id"] > 0
        assert created["type"] == "spoof_detected"

        # Filter by spoof_detected
        spoof_logs = get_alert_logs(limit=10, alert_type="spoof_detected", db=db)
        assert any(l["id"] == created["id"] for l in spoof_logs)

        # Cleanup
        del_res = delete_alert_log(created["id"], db=db)
        assert del_res["status"] == "success"
    finally:
        db.close()



