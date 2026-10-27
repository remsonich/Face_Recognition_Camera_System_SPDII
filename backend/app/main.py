from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import cv2
import numpy as np
import base64
import face_recognition

from app import models, schemas, database

# Create tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="Face Recognition API",
    description="API for Face Recognition System",
    version="1.0.0"
)

# CORS setup
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

@app.get("/")
def read_root():
    return {"message": "Welcome to Face Recognition API"}

# Store for tracking the last detected state
last_detection_state = {
    "person_encoding": None,
    "scene_histogram": None,
    "face_count": 0
}

def compare_scene_histograms(hist1, hist2, threshold=0.7):
    """Compare two scene histograms to detect scene change"""
    if hist1 is None or hist2 is None:
        return False
    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    return correlation < threshold  # True if scene changed significantly

@app.post("/api/recognize")
def recognize_face(request: schemas.RecognitionRequest, db: Session = Depends(get_db)):
    try:
        # Decode base64 image
        if "," in request.image:
            header, encoded = request.image.split(",", 1)
        else:
            encoded = request.image
            
        image_data = base64.b64decode(encoded)
        
        # Convert to numpy array for OpenCV
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
            
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Calculate scene histogram for scene change detection
        hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        scene_histogram = cv2.calcHist([hsv_img], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(scene_histogram, scene_histogram)
        
        face_locations = face_recognition.face_locations(rgb_img)
        
        # Check for changes
        scene_changed = compare_scene_histograms(last_detection_state["scene_histogram"], scene_histogram)
        person_changed = False
        alert_type = None
        
        if not face_locations:
            # No face detected
            if last_detection_state["face_count"] > 0:
                alert_type = "person_left"
            last_detection_state["face_count"] = 0
            last_detection_state["person_encoding"] = None
            last_detection_state["scene_histogram"] = scene_histogram
            
            return {
                "status": "no face detected", 
                "faces_found": 0,
                "alert": alert_type is not None,
                "alert_type": alert_type,
                "scene_changed": scene_changed
            }
            
        # Get face encodings
        encodings = face_recognition.face_encodings(rgb_img, face_locations)
        
        if encodings:
            current_encoding = encodings[0]
            
            # Compare with last detected person
            if last_detection_state["person_encoding"] is not None:
                matches = face_recognition.compare_faces(
                    [last_detection_state["person_encoding"]], 
                    current_encoding,
                    tolerance=0.6
                )
                person_changed = not matches[0]
            else:
                person_changed = True  # First detection
            
            # Update state
            if person_changed or len(face_locations) != last_detection_state["face_count"]:
                last_detection_state["person_encoding"] = current_encoding
                alert_type = "person_changed"
        
        last_detection_state["face_count"] = len(face_locations)
        last_detection_state["scene_histogram"] = scene_histogram
        
        # Determine alert type
        if scene_changed and person_changed:
            alert_type = "scene_and_person_changed"
        elif scene_changed:
            alert_type = "scene_changed"
        elif person_changed:
            alert_type = "person_changed"
        
        return {
            "status": "success",
            "faces_found": len(face_locations),
            "alert": alert_type is not None,
            "alert_type": alert_type,
            "scene_changed": scene_changed,
            "person_changed": person_changed,
            "message": "Face processed successfully with change detection."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
