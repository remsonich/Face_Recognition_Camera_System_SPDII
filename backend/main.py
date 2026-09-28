from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import cv2
import numpy as np
import base64
import face_recognition

import models, schemas, database
import auth

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
        face_locations = face_recognition.face_locations(rgb_img)
        
        if not face_locations:
            return {"status": "no face detected", "faces_found": 0}
            
        # Get face encodings
        encodings = face_recognition.face_encodings(rgb_img, face_locations)
        
        # In a real app, you would retrieve encodings from the DB and compare:
        # stored_encodings = db.query(models.FaceEncoding).all()
        # for stored in stored_encodings:
        #     known_encoding = np.frombuffer(stored.encoding_data, dtype=np.float64)
        #     match = face_recognition.compare_faces([known_encoding], encodings[0])
        #     if match[0]:
        #         user = db.query(models.User).filter(models.User.id == stored.user_id).first()
        #         return {"status": "success", "user": user.username}
        
        return {
            "status": "success",
            "faces_found": len(face_locations),
            "message": "Face processed successfully. Match logic requires stored users."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
