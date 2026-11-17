import base64
import logging
from datetime import datetime, timezone
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


class BiometricCache:
    """High-speed in-memory cache for face encodings and user metadata to eliminate repeated DB reads during scanning."""
    def __init__(self):
        self.known_encodings: List[np.ndarray] = []
        self.known_user_ids: List[int] = []
        self.user_map: dict = {}  # user_id -> {"username": str, "role": Optional[str]}
        self.is_loaded: bool = False

    def load_if_needed(self, db: Session):
        if not self.is_loaded:
            self.refresh(db)

    def refresh(self, db: Session):
        try:
            records = (
                db.query(models.FaceEncoding)
                .join(models.User)
                .filter(models.User.is_active == True)
                .all()
            )
            self.known_encodings = [np.frombuffer(rec.encoding_data, dtype=np.float64) for rec in records]
            self.known_user_ids = [rec.user_id for rec in records]

            users = db.query(models.User).filter(models.User.is_active == True).all()
            self.user_map = {u.id: {"username": u.username, "role": u.role} for u in users}
            self.is_loaded = True
            logger.info(f"BiometricCache refreshed: {len(self.known_encodings)} encodings across {len(self.user_map)} users in memory.")
        except Exception as e:
            logger.error(f"Failed to refresh BiometricCache from database: {e}")

    def invalidate(self):
        self.is_loaded = False


biometric_cache = BiometricCache()

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


def check_liveness_and_spoof(bgr_img: np.ndarray, loc: tuple) -> tuple:
    """
    Evaluates whether a detected face is from a live 3D human
    or a 2D presentation attack (smartphone screen, tablet, or printed photo).

    Returns: (is_spoof: bool, reason_str: str, spoof_score: float, details: dict)
    """
    h_img, w_img = bgr_img.shape[:2]
    top, right, bottom, left = loc
    fh = max(1, bottom - top)
    fw = max(1, right - left)

    # Context window around the face to detect screen bezel / phone edges
    pad_y = int(fh * 0.40)
    pad_x = int(fw * 0.40)
    exp_top = max(0, top - pad_y)
    exp_bottom = min(h_img, bottom + pad_y)
    exp_left = max(0, left - pad_x)
    exp_right = min(w_img, right + pad_x)

    exp_roi = bgr_img[exp_top:exp_bottom, exp_left:exp_right]
    face_roi = bgr_img[top:bottom, left:right]

    if exp_roi.size == 0 or face_roi.size == 0:
        return False, "Valid", 0.0, {}

    spoof_points = 0
    reasons = []
    details = {}

    # 1. Bezel / Straight Line Edge Detection
    # On a phone screen or tablet, the screen border is close to the face crop and is continuous
    gray_exp = cv2.cvtColor(exp_roi, cv2.COLOR_BGR2GRAY)
    blurred_exp = cv2.GaussianBlur(gray_exp, (5, 5), 0)
    edges = cv2.Canny(blurred_exp, 60, 180)

    min_line_len = int(min(fh, fw) * 0.6)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=45, minLineLength=min_line_len, maxLineGap=10)

    cardinal_lines = 0
    if lines is not None:
        for l in lines:
            line_pts = l[0] if len(l.shape) > 1 else l
            x1, y1, x2, y2 = line_pts
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if angle < 18 or angle > 162 or (72 < angle < 108):
                cardinal_lines += 1

    details["cardinal_lines"] = cardinal_lines
    if cardinal_lines >= 8:
        spoof_points += 35
        reasons.append("រកឃើញគែមអេក្រង់ទូរស័ព្ទ (Screen Bezel Edges)")
    elif cardinal_lines >= 4:
        spoof_points += 15

    # 2. Color Saturation & Gamut (Screens suffer from digital re-sampling and gamut desaturation)
    hsv_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
    sat_channel = hsv_face[:, :, 1]
    val_channel = hsv_face[:, :, 2]

    mean_sat = float(np.mean(sat_channel))
    mean_val = float(np.mean(val_channel))
    details["mean_sat"] = round(mean_sat, 2)
    details["mean_val"] = round(mean_val, 2)

    # Live human face under normal room lighting has warm skin tone (mean_sat >= 48)
    if mean_val > 50:
        if mean_sat < 36.0:
            spoof_points += 35
            reasons.append(f"កម្រិតពណ៌ស្លេកខុសប្រក្រតី (Screen Desaturation S={mean_sat:.1f})")
        elif mean_sat < 44.0:
            spoof_points += 20
            reasons.append(f"កម្រិតពណ៌ទាប (Low Color Saturation S={mean_sat:.1f})")

    # 3. Specular Glare / Glass Reflection
    hsv_exp = cv2.cvtColor(exp_roi, cv2.COLOR_BGR2HSV)
    v_exp = hsv_exp[:, :, 2]
    s_exp = hsv_exp[:, :, 1]
    glare_mask = (v_exp > 245) & (s_exp < 30)
    glare_ratio = float(np.sum(glare_mask)) / float(exp_roi.shape[0] * exp_roi.shape[1])
    details["glare_ratio"] = round(glare_ratio, 4)

    if glare_ratio > 0.022:
        spoof_points += 25
        reasons.append("ពន្លឺផ្លាតលើកញ្ចក់អេក្រង់ (Screen Glare / Specular Reflection)")
    elif glare_ratio > 0.012:
        spoof_points += 10

    # 4. Texture Variance (Laplacian of Gaussian)
    # Real live faces have high micro-texture variance (> 350).
    # Screen re-photographed faces are blurred or low-contrast (< 220).
    gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())
    details["lap_var"] = round(lap_var, 2)

    if lap_var < 180.0:
        spoof_points += 25
        reasons.append(f"ផ្ទៃរាបស្មើគ្មានលម្អិតស្បែក (Flat 2D Surface Var={lap_var:.1f})")
    elif lap_var < 260.0:
        spoof_points += 15

    # Live human bonus: If face has very high natural texture variance (> 450) and rich natural saturation (> 55),
    # significantly discount any false line alarms (from room walls/shelves in background)
    if lap_var > 450.0 and mean_sat > 55.0:
        spoof_points = max(0, spoof_points - 35)

    spoof_score = min(100.0, float(spoof_points))
    details["spoof_score"] = spoof_score

    # Threshold for presentation attack
    is_spoof = spoof_score >= 45.0
    reason_str = " | ".join(reasons) if reasons else "Live face verified"

    return is_spoof, reason_str, spoof_score, details


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

        # Fast in-memory biometric cache lookup (avoids repetitive DB overhead)
        biometric_cache.load_if_needed(db)
        known_encodings = biometric_cache.known_encodings
        known_user_ids = biometric_cache.known_user_ids
        user_cache = biometric_cache.user_map

        detected_faces: List[schemas.DetectedFaceInfo] = []
        matched_users_set = set()
        unknown_faces_count = 0
        spoof_detected_count = 0
        primary_spoof_reason = None
        suspected_spoof_target = None

        # Strict security thresholds to eliminate false positives and 2D photo bypasses
        MATCH_TOLERANCE = 0.46  # Strict distance threshold for biometric authorization
        MIN_MATCH_CONFIDENCE = 50.0  # Minimum 50% confidence required to authorize

        for loc, enc in zip(face_locations, encodings):
            matched = False
            best_dist = 1.0
            matched_name = "Unknown Person"
            matched_role = None

            # 1. Anti-Spoofing & Liveness Inspection (detects phone/tablet screens & photos)
            is_spoof, spoof_reason, spoof_score, _ = check_liveness_and_spoof(bgr_img, loc)

            if len(known_encodings) > 0:
                distances = face_recognition.face_distance(known_encodings, enc)
                best_idx = int(np.argmin(distances))
                best_dist = float(distances[best_idx])
                candidate_user = user_cache.get(known_user_ids[best_idx])
                candidate_name = candidate_user["username"] if candidate_user else "Unknown"

                # Calculate confidence score based on strict distance curve
                if best_dist < 0.55:
                    confidence = round(max(0.0, min(100.0, (1.0 - (best_dist / 0.55)) * 100)), 1)
                else:
                    confidence = 0.0

                if is_spoof:
                    # Spoof attack detected! Disallow match regardless of similarity
                    matched = False
                    matched_name = "ការក្លែងបន្លំ (Screen Spoof)"
                    matched_role = f"Target: {candidate_name}" if best_dist <= 0.52 else None
                    spoof_detected_count += 1
                    if not primary_spoof_reason:
                        primary_spoof_reason = spoof_reason
                    if not suspected_spoof_target and best_dist <= 0.52:
                        suspected_spoof_target = candidate_name

                elif best_dist <= MATCH_TOLERANCE and confidence >= MIN_MATCH_CONFIDENCE:
                    matched = True
                    if candidate_user:
                        matched_name = candidate_user["username"]
                        matched_role = candidate_user["role"]
                        matched_users_set.add(matched_name)
                else:
                    unknown_faces_count += 1
                    matched_name = "Unknown Person"
            else:
                confidence = 0.0
                if is_spoof:
                    matched = False
                    matched_name = "ការក្លែងបន្លំ (Screen Spoof)"
                    spoof_detected_count += 1
                    if not primary_spoof_reason:
                        primary_spoof_reason = spoof_reason
                else:
                    unknown_faces_count += 1

            detected_faces.append(
                schemas.DetectedFaceInfo(
                    box=list(loc),
                    name=matched_name,
                    role=matched_role,
                    matched=matched,
                    distance=round(best_dist, 3),
                    confidence=confidence,
                    is_spoof=is_spoof,
                    spoof_reason=spoof_reason if is_spoof else None
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
        # Priority 1: Spoof attack detected (phone screen / photo spoof)
        # Priority 2: Unknown / Intruder face detected
        # Priority 3: Scene & Person changed
        # Priority 4: Person changed
        # Priority 5: Scene changed
        alert = False
        alert_type = None
        telegram_sent = False

        if spoof_detected_count > 0:
            alert = True
            alert_type = "spoof_detected"
            status_text = "spoof_detected"
            msg = f"Alert: Phone/Photo screen spoof detected! ({primary_spoof_reason})"

            # Send high-priority Telegram alert for presentation attack
            if telegram_service.enabled and telegram_service.is_configured():
                background_tasks.add_task(
                    telegram_service.send_spoof_alert,
                    raw_bytes,
                    spoof_reason=primary_spoof_reason or "Screen bezel or 2D photo detected",
                    suspected_user=suspected_spoof_target
                )
                telegram_sent = True

        elif unknown_faces_count > 0:
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

        # Persist alert to database if triggered
        log_id = None
        if alert and alert_type:
            try:
                from datetime import timezone
                db_log = models.AlertLog(
                    alert_type=alert_type,
                    faces_count=faces_found,
                    matched_users=", ".join(matched_users_set) if matched_users_set else (f"Spoof ({suspected_spoof_target})" if suspected_spoof_target else None),
                    telegram_sent=telegram_sent,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(db_log)
                db.commit()
                db.refresh(db_log)
                log_id = db_log.id
            except Exception as log_err:
                logger.warning(f"Could not persist alert log to database: {log_err}")
                db.rollback()

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
            is_spoof=(spoof_detected_count > 0),
            spoof_detected_count=spoof_detected_count,
            log_id=log_id,
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
    try:
        from sqlalchemy import func
        user = db.query(models.User).filter(func.lower(models.User.username) == name.lower()).first()
        is_new_user = user is None
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

        total_samples = db.query(models.FaceEncoding).filter(models.FaceEncoding.user_id == user.id).count()

        # Synchronize in-memory biometric cache immediately
        biometric_cache.refresh(db)

    except Exception as e:
        db.rollback()
        logger.exception(f"Database error during face registration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database transaction failure during registration: {str(e)}"
        )

    action_msg = f"បានចុះឈ្មោះ {user.username} ជោគជ័យ ({len(extracted_encodings)} គំរូមុខ)!" if is_new_user else f"បានបន្ថែម {len(extracted_encodings)} គំរូមុខថ្មីទៅកាន់ {user.username} (សរុប {total_samples} គំរូ)!"
    return schemas.FaceRegisterResponse(
        status="success",
        user_id=user.id,
        name=user.username,
        role=user.role,
        encodings_saved=len(extracted_encodings),
        message=action_msg
    )


@app.post("/api/faces/check_frame", response_model=schemas.FrameCheckResponse)
def check_face_frame(req: schemas.FrameCheckRequest):
    """Real-time biometric alignment and quality validator for smart automated camera training."""
    try:
        raw_bytes, bgr_img, rgb_img = decode_base64_image(req.image)
        h, w = bgr_img.shape[:2]

        face_locations, _, _ = get_face_locations_and_encodings(bgr_img, rgb_img)
        faces_count = len(face_locations)

        if faces_count == 0:
            return schemas.FrameCheckResponse(
                face_found=False,
                quality_ok=False,
                status="no_face",
                message="មិនទាន់ឃើញមុខនៅឡើយទេ។ សូមមើលចំកាមេរ៉ា (No face detected)"
            )

        if faces_count > 1:
            return schemas.FrameCheckResponse(
                face_found=True,
                quality_ok=False,
                status="multiple_faces",
                message=f"ឃើញមនុស្ស {faces_count} នាក់! សូមឱ្យមានមនុស្សតែម្នាក់គត់មុខកាមេរ៉ា",
                multiple_faces=True
            )

        # Single face evaluation
        top, right, bottom, left = face_locations[0]
        face_w = right - left
        face_h = bottom - top
        face_center_x = (left + right) / 2.0
        face_center_y = (top + bottom) / 2.0

        frame_center_x = w / 2.0
        frame_center_y = h / 2.0

        h_ratio = face_h / float(h)
        too_close = h_ratio > 0.72
        too_far = h_ratio < 0.20

        dx = abs(face_center_x - frame_center_x) / float(w)
        dy = abs(face_center_y - frame_center_y) / float(h)
        centered = dx < 0.22 and dy < 0.25

        if too_far:
            return schemas.FrameCheckResponse(
                face_found=True,
                quality_ok=False,
                status="too_far",
                message="សូមខិតជិតកាមេរ៉ាបន្តិច (Move closer)",
                box=list(face_locations[0]),
                too_far=True,
                centered=centered
            )

        if too_close:
            return schemas.FrameCheckResponse(
                face_found=True,
                quality_ok=False,
                status="too_close",
                message="សូមថយក្រោយបន្តិច (Move back a bit)",
                box=list(face_locations[0]),
                too_close=True,
                centered=centered
            )

        if not centered:
            return schemas.FrameCheckResponse(
                face_found=True,
                quality_ok=False,
                status="not_centered",
                message="សូមដាក់មុខឱ្យចំកណ្តាលរង្វង់ (Center your face)",
                box=list(face_locations[0]),
                centered=False
            )

        return schemas.FrameCheckResponse(
            face_found=True,
            quality_ok=True,
            status="perfect",
            message="មុខចំកណ្តាលល្អឥតខ្ចោះ! (Perfect alignment)",
            box=list(face_locations[0]),
            centered=True,
            too_close=False,
            too_far=False,
            multiple_faces=False
        )

    except Exception as e:
        logger.warning(f"Error checking face frame: {e}")
        return schemas.FrameCheckResponse(
            face_found=False,
            quality_ok=False,
            status="error",
            message=str(e)
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

    try:
        # Remove face encodings and user safely with transaction
        db.query(models.FaceEncoding).filter(models.FaceEncoding.user_id == user_id).delete()
        db.delete(user)
        db.commit()

        # Update in-memory biometric cache immediately
        biometric_cache.refresh(db)
    except Exception as e:
        db.rollback()
        logger.exception(f"Database error during user deletion: {e}")
        raise HTTPException(status_code=500, detail=f"Database error during deletion: {str(e)}")

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


# ==========================================================
# Alert Logs Management Endpoints
# ==========================================================

@app.get("/api/logs")
def get_alert_logs(
    limit: int = 500,
    alert_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(models.AlertLog)
        if alert_type and alert_type != "all":
            query = query.filter(models.AlertLog.alert_type == alert_type)
        records = query.order_by(models.AlertLog.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "type": r.alert_type,
                "faces": r.faces_count,
                "matched": [u.strip() for u in r.matched_users.split(",")] if r.matched_users else [],
                "telegram": r.telegram_sent,
                "time": (r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")) if r.created_at else None
            }
            for r in records
        ]
    except Exception as e:
        logger.warning(f"Error fetching logs from database: {e}")
        return []


@app.post("/api/logs")
def create_alert_log(log_in: schemas.AlertLogCreate, db: Session = Depends(get_db)):
    try:
        db_log = models.AlertLog(
            alert_type=log_in.type,
            faces_count=log_in.faces,
            matched_users=", ".join(log_in.matched) if log_in.matched else None,
            telegram_sent=log_in.telegram,
            created_at=datetime.now(timezone.utc)
        )
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return {
            "id": db_log.id,
            "type": db_log.alert_type,
            "faces": db_log.faces_count,
            "matched": log_in.matched,
            "telegram": db_log.telegram_sent,
            "time": db_log.created_at.isoformat()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/logs/{log_id}")
def delete_alert_log(log_id: int, db: Session = Depends(get_db)):
    try:
        entry = db.query(models.AlertLog).filter(models.AlertLog.id == log_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Log entry not found")
        db.delete(entry)
        db.commit()
        return {"status": "success", "message": f"Log {log_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/logs")
def clear_all_alert_logs(db: Session = Depends(get_db)):
    try:
        db.query(models.AlertLog).delete()
        db.commit()
        return {"status": "success", "message": "All alert logs cleared from database"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

