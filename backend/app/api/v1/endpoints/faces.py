"""
Face Recognition and Management Endpoints
Handles face detection, registration, deletion, and access control
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
import base64
import logging
import cv2
import os
import tempfile
from typing import List

from app.database import get_db
from app import models, schemas
from app.services.face_detector import YOLOFaceDetector
from app.services.face_recognizer import FaceRecognizer
from app.services.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize face detection and recognition services
try:
    detector = YOLOFaceDetector(conf_threshold=0.6)
    recognizer = FaceRecognizer(model_name="face_recognition")
except Exception as e:
    logger.warning(f"Face services not fully initialized: {str(e)}")
    detector = None
    recognizer = None


@router.post(
    "/scan",
    response_model=schemas.RecognitionResponse,
    summary="Scan face for access control",
    tags=["Faces"]
)
async def scan_face(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
) -> schemas.RecognitionResponse:
    """
    Scan and identify face in uploaded image
    
    - Detects faces using YOLO
    - Extracts embeddings
    - Matches against registered users
    - Logs access attempt
    """
    try:
        if not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must be an image (JPEG, PNG, etc.)"
            )

        # Read image file
        image_data = await file.read()
        
        # Detect faces
        if detector is None:
            raise HTTPException(
                status_code=500,
                detail="Face detection service not initialized"
            )
        
        original_img, detections = detector.detect(image_data)
        
        if not detections:
            # Log no face detected
            access_log = models.AccessLog(
                user_id=None,
                match_status="NO_FACE",
                confidence=0.0,
                bounding_box=None
            )
            db.add(access_log)
            db.commit()
            
            return schemas.RecognitionResponse(
                status="no_face",
                faces_found=0,
                recognized=False,
                confidence=0.0,
                message="No face detected in the image"
            )
        
        # Process primary face
        primary_detection = detections[0]
        face_crop = primary_detection["crop"]
        confidence = primary_detection["confidence"]
        bounding_box = primary_detection["bounding_box"]
        
        # Extract embedding from detected face
        if recognizer is None:
            raise HTTPException(
                status_code=500,
                detail="Face recognition service not initialized"
            )
        
        # Convert BGR to RGB and extract embedding directly
        face_crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        query_embedding = recognizer.extract_embedding_from_array(face_crop_rgb)
        
        if query_embedding is None:
            access_log = models.AccessLog(
                user_id=None,
                match_status="NO_FACE",
                confidence=float(confidence),
                bounding_box=bounding_box
            )
            db.add(access_log)
            db.commit()
            
            return schemas.RecognitionResponse(
                status="unknown",
                faces_found=1,
                recognized=False,
                confidence=float(confidence),
                bounding_boxes=[bounding_box],
                message="Face detected but embedding extraction failed"
            )
        
        # Get all registered face encodings
        face_encodings = db.query(models.FaceEncoding).all()
        
        if not face_encodings:
            access_log = models.AccessLog(
                user_id=None,
                match_status="UNKNOWN",
                confidence=float(confidence),
                bounding_box=bounding_box
            )
            db.add(access_log)
            db.commit()
            
            return schemas.RecognitionResponse(
                status="unknown",
                faces_found=1,
                recognized=False,
                confidence=float(confidence),
                bounding_boxes=[bounding_box],
                message="No registered faces in database"
            )
        
        # Compare with all registered embeddings
        stored_embeddings = [
            FaceRecognizer.embedding_from_json(enc.embedding_data)
            for enc in face_encodings if enc.embedding_data
        ]
        
        matched, best_idx, distance = recognizer.match_against_embeddings(
            query_embedding,
            stored_embeddings,
            threshold=0.75
        )
        
        if matched and best_idx is not None:
            matched_encoding = face_encodings[best_idx]
            user = matched_encoding.user
            
            # Log successful match
            access_log = models.AccessLog(
                user_id=user.id,
                match_status="SUCCESS",
                confidence=float(1.0 - distance),
                bounding_box=bounding_box
            )
            db.add(access_log)
            db.commit()
            
            return schemas.RecognitionResponse(
                status="success",
                faces_found=1,
                recognized=True,
                user_id=user.id,
                username=user.username,
                confidence=float(1.0 - distance),
                bounding_boxes=[bounding_box],
                message=f"Access granted to {user.full_name or user.username}"
            )
        else:
            # Log unknown face
            access_log = models.AccessLog(
                user_id=None,
                match_status="UNKNOWN",
                confidence=float(1.0 - distance) if best_idx is not None else 0.0,
                bounding_box=bounding_box
            )
            db.add(access_log)
            db.commit()
            
            return schemas.RecognitionResponse(
                status="unknown",
                faces_found=1,
                recognized=False,
                confidence=float(1.0 - distance) if best_idx is not None else 0.0,
                bounding_boxes=[bounding_box],
                message="Face not recognized - Access denied"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in face scan: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Face scan failed: {str(e)}")


@router.post(
    "/register",
    response_model=schemas.FaceRegistrationResponse,
    summary="Register new user with face",
    tags=["Faces"]
)
async def register_face(
    request: schemas.FaceRegistrationRequest,
    db: Session = Depends(get_db)
) -> schemas.FaceRegistrationResponse:
    """
    Register a new user with face recognition data
    
    - Detects face in image
    - Extracts face embedding
    - Creates user account
    - Stores embedding in database
    """
    try:
        # Check if user already exists
        existing_user = db.query(models.User).filter(
            models.User.username == request.username
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail=f"Username '{request.username}' already exists"
            )
        
        # Decode base64 image
        if "," in request.image:
            _, encoded = request.image.split(",", 1)
        else:
            encoded = request.image
        
        image_data = base64.b64decode(encoded)
        
        # Detect face
        if detector is None:
            raise HTTPException(status_code=500, detail="Face detection service not initialized")
        
        original_img, detections = detector.detect(image_data)
        
        if not detections:
            raise HTTPException(status_code=400, detail="No face detected in image")
        
        # Process primary face
        primary_detection = detections[0]
        face_crop = primary_detection["crop"]
        
        # Extract embedding
        if recognizer is None:
            raise HTTPException(status_code=500, detail="Face recognition service not initialized")
        
        # Convert BGR to RGB and extract embedding directly
        face_crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
        embedding = recognizer.extract_embedding_from_array(face_crop_rgb)
        
        if embedding is None:
            raise HTTPException(
                status_code=400,
                detail="Could not extract face embedding from image"
            )
        
        # Create user
        hashed_password = hash_password(request.password) if request.password else hash_password(request.username)
        
        user = models.User(
            username=request.username,
            full_name=request.full_name or request.username,
            hashed_password=hashed_password,
            role=request.role,
            is_active=True
        )
        db.add(user)
        db.flush()  # Get user.id without commit
        
        # Store face encoding
        embedding_json = FaceRecognizer.embedding_to_json(embedding)
        
        face_encoding = models.FaceEncoding(
            user_id=user.id,
            embedding_data=embedding_json,
            confidence=float(primary_detection["confidence"])
        )
        db.add(face_encoding)
        db.commit()
        
        logger.info(f"User '{request.username}' registered successfully")
        
        return schemas.FaceRegistrationResponse(
            user_id=user.id,
            username=request.username,
            status="success",
            message=f"User '{request.username}' registered with face recognition",
            encoding_id=face_encoding.id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error in face registration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.delete(
    "/{encoding_id}",
    response_model=schemas.FaceDeletionResponse,
    summary="Delete face encoding",
    tags=["Faces"]
)
async def delete_face(
    encoding_id: int,
    db: Session = Depends(get_db)
) -> schemas.FaceDeletionResponse:
    """
    Delete a face encoding from database
    Useful for privacy compliance and data removal
    """
    try:
        face_encoding = db.query(models.FaceEncoding).filter(
            models.FaceEncoding.id == encoding_id
        ).first()
        
        if not face_encoding:
            raise HTTPException(status_code=404, detail="Face encoding not found")
        
        user_id = face_encoding.user_id
        db.delete(face_encoding)
        
        # Check if user has other encodings
        remaining_encodings = db.query(models.FaceEncoding).filter(
            models.FaceEncoding.user_id == user_id
        ).count()
        
        db.commit()
        
        logger.info(f"Face encoding {encoding_id} deleted")
        
        return schemas.FaceDeletionResponse(
            status="success",
            deleted_encodings=1,
            message=f"Face encoding deleted. User has {remaining_encodings} remaining encodings"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting face encoding: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")
