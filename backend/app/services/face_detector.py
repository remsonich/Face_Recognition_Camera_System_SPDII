"""
YOLO Face Detection Service
Detects faces in images using YOLOv8 model with Haar cascade fallback
"""
import cv2
import numpy as np
from typing import Tuple, List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class YOLOFaceDetector:
    """
    Face detection using YOLOv8 model with Haar cascade fallback
    Returns face crops and bounding boxes with confidence scores
    """

    def __init__(self, model_path: str = "models/yolov8n-face.pt", conf_threshold: float = 0.6):
        """
        Initialize YOLO Face Detector with fallback to Haar cascade
        
        Args:
            model_path: Path to YOLOv8 face model weights (optional, will try auto-download)
            conf_threshold: Confidence threshold for detection (0.0-1.0)
        """
        self.conf_threshold = conf_threshold
        self.backend = None
        self.model = None
        self.cascade = None
        
        # Try to load YOLO first
        try:
            from ultralytics import YOLO
            try:
                # Try with provided path first
                self.model = YOLO(model_path)
                self.backend = "yolo_file"
                logger.info(f"YOLO model loaded from {model_path}")
            except Exception:
                # Fall back to auto-download of yolov8n.pt
                logger.info("Attempting to auto-download YOLOv8n model...")
                self.model = YOLO('yolov8n.pt')
                self.backend = "yolo_auto"
                logger.info("YOLO model auto-downloaded successfully")
        except ImportError:
            logger.warning("ultralytics package not available, will use Haar cascade fallback")
            self.backend = None
        except Exception as e:
            logger.warning(f"YOLO loading failed ({str(e)}), will use Haar cascade fallback")
            self.backend = None
        
        # If YOLO didn't work, load Haar cascade
        if self.backend is None:
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                self.cascade = cv2.CascadeClassifier(cascade_path)
                if self.cascade.empty():
                    logger.error(f"Failed to load Haar cascade from {cascade_path}")
                    raise ValueError("Could not load Haar cascade classifier")
                self.backend = "haar"
                logger.info("Using Haar cascade classifier for face detection")
            except Exception as e:
                logger.error(f"Failed to initialize Haar cascade: {str(e)}")
                raise RuntimeError("Neither YOLO nor Haar cascade could be initialized")

    def detect(self, image_bytes: bytes) -> Tuple[np.ndarray, List[Dict]]:
        """
        Detect faces in image using YOLO or Haar cascade
        
        Args:
            image_bytes: Image data as bytes (JPEG/PNG)
        
        Returns:
            Tuple of (original_image, list of detections)
            Each detection contains: bounding_box, confidence, crop, crop_bytes
        
        Raises:
            ValueError: If image is invalid
        """
        try:
            # Decode image from bytes
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Invalid image file format")

            detections = []
            
            if self.backend and self.backend.startswith("yolo"):
                # Use YOLO detection
                detections = self._detect_with_yolo(img)
            else:
                # Use Haar cascade detection
                detections = self._detect_with_haar(img)

            logger.info(f"Detected {len(detections)} faces using {self.backend} backend")
            return img, detections

        except ValueError as ve:
            logger.error(f"Invalid image data: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Error in face detection: {str(e)}")
            raise Exception(f"Face detection failed: {str(e)}")

    def _detect_with_yolo(self, img: np.ndarray) -> List[Dict]:
        """Detect faces using YOLO model"""
        detections = []
        try:
            results = self.model(img)
            
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    
                    # Filter by confidence threshold
                    if conf >= self.conf_threshold:
                        # Get bounding box coordinates
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # Ensure coordinates are within image bounds
                        h, w = img.shape[:2]
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(w, x2), min(h, y2)
                        
                        # Extract face crop
                        face_crop = img[y1:y2, x1:x2].copy()
                        
                        detections.append({
                            "bounding_box": [x1, y1, x2, y2],
                            "confidence": round(conf, 4),
                            "crop": face_crop,
                            "crop_bytes": cv2.imencode('.jpg', face_crop)[1].tobytes()
                        })
        except Exception as e:
            logger.warning(f"YOLO detection failed: {str(e)}, falling back to Haar cascade")
            # Fall back to Haar if YOLO fails
            if self.cascade is not None:
                detections = self._detect_with_haar(img)
        
        return detections

    def _detect_with_haar(self, img: np.ndarray) -> List[Dict]:
        """Detect faces using Haar cascade classifier"""
        detections = []
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Detect faces
            faces = self.cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            h, w = img.shape[:2]
            
            for (x1, y1, width, height) in faces:
                x2 = x1 + width
                y2 = y1 + height
                
                # Ensure coordinates are within bounds
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                
                # Extract face crop
                face_crop = img[y1:y2, x1:x2].copy()
                
                detections.append({
                    "bounding_box": [x1, y1, x2, y2],
                    "confidence": 0.85,  # Haar doesn't provide confidence, use fixed value
                    "crop": face_crop,
                    "crop_bytes": cv2.imencode('.jpg', face_crop)[1].tobytes()
                })
        except Exception as e:
            logger.error(f"Haar cascade detection failed: {str(e)}")
        
        return detections

    def detect_from_file(self, image_path: str) -> Tuple[np.ndarray, List[Dict]]:
        """
        Detect faces from image file path
        
        Args:
            image_path: Path to image file
        
        Returns:
            Tuple of (original_image, list of detections)
        """
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            return self.detect(image_bytes)
        except FileNotFoundError:
            logger.error(f"Image file not found: {image_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading image file: {str(e)}")
            raise
