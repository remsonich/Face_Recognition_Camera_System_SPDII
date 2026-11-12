import base64
import logging
from typing import List, Optional
import cv2
import numpy as np
import face_recognition
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models, schemas, database
from app.services.telegram import telegram_service

logger = logging.getLogger("face_recognition_api")

# Create database tables if they do not exist
try:
    models.Base.metadata.create_all(bind=database.engine)
except Exception as e:
    logger.warning(f"Could not connect to configured database ({e}). Falling back to local SQLite database.")
    print(f"⚠️ Could not connect to remote database: {e}")
    print("ℹ️ Automatically falling back to local SQLite database (sql_app.db) so server can continue running.")
    database.SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"
    database.engine = database.create_engine("sqlite:///./sql_app.db", connect_args={"check_same_thread": False})
    database.SessionLocal = database.sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="Face Recognition & Intruder Alert API",
    description="Face Recognition System with SQLite storage and Telegram Intruder Alerts",
    version="2.1.0"
)

# CORS setup for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# In-memory tracking for scene and person transitions
last_detection_state = {
    "person_encoding": None,
    "last_recognized_name": None,
    "scene_histogram": None,
    "face_count": 0
}


def decode_base64_image(image_str: str) -> tuple[bytes, np.ndarray, np.ndarray]:
    """Decode base64 string to raw bytes, OpenCV BGR image, and RGB image."""
    try:
        if "," in image_str:
            _, encoded = image_str.split(",", 1)
        else:
            encoded = image_str
        raw_bytes = base64.b64decode(encoded)
        nparr = np.frombuffer(raw_bytes, np.uint8)
        bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Failed to decode image buffer.")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return raw_bytes, bgr, rgb
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")


def enhance_image_clahe(bgr_img: np.ndarray) -> np.ndarray:
    """Enhance contrast and brightness using CLAHE on the L-channel of LAB color space for dark/backlit scenes."""
    lab = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    enhanced_bgr = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
    return cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)


def get_face_locations_and_encodings(bgr_img: np.ndarray, rgb_img: np.ndarray):
    """
    Multi-pass robust face detection:
    1. Standard HOG on raw RGB.
    2. If no faces detected, apply adaptive CLAHE enhancement (ideal for webcam shadows/backlighting).
    3. If still no faces, try CLAHE with 2x upsampling.
    """
    # Pass 1: Standard detection
    locs = face_recognition.face_locations(rgb_img)
    active_rgb = rgb_img

    # Pass 2: CLAHE enhancement for dim/backlit scenes
    if not locs:
        enhanced_rgb = enhance_image_clahe(bgr_img)
        locs = face_recognition.face_locations(enhanced_rgb, number_of_times_to_upsample=1)
        active_rgb = enhanced_rgb

    # Pass 3: Upsample=2 on enhanced image for small or distant faces
    if not locs:
        locs = face_recognition.face_locations(active_rgb, number_of_times_to_upsample=2)

    encodings = []
    if locs:
        encodings = face_recognition.face_encodings(active_rgb, locs)

    return locs, encodings, active_rgb


def compare_scene_histograms(hist1, hist2, threshold: float = 0.7) -> bool:
    """Compare HSV histograms to detect significant camera view/scene shifts."""
    if hist1 is None or hist2 is None:
        return False
    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    return correlation < threshold


@app.get("/")
def read_root():
    db_type = "Supabase / PostgreSQL" if "postgres" in database.SQLALCHEMY_DATABASE_URL else "SQLite"
    return {
        "status": "online",
        "service": "Face Recognition & Intruder Alert API",
        "database": db_type,
        "version": "2.1.0"
    }


# ==========================================================
# Face Recognition & Intruder Detection Endpoint
# ==========================================================

@app.post("/api/recognize", response_model=schemas.RecognitionResponse)
def recognize_face(
    request: schemas.RecognitionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        raw_bytes, bgr_img, rgb_img = decode_base64_image(request.image)

        # Compute scene histogram
        hsv_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        scene_histogram = cv2.calcHist([hsv_img], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(scene_histogram, scene_histogram)

        scene_changed = compare_scene_histograms(last_detection_state["scene_histogram"], scene_histogram)

        # Detect faces with adaptive lighting enhancement
        face_locations, encodings, _ = get_face_locations_and_encodings(bgr_img, rgb_img)
        faces_found = len(face_locations)

        # Handle case where no faces are found in current frame
        if faces_found == 0:
            person_left = last_detection_state["face_count"] > 0
            alert_type = "person_left" if person_left else None

            last_detection_state["face_count"] = 0
            last_detection_state["person_encoding"] = None
            last_detection_state["last_recognized_name"] = None
            last_detection_state["scene_histogram"] = scene_histogram

            return schemas.RecognitionResponse(
                status="no face detected",
                faces_found=0,
                alert=person_left,
                alert_type=alert_type,
                matched_users=[],
                unknown_faces_count=0,
                faces=[],
                scene_changed=scene_changed,
                person_changed=False,
                telegram_sent=False,
                message="No face detected in camera view."
            )

        # Fetch known face encodings and users from SQLite database
        known_encodings_records = (
            db.query(models.FaceEncoding)
            .join(models.User)
            .filter(models.User.is_active == True)
            .all()
        )

        known_encodings = []
        known_user_ids = []
        for rec in known_encodings_records:
            arr = np.frombuffer(rec.encoding_data, dtype=np.float64)
            known_encodings.append(arr)
            known_user_ids.append(rec.user_id)

        user_cache = {u.id: u for u in db.query(models.User).filter(models.User.is_active == True).all()}

        detected_faces: List[schemas.DetectedFaceInfo] = []
        matched_users_set = set()
        unknown_faces_count = 0
        MATCH_TOLERANCE = 0.56  # 0.56 is optimal for webcam environments (balances lighting variations with accuracy)

        for loc, enc in zip(face_locations, encodings):
            matched = False
            best_dist = 1.0
            matched_name = "Unknown Person"
            matched_role = None

            if len(known_encodings) > 0:
                distances = face_recognition.face_distance(known_encodings, enc)
                best_idx = int(np.argmin(distances))
                best_dist = float(distances[best_idx])

                if best_dist <= MATCH_TOLERANCE:
                    matched = True
                    matched_user = user_cache.get(known_user_ids[best_idx])
                    if matched_user:
                        matched_name = matched_user.username
                        matched_role = matched_user.role
                        matched_users_set.add(matched_name)

            if matched:
                confidence = round(max(0.0, min(100.0, (1.0 - (best_dist / 0.60)) * 100)), 1)
            else:
                unknown_faces_count += 1
                confidence = round(max(0.0, (1.0 - min(best_dist, 1.0))) * 50, 1)

            detected_faces.append(
                schemas.DetectedFaceInfo(
                    box=list(loc),
                    name=matched_name,
                    role=matched_role,
                    matched=matched,
                    distance=round(best_dist, 3),
                    confidence=confidence
                )
            )

        # Track person transition
        primary_encoding = encodings[0]
        person_changed = False
        if last_detection_state["person_encoding"] is not None:
            matches = face_recognition.compare_faces(
                [last_detection_state["person_encoding"]],
                primary_encoding,
                tolerance=0.58
            )
            person_changed = not matches[0]
        else:
            person_changed = True

        last_detection_state["face_count"] = faces_found
        last_detection_state["person_encoding"] = primary_encoding
        last_detection_state["scene_histogram"] = scene_histogram

        # Determine Alert Condition
        # Priority 1: Unknown / Intruder face detected
        # Priority 2: Scene & Person changed
        # Priority 3: Person changed
        # Priority 4: Scene changed
        alert = False
        alert_type = None
        telegram_sent = False

        if unknown_faces_count > 0:
            alert = True
            alert_type = "unknown_person"
            status_text = "unknown_detected"
            if len(known_encodings) == 0:
                msg = "No trained faces in database. Registered face needed."
            else:
                msg = f"Alert: {unknown_faces_count} unknown face(s) detected!"

            # Schedule Telegram alert in background with intruder snapshot
            if telegram_service.enabled and telegram_service.is_configured():
                background_tasks.add_task(
                    telegram_service.send_intruder_alert,
                    raw_bytes,
                    unknown_count=unknown_faces_count,
                    total_faces=faces_found,
                    matched_names=list(matched_users_set)
                )
                telegram_sent = True
        else:
            # All detected faces are authorized / known
            status_text = "success"
            names_str = ", ".join(matched_users_set)
            msg = f"Authorized: Recognized {names_str}"

            if scene_changed and person_changed:
                alert = True
                alert_type = "scene_and_person_changed"
            elif person_changed and last_detection_state["last_recognized_name"] != names_str:
                alert = True
                alert_type = "person_changed"
            elif scene_changed:
                alert = True
                alert_type = "scene_changed"

            last_detection_state["last_recognized_name"] = names_str

        return schemas.RecognitionResponse(
            status=status_text,
            faces_found=faces_found,
            alert=alert,
            alert_type=alert_type,
            matched_users=list(matched_users_set),
            unknown_faces_count=unknown_faces_count,
            faces=detected_faces,
            scene_changed=scene_changed,
            person_changed=person_changed,
            telegram_sent=telegram_sent,
            message=msg
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing recognize request")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================================
# Face Registration & Management Endpoints
# ==========================================================

@app.post("/api/faces/register", response_model=schemas.FaceRegisterResponse)
def register_face(request: schemas.FaceRegisterRequest, db: Session = Depends(get_db)):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    if not request.images or len(request.images) == 0:
        raise HTTPException(status_code=400, detail="At least 1 face image is required.")

    # 1. Process and extract encodings from images BEFORE touching DB
    extracted_encodings = []
    first_thumbnail = None

    for idx, img_b64 in enumerate(request.images):
        try:
            raw_bytes, bgr_img, rgb_img = decode_base64_image(img_b64)
            locs, encs, _ = get_face_locations_and_encodings(bgr_img, rgb_img)
            if encs:
                extracted_encodings.append(encs[0].tobytes())

                # Generate small thumbnail from the first detected face image
                if first_thumbnail is None:
                    h, w = bgr_img.shape[:2]
                    dim = 96
                    ratio = dim / float(max(h, w))
                    new_w, new_h = int(w * ratio), int(h * ratio)
                    thumb_img = cv2.resize(bgr_img, (new_w, new_h))
                    _, buf = cv2.imencode(".jpg", thumb_img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    first_thumbnail = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

        except Exception as e:
            logger.warning(f"Error processing image sample {idx} for {name}: {e}")
            continue

    if len(extracted_encodings) == 0:
        raise HTTPException(
            status_code=400,
            detail="មិនអាចចាប់យកមុខបានច្បាស់ក្នុងរូបថតនេះទេ។ សូមបន្ថែមពន្លឺលើផ្ទៃមុខ ឬខិតជិតកាមេរ៉ាបន្តិច! (No faces could be detected. Please ensure your face is well-lit and facing the camera.)"
        )

    # 2. Find or create user only when encodings are guaranteed
    user = db.query(models.User).filter(models.User.username == name).first()
    if not user:
        user = models.User(
            username=name,
            role=request.role.strip() if request.role else None,
            thumbnail=first_thumbnail,
            is_active=True
        )
        db.add(user)
        db.flush()
    else:
        if request.role:
            user.role = request.role.strip()
        if first_thumbnail:
            user.thumbnail = first_thumbnail

    for enc_bytes in extracted_encodings:
        face_enc = models.FaceEncoding(
            user_id=user.id,
            encoding_data=enc_bytes
        )
        db.add(face_enc)

    db.commit()
    db.refresh(user)

    return schemas.FaceRegisterResponse(
        status="success",
        user_id=user.id,
        name=user.username,
        role=user.role,
        encodings_saved=len(extracted_encodings),
        message=f"Successfully trained {user.username} with {len(extracted_encodings)} face sample(s)."
    )


@app.get("/api/faces", response_model=List[schemas.UserOut])
def list_registered_faces(db: Session = Depends(get_db)):
    users = db.query(models.User).filter(models.User.is_active == True).all()
    results = []
    for u in users:
        count = db.query(models.FaceEncoding).filter(models.FaceEncoding.user_id == u.id).count()
        if count > 0:
            results.append(
                schemas.UserOut(
                    id=u.id,
                    name=u.username,
                    role=u.role,
                    thumbnail=u.thumbnail,
                    samples_count=count,
                    created_at=u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else None
                )
            )
    return results


@app.delete("/api/faces/{user_id}")
def delete_registered_face(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Remove face encodings and user
    db.query(models.FaceEncoding).filter(models.FaceEncoding.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    return {"status": "success", "message": f"User {user.username} deleted successfully."}


# ==========================================================
# Telegram Bot Configuration & Test Endpoints
# ==========================================================

@app.get("/api/telegram/config", response_model=schemas.TelegramConfigResponse)
def get_telegram_config():
    return schemas.TelegramConfigResponse(
        bot_token_masked=telegram_service.get_masked_token(),
        chat_id=telegram_service.chat_id,
        enabled=telegram_service.enabled,
        configured=telegram_service.is_configured()
    )


@app.post("/api/telegram/config")
def update_telegram_config(config: schemas.TelegramConfigRequest):
    telegram_service.update_config(
        bot_token=config.bot_token,
        chat_id=config.chat_id,
        enabled=config.enabled
    )
    return {
        "status": "success",
        "message": "Telegram settings updated successfully.",
        "configured": telegram_service.is_configured(),
        "enabled": telegram_service.enabled
    }


@app.post("/api/telegram/test")
def test_telegram_connection(req: schemas.TelegramTestRequest):
    success, msg = telegram_service.send_test_message(req.bot_token, req.chat_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}
