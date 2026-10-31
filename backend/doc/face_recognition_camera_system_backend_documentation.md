# Technical Documentation & Architecture Guide
**Project Title:** Face Recognition Camera System for Access Control  
**Platform:** Web-based UI (Frontend) with Machine Learning & FastAPI (Backend)  
**Document Purpose:** Complete technical architecture, YOLO integration pipeline, API specifications, and database schema design for backend developers and team leaders.

---

## 1. System Overview & Technical Stack

The system captures live video frames from a web browser via WebRTC/`getUserMedia`, sends the image payloads to a high-performance Python FastAPI backend, processes face detection using **YOLO**, performs face identification/embeddings, and verifies authorization against a PostgreSQL database.

| Layer | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Frontend** | HTML5, CSS3, JavaScript (WebRTC, Fetch API) | Camera stream, frame capture, TTS voice response |
| **API Framework** | Python 3.10+, FastAPI, Uvicorn | High-concurrency RESTful API service |
| **Face Detection** | YOLOv8 / YOLOv11 (Ultralytics), OpenCV | High-speed, real-time face localization & cropping |
| **Face Embedding** | DeepFace / FaceNet / ArcFace | 128D / 512D vector extraction & distance matching |
| **Database** | PostgreSQL | User profiles, biometric vector storage, audit logs |
| **ORM & Validation**| SQLAlchemy 2.0, Pydantic v2 | DB queries, data validation, API contracts |

---

## 2. Directory & File Structure

```text
Face_Recognition_Camera_System_SPDII/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI initialization, CORS, routing
│   │   ├── config.py                # App settings, thresholds, environment vars
│   │   ├── database.py              # PostgreSQL database engine & session dependency
│   │   ├── models.py                # SQLAlchemy ORM database models
│   │   ├── schemas.py               # Pydantic schemas for request/response validation
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── api.py           # Includes endpoints routers
│   │   │       └── endpoints/
│   │   │           ├── __init__.py
│   │   │           ├── faces.py     # Scanning, Registration, Deletion endpoints
│   │   │           ├── users.py     # Profile management endpoints
│   │   │           └── health.py    # System status check endpoint
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── face_detector.py     # YOLO Face Detection logic
│   │   │   ├── face_recognizer.py   # Embedding extraction & cosine distance calculation
│   │   │   └── security.py          # Data encryption & authorization utilities
│   │   └── utils/
│   │       └── __init__.py
│   ├── models/                      # Stored weights (e.g., yolov8n-face.pt)
│   │   └── yolov8n-face.pt
│   ├── tests/                       # Pytest automated test suite
│   │   ├── test_faces.py
│   │   └── test_health.py
│   ├── requirements.txt             # Python package dependencies
│   └── Dockerfile                   # Deployment container config
└── frontend/                        # Web Interface (HTML5, JS, CSS)
    ├── index.html
    ├── style.css
    └── app.js
```

---

## 3. Core Implementation Code

### 3.1 Dependencies (`backend/requirements.txt`)

```text
fastapi==0.110.0
uvicorn==0.28.0
pydantic==2.6.4
pydantic-settings==2.2.1
sqlalchemy==2.0.28
psycopg2-binary==2.9.9
python-multipart==0.0.9
opencv-python-headless==4.9.0.80
ultralytics==8.1.42
numpy==1.26.4
scipy==1.12.0
```

---

### 3.2 FastAPI App Entrypoint (`backend/app/main.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.config import settings

app = FastAPI(
    title="Face Recognition Camera System API",
    description="Backend ML Engine for Access Control using YOLO and FastAPI",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS for Web Interface integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/", tags=["Root"])
def read_root():
    return {
        "system": "Face Recognition Access Control Engine",
        "status": "Online",
        "docs": "/docs"
    }
```

---

### 3.3 Database Models (`backend/app/models.py`)

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String(100), nullable=False)
    role = Column(String(50), default="Employee")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    faces = relationship("FaceEmbedding", back_populates="user", cascade="all, delete-orphan")

class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    embedding_data = Column(JSON, nullable=False)  # Stores vector array (e.g. 128D/512D)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="faces")

class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)
    match_status = Column(String(20), nullable=False)  # 'SUCCESS', 'UNKNOWN', 'NO_FACE'
    confidence = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
```

---

### 3.4 Machine Learning Engine: YOLO Detector & Recognizer (`backend/app/services/face_detector.py`)

```python
import cv2
import numpy as np
from ultralytics import YOLO

class YOLOFaceDetector:
    def __init__(self, model_path: str = "models/yolov8n-face.pt", conf_threshold: float = 0.6):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold

    def detect(self, image_bytes: bytes):
        """
        Processes image payload, runs YOLO inference, returning crops and bounding boxes.
        """
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Invalid image file format")

        results = self.model(img)
        detections = []

        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                if conf >= self.conf_threshold:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    # Bound checks for cropping
                    h, w, _ = img.shape
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    
                    face_crop = img[y1:y2, x1:x2]
                    detections.append({
                        "bounding_box": [x1, y1, x2, y2],
                        "confidence": round(conf, 4),
                        "crop": face_crop
                    })

        return img, detections
```

---

### 3.5 API Route Implementation (`backend/app/api/v1/endpoints/faces.py`)

```python
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.face_detector import YOLOFaceDetector

router = APIRouter()
detector = YOLOFaceDetector()

@router.post("/scan", summary="Scan Face for Access Control")
async def scan_face(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")

    image_bytes = await file.read()
    
    try:
        _, detections = detector.detect(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    if not detections:
        return {
            "status": "UNKNOWN",
            "message": "No face detected in video frame",
            "recognized": False,
            "user": None
        }

    # Extract primary face detected
    primary_detection = detections[0]
    
    # Threshold Verification Rule (Architecture Rule: Reject low confidence/uncertain matches)
    RECOGNITION_THRESHOLD = 0.75  # Cosine distance / match threshold
    
    # Mocking recognition pipeline evaluation (Integrate with embeddings matcher)
    match_found = False  
    user_data = None

    if match_found:
        return {
            "status": "MATCHED",
            "recognized": True,
            "confidence": primary_detection["confidence"],
            "bounding_box": primary_detection["bounding_box"],
            "user": user_data
        }
    
    return {
        "status": "UNKNOWN",
        "recognized": False,
        "confidence": primary_detection["confidence"],
        "bounding_box": primary_detection["bounding_box"],
        "user": None,
        "message": "Access Denied: Face not recognized in system database"
    }
```

---

## 4. API Endpoints Contract Specification

| Method | Endpoint | Request Payload | Response Object | Description |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/faces/scan` | `multipart/form-data` (file) | JSON (`status`, `user`, `bounding_box`) | Real-time face detection via YOLO and identification lookup. |
| `POST` | `/api/v1/faces/register` | `multipart/form-data` (`file`, `full_name`, `role`) | JSON (`user_id`, `status`) | Registers a user, extracts embedding, and saves to DB. |
| `GET` | `/api/v1/users/{id}` | Path Parameter (`id`) | JSON (`user_profile`) | Fetches metadata of authorized person. |
| `DELETE`| `/api/v1/faces/{id}` | Path Parameter (`id`) | JSON (`deleted`: true) | Purges face embedding data per privacy standards. |
| `GET` | `/api/v1/health` | None | JSON (`status`: "healthy") | Health check probe for system monitoring. |

---

## 5. Setup & Deployment Instructions

### Local Development Setup

1. **Clone and navigate to backend:**
   ```bash
   cd Face_Recognition_Camera_System_SPDII/backend
   ```

2. **Create Python Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Run ASGI Server (Development Mode):**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

5. **Verify Installation:**
   * Open browser at `http://127.0.0.1:8000/docs` to test interactive Swagger documentation.