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


# In-memory tracking for scene, person transitions, and alert log deduplication cooldown
last_detection_state = {
    "person_encoding": None,
    "last_recognized_name": None,
    "scene_histogram": None,
    "face_count": 0,
    "last_alert_log_type": None,
    "last_alert_log_matched": None,
    "last_alert_log_time": None
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
    2. If no valid faces detected, apply adaptive CLAHE enhancement (ideal for webcam shadows/backlighting).
    3. If still no valid faces, try CLAHE with 2x upsampling.
    Filters out tiny noisy false detections (< 42px) when normal webcam frames are processed.
    """
    def _filter_valid_locs(raw_locs):
        return [loc for loc in raw_locs if (loc[2] - loc[0]) >= 42 and (loc[1] - loc[3]) >= 42]

    # Pass 1: Standard detection
    locs = _filter_valid_locs(face_recognition.face_locations(rgb_img))
    active_rgb = rgb_img

    # Pass 2: CLAHE enhancement for dim/backlit scenes
    if not locs:
        enhanced_rgb = enhance_image_clahe(bgr_img)
        locs = _filter_valid_locs(face_recognition.face_locations(enhanced_rgb, number_of_times_to_upsample=1))
        active_rgb = enhanced_rgb

    # Pass 3: Upsample=2 on enhanced image for small or distant faces
    if not locs:
        locs = _filter_valid_locs(face_recognition.face_locations(active_rgb, number_of_times_to_upsample=2))

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


def face_distance_to_confidence(face_distance: float, match_threshold: float = 0.54) -> float:
    """
    Convert dlib ResNet Euclidean face distance into an intuitive 0-100% confidence score.
    Calibrated for real-world webcam lighting variations:
      - dist = 0.00 -> 100.0%
      - dist = 0.30 -> 84.4%
      - dist = 0.40 -> 75.2%
      - dist = 0.48 -> 66.8%
      - dist = 0.54 (threshold) -> 60.0%
      - dist = 0.60 -> 48.0%
      - dist >= 0.84 -> 0.0%
    """
    if face_distance <= match_threshold:
        ratio = max(0.0, face_distance) / max(0.01, match_threshold)
        score = 100.0 - (ratio ** 1.6) * 40.0
        return round(max(60.0, min(100.0, score)), 1)
    else:
        excess = face_distance - match_threshold
        score = 60.0 * (1.0 - (excess / 0.30))
        return round(max(0.0, min(59.9, score)), 1)


def check_liveness_and_spoof(bgr_img: np.ndarray, loc: tuple) -> tuple:
    """
    V2 Multi-Factor Anti-Spoofing & Liveness Detection Engine.
    Evaluates whether a detected face is from a live 3D human or a 2D presentation attack
    (smartphone screen, tablet, monitor, or printed photo) even on vivid OLED screens or tilted phones:
      1. Closed 4-sided screen quadrilateral contour enclosing the face.
      2. Parallel Left/Right & Top/Bottom screen bezel edges bracketing the face at any tilt angle (+-35 deg).
      3. Self-luminous backlit screen brightness step (screen glowing brighter than surrounding hand/room).
      4. Color gamut desaturation (HSV saturation washout on recaptured displays).
      5. Face-surface specular glass reflection/glare.
      6. 2D flat surface micro-texture variance (Laplacian).

    Returns: (is_spoof: bool, reason_str: str, spoof_score: float, details: dict)
    """
    h_img, w_img = bgr_img.shape[:2]
    top, right, bottom, left = loc
    fh = max(1, bottom - top)
    fw = max(1, right - left)
    fcx = (left + right) / 2.0
    fcy = (top + bottom) / 2.0

    # Expanded search region (up to ~0.95x face size around face) to catch full smartphone/tablet bezels
    pad_y = int(fh * 0.95)
    pad_x = int(fw * 0.95)
    ex1 = max(0, left - pad_x)
    ey1 = max(0, top - pad_y)
    ex2 = min(w_img, right + pad_x)
    ey2 = min(h_img, bottom + pad_y)

    exp_roi = bgr_img[ey1:ey2, ex1:ex2]
    face_roi = bgr_img[top:bottom, left:right]

    if exp_roi.size == 0 or face_roi.size == 0:
        return False, "Valid", 0.0, {}

    rel_l = left - ex1
    rel_r = right - ex1
    rel_t = top - ey1
    rel_b = bottom - ey1
    rel_cx = fcx - ex1
    rel_cy = fcy - ey1

    spoof_points = 0
    face_surface_flags = 0
    screen_geometry_confirmed = False
    reasons = []
    details = {}

    gray_exp = cv2.cvtColor(exp_roi, cv2.COLOR_BGR2GRAY)
    blur_exp = cv2.GaussianBlur(gray_exp, (5, 5), 0)
    edges = cv2.Canny(blur_exp, 45, 140)

    # 1. Closed 4-Sided Screen Contour Enclosing the Face (catches phone/tablet screens even with vivid OLED photos!)
    dilated = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    quad_encloses_face = False
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (fw * fh * 1.1):
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if 4 <= len(approx) <= 6:
            if cv2.pointPolygonTest(approx, (rel_cx, rel_cy), False) >= 0:
                quad_encloses_face = True
                break

    details["quad_encloses_face"] = quad_encloses_face
    if quad_encloses_face:
        spoof_points += 50
        screen_geometry_confirmed = True
        reasons.append("រកឃើញស៊ុមអេក្រង់ទូរស័ព្ទ ៤ ជ្រុង (Phone/Tablet Screen Frame Detected)")

    # 2. Parallel Bracketing Bezel Edges at ANY Tilt Angle (up to +-35 deg from vertical/horizontal)
    min_line_len = int(min(fh, fw) * 0.65)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35, minLineLength=min_line_len, maxLineGap=18)

    left_verticals = []
    right_verticals = []
    top_horizontals = []
    bottom_horizontals = []

    if lines is not None:
        for l in lines:
            line_pts = l[0] if len(l.shape) > 1 else l
            x1, y1, x2, y2 = line_pts
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180.0
            mx = (x1 + x2) / 2.0
            my = (y1 + y2) / 2.0

            if 55.0 <= angle <= 125.0:
                ymin, ymax = min(y1, y2), max(y1, y2)
                if ymax > rel_t and ymin < rel_b:
                    if mx < rel_l + fw * 0.15:
                        left_verticals.append((mx, angle))
                    elif mx > rel_r - fw * 0.15:
                        right_verticals.append((mx, angle))
            elif angle <= 35.0 or angle >= 145.0:
                xmin, xmax = min(x1, x2), max(x1, x2)
                if xmax > rel_l and xmin < rel_r:
                    norm_angle = angle if angle <= 90 else angle - 180.0
                    if my < rel_t + fh * 0.15:
                        top_horizontals.append((my, norm_angle))
                    elif my > rel_b - fh * 0.15:
                        bottom_horizontals.append((my, norm_angle))

    parallel_lr_pairs = 0
    for lx, la in left_verticals:
        for rx, ra in right_verticals:
            span_w = rx - lx
            if abs(la - ra) <= 12.0 and (fw * 0.95 <= span_w <= fw * 3.0):
                parallel_lr_pairs += 1

    parallel_tb_pairs = 0
    for ty, ta in top_horizontals:
        for by, ba in bottom_horizontals:
            span_h = by - ty
            if abs(ta - ba) <= 12.0 and (fh * 0.95 <= span_h <= fh * 3.2):
                parallel_tb_pairs += 1

    bezel_sides = (
        int(len(left_verticals) > 0)
        + int(len(right_verticals) > 0)
        + int(len(top_horizontals) > 0)
        + int(len(bottom_horizontals) > 0)
    )
    details["parallel_lr_pairs"] = parallel_lr_pairs
    details["parallel_tb_pairs"] = parallel_tb_pairs
    details["bezel_sides"] = bezel_sides

    if parallel_lr_pairs >= 8 and bezel_sides >= 3:
        spoof_points += 40
        screen_geometry_confirmed = True
        reasons.append("រកឃើញគែមអេក្រង់សងខាងស្របគ្នា (Parallel Phone Bezel Edges)")
    elif parallel_lr_pairs >= 4 and parallel_tb_pairs >= 2 and bezel_sides == 4:
        spoof_points += 30
        reasons.append("រកឃើញគែមស៊ុមអេក្រង់ (Rectangular Screen Borders)")

    # 3. Color Saturation & Gamut (Screens suffer from digital re-sampling and gamut desaturation)
    hsv_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2HSV)
    mean_sat = float(np.mean(hsv_face[:, :, 1]))
    mean_val = float(np.mean(hsv_face[:, :, 2]))
    details["mean_sat"] = round(mean_sat, 2)
    details["mean_val"] = round(mean_val, 2)

    if mean_val > 50:
        if mean_sat < 36.0:
            spoof_points += 35
            face_surface_flags += 1
            reasons.append(f"កម្រិតពណ៌ស្លេកខុសប្រក្រតី (Screen Desaturation S={mean_sat:.1f})")
        elif mean_sat < 44.0:
            spoof_points += 20
            face_surface_flags += 1
            reasons.append(f"កម្រិតពណ៌ទាប (Low Color Saturation S={mean_sat:.1f})")

    # 4. Self-Luminous Screen Backlight Glow (Screen emits light brighter than surrounding hand/room)
    outer_mask = np.ones(gray_exp.shape, dtype=np.uint8)
    cv2.rectangle(
        outer_mask,
        (max(0, rel_l - int(fw * 0.25)), max(0, rel_t - int(fh * 0.25))),
        (min(gray_exp.shape[1], rel_r + int(fw * 0.25)), min(gray_exp.shape[0], rel_b + int(fh * 0.25))),
        0,
        -1
    )
    outer_vals = gray_exp[outer_mask == 1]
    outer_bright = float(np.mean(outer_vals)) if outer_vals.size > 0 else mean_val
    screen_glow_delta = mean_val - outer_bright
    details["screen_glow_delta"] = round(screen_glow_delta, 1)

    if screen_glow_delta >= 35.0 and (parallel_lr_pairs >= 4 or quad_encloses_face or mean_val > 190.0):
        spoof_points += 25
        reasons.append(f"ពន្លឺអេក្រង់ភ្លឺចែងចាំងខុសប្រក្រតី (Backlit Screen Glow +{screen_glow_delta:.0f})")

    # 5. Specular Glare / Glass Reflection on the face surface itself (avoids background windows)
    glare_pad_y = int(fh * 0.10)
    glare_pad_x = int(fw * 0.10)
    g_roi = bgr_img[
        max(0, top - glare_pad_y):min(h_img, bottom + glare_pad_y),
        max(0, left - glare_pad_x):min(w_img, right + glare_pad_x)
    ]
    hsv_glare = cv2.cvtColor(g_roi, cv2.COLOR_BGR2HSV)
    glare_mask = (hsv_glare[:, :, 2] > 245) & (hsv_glare[:, :, 1] < 25)
    glare_ratio = float(np.sum(glare_mask)) / float(max(1, g_roi.shape[0] * g_roi.shape[1]))
    details["glare_ratio"] = round(glare_ratio, 4)

    if glare_ratio > 0.045:
        spoof_points += 25
        face_surface_flags += 1
        reasons.append("ពន្លឺផ្លាតលើកញ្ចក់អេក្រង់ (Screen Glare / Specular Reflection)")
    elif glare_ratio > 0.025:
        spoof_points += 10

    # 6. Texture Variance (Laplacian of Gaussian)
    gray_face = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray_face, cv2.CV_64F).var())
    details["lap_var"] = round(lap_var, 2)

    if lap_var < 180.0:
        spoof_points += 25
        face_surface_flags += 1
        reasons.append(f"ផ្ទៃរាបស្មើគ្មានលម្អិតស្បែក (Flat 2D Surface Var={lap_var:.1f})")
    elif lap_var < 240.0 and mean_val > 100.0:
        spoof_points += 15

    # Live human discount: ONLY apply if NO confirmed phone screen frame geometry was detected!
    if (not screen_geometry_confirmed) and ((mean_sat >= 55.0 and lap_var >= 280.0) or (mean_sat >= 70.0 and lap_var >= 220.0)):
        spoof_points = max(0, spoof_points - 40)

    spoof_score = min(100.0, float(spoof_points))
    details["spoof_score"] = spoof_score
    details["screen_geometry_confirmed"] = screen_geometry_confirmed

    # Flag as spoof if score >= 45 AND either confirmed phone screen geometry or face-surface 2D anomaly
    is_spoof = (spoof_score >= 45.0) and (screen_geometry_confirmed or face_surface_flags > 0)
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

        # Balanced biometric threshold for webcam lighting variations (day/night, glasses on/off).
        # 2D photo & phone screen attacks are blocked independently by check_liveness_and_spoof().
        MATCH_TOLERANCE = 0.54
        clahe_rgb_cache = None

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

                # Lighting-resilient fallback: if a live face is borderline (e.g. harsh side sunlight or dim room),
                # normalize lighting via CLAHE and re-evaluate encoding at the same face location
                if (not is_spoof) and (MATCH_TOLERANCE < best_dist <= 0.62):
                    try:
                        if clahe_rgb_cache is None:
                            clahe_rgb_cache = enhance_image_clahe(bgr_img)
                        clahe_encs = face_recognition.face_encodings(clahe_rgb_cache, [loc])
                        if clahe_encs:
                            clahe_dists = face_recognition.face_distance(known_encodings, clahe_encs[0])
                            clahe_best_idx = int(np.argmin(clahe_dists))
                            clahe_best_dist = float(clahe_dists[clahe_best_idx])
                            if clahe_best_dist < best_dist:
                                best_dist = clahe_best_dist
                                best_idx = clahe_best_idx
                    except Exception as clahe_err:
                        logger.debug(f"CLAHE fallback encoding skipped: {clahe_err}")

                candidate_user = user_cache.get(known_user_ids[best_idx])
                candidate_name = candidate_user["username"] if candidate_user else "Unknown"

                # Calibrated confidence score aligned with MATCH_TOLERANCE (60%-100% for valid matches)
                confidence = face_distance_to_confidence(best_dist, MATCH_TOLERANCE)

                if is_spoof:
                    # Spoof attack detected! Disallow match regardless of similarity
                    matched = False
                    matched_name = "ការក្លែងបន្លំ (Screen Spoof)"
                    matched_role = f"Target: {candidate_name}" if best_dist <= 0.56 else None
                    spoof_detected_count += 1
                    if not primary_spoof_reason:
                        primary_spoof_reason = spoof_reason
                    if not suspected_spoof_target and best_dist <= 0.56:
                        suspected_spoof_target = candidate_name

                elif best_dist <= MATCH_TOLERANCE:
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

        # Persist alert to database if triggered (with 20s server-side deduplication cooldown)
        log_id = None
        if alert and alert_type:
            try:
                now_utc = datetime.now(timezone.utc)
                matched_log_str = (
                    ", ".join(matched_users_set)
                    if matched_users_set
                    else (suspected_spoof_target if suspected_spoof_target else None)
                )

                last_t = last_detection_state.get("last_alert_log_time")
                last_type = last_detection_state.get("last_alert_log_type")
                last_matched = last_detection_state.get("last_alert_log_matched")

                is_duplicate_burst = False
                if last_t is not None and last_type == alert_type:
                    elapsed = (now_utc - last_t).total_seconds()
                    if elapsed < 20.0:
                        if alert_type in ("spoof_detected", "unknown_person"):
                            is_duplicate_burst = True
                        elif last_matched == matched_log_str:
                            is_duplicate_burst = True

                if not is_duplicate_burst:
                    db_log = models.AlertLog(
                        alert_type=alert_type,
                        faces_count=faces_found,
                        matched_users=matched_log_str,
                        telegram_sent=telegram_sent,
                        created_at=now_utc
                    )
                    db.add(db_log)
                    db.commit()
                    db.refresh(db_log)
                    log_id = db_log.id

                    last_detection_state["last_alert_log_type"] = alert_type
                    last_detection_state["last_alert_log_matched"] = matched_log_str
                    last_detection_state["last_alert_log_time"] = now_utc
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

        def _clean_matched(raw_str: Optional[str]) -> List[str]:
            if not raw_str:
                return []
            cleaned = []
            for u in raw_str.split(","):
                name = u.strip()
                if name.startswith("Spoof (") and name.endswith(")"):
                    name = name[7:-1].strip()
                if name:
                    cleaned.append(name)
            return cleaned

        deduped = []
        for r in records:
            matched_list = _clean_matched(r.matched_users)
            r_time = r.created_at
            is_dup = False

            for prev in deduped:
                prev_time = prev["_dt"]
                if prev["type"] == r.alert_type and r_time is not None and prev_time is not None:
                    t1 = r_time.replace(tzinfo=None)
                    t2 = prev_time.replace(tzinfo=None)
                    if abs((t2 - t1).total_seconds()) < 20.0:
                        if r.alert_type in ("spoof_detected", "unknown_person") or prev["matched"] == matched_list:
                            # Keep richer matched info if newer burst row had empty matched
                            if not prev["matched"] and matched_list:
                                prev["matched"] = matched_list
                            if r.telegram_sent:
                                prev["telegram"] = True
                            is_dup = True
                            break

            if not is_dup:
                deduped.append({
                    "id": r.id,
                    "type": r.alert_type,
                    "faces": r.faces_count,
                    "matched": matched_list,
                    "telegram": r.telegram_sent,
                    "time": (r_time.strftime("%Y-%m-%dT%H:%M:%SZ")) if r_time else None,
                    "_dt": r_time
                })

        for item in deduped:
            item.pop("_dt", None)

        return deduped
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

