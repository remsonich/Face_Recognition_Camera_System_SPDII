"""
Face Recognition Service
Extracts face embeddings and performs face matching/identification
"""
import numpy as np
from typing import Optional, List, Tuple, Dict
import logging
import json
import cv2

logger = logging.getLogger(__name__)

# Lazy import of face_recognition
_face_recognition = None

def _get_face_recognition():
    global _face_recognition
    if _face_recognition is None:
        try:
            import face_recognition
            _face_recognition = face_recognition
        except ImportError as e:
            raise ImportError(f"face_recognition library not available: {e}")
    return _face_recognition


class FaceRecognizer:
    """
    Face recognition using embeddings with face_recognition library
    Supports extraction and matching of face embeddings
    """

    def __init__(self, model_name: str = "face_recognition", distance_metric: str = "cosine"):
        """
        Initialize Face Recognizer
        
        Args:
            model_name: Model type (currently always 'face_recognition')
            distance_metric: Distance metric for matching (cosine, euclidean)
        """
        try:
            self.face_recognition = _get_face_recognition()
            self.model_name = "face_recognition"
            self.distance_metric = distance_metric
            logger.info(f"Face recognizer initialized with {self.model_name} library")
        except Exception as e:
            logger.error(f"face_recognition library not available: {e}")
            raise

    def extract_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """
        Extract face embedding from image file
        
        Args:
            image_path: Path to image file containing a face
        
        Returns:
            Embedding vector as numpy array, or None if face not found
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError("Could not read image file")
            
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_locations = self.face_recognition.face_locations(rgb_img)
            
            if not face_locations:
                logger.warning(f"No face found in image: {image_path}")
                return None
            
            embeddings = self.face_recognition.face_encodings(rgb_img, face_locations)
            if embeddings:
                return embeddings[0]
            return None
                
        except Exception as e:
            logger.error(f"Error extracting embedding: {str(e)}")
            return None

    def extract_embedding_from_bytes(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """
        Extract face embedding from image bytes
        
        Args:
            image_bytes: Image data as bytes
        
        Returns:
            Embedding vector as numpy array, or None if face not found
        """
        try:
            # Decode image from bytes
            nparr = np.frombuffer(image_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img_bgr is None:
                raise ValueError("Invalid image data")
            
            # Convert BGR to RGB for face_recognition
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            # Using face_recognition library
            face_locations = self.face_recognition.face_locations(img_rgb)
            
            if not face_locations:
                logger.warning("No face found in image bytes")
                return None
            
            embeddings = self.face_recognition.face_encodings(img_rgb, face_locations)
            if embeddings:
                return embeddings[0]
            return None
                
        except Exception as e:
            logger.error(f"Error extracting embedding from bytes: {str(e)}")
            return None

    def extract_embedding_from_array(self, img_rgb: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract face embedding from already-decoded RGB numpy array
        
        Args:
            img_rgb: RGB image as numpy array
        
        Returns:
            Embedding vector as numpy array, or None if face not found
        """
        try:
            face_locations = self.face_recognition.face_locations(img_rgb)
            
            if not face_locations:
                logger.warning("No face found in image array")
                return None
            
            embeddings = self.face_recognition.face_encodings(img_rgb, face_locations)
            if embeddings:
                return embeddings[0]
            return None
                
        except Exception as e:
            logger.error(f"Error extracting embedding from array: {str(e)}")
            return None

    def match_embeddings(
        self, 
        embedding1: np.ndarray, 
        embedding2: np.ndarray,
        threshold: float = 0.75
    ) -> Tuple[bool, float]:
        """
        Compare two face embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            threshold: Matching threshold (0.0-1.0)
        
        Returns:
            Tuple of (match: bool, distance: float)
        """
        try:
            if embedding1 is None or embedding2 is None:
                return False, 1.0
            
            # Calculate cosine distance
            distance = self._cosine_distance(embedding1, embedding2)
            match = distance <= (1.0 - threshold)  # Convert threshold to distance
            
            logger.info(f"Embedding comparison - Distance: {distance:.4f}, Match: {match}")
            return match, distance
            
        except Exception as e:
            logger.error(f"Error comparing embeddings: {str(e)}")
            return False, 1.0

    def match_against_embeddings(
        self,
        query_embedding: np.ndarray,
        stored_embeddings: List[np.ndarray],
        threshold: float = 0.75
    ) -> Tuple[bool, Optional[int], float]:
        """
        Match query embedding against list of stored embeddings
        
        Args:
            query_embedding: Query face embedding
            stored_embeddings: List of stored embeddings
            threshold: Matching threshold
        
        Returns:
            Tuple of (matched: bool, best_match_idx: Optional[int], best_distance: float)
        """
        try:
            if not stored_embeddings:
                return False, None, 1.0
            
            best_distance = float('inf')
            best_idx = None
            threshold_distance = 1.0 - threshold
            
            for idx, stored_emb in enumerate(stored_embeddings):
                distance = self._cosine_distance(query_embedding, stored_emb)
                
                if distance < best_distance:
                    best_distance = distance
                    best_idx = idx
            
            matched = best_distance <= threshold_distance
            logger.info(f"Found best match at idx {best_idx} with distance {best_distance:.4f}")
            
            return matched, best_idx, best_distance
            
        except Exception as e:
            logger.error(f"Error matching embeddings: {str(e)}")
            return False, None, 1.0

    @staticmethod
    def _cosine_distance(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine distance between two vectors
        
        Args:
            vec1: First vector
            vec2: Second vector
        
        Returns:
            Cosine distance (0.0-1.0)
        """
        try:
            # Normalize vectors
            vec1_norm = vec1 / np.linalg.norm(vec1)
            vec2_norm = vec2 / np.linalg.norm(vec2)
            
            # Calculate cosine similarity
            similarity = np.dot(vec1_norm, vec2_norm)
            
            # Convert to distance (1 - similarity)
            distance = 1 - similarity
            
            return float(np.clip(distance, 0.0, 1.0))
        except Exception as e:
            logger.error(f"Error calculating cosine distance: {str(e)}")
            return 1.0

    @staticmethod
    def embedding_to_json(embedding: np.ndarray) -> str:
        """Convert embedding to JSON string"""
        return json.dumps(embedding.tolist())

    @staticmethod
    def embedding_from_json(json_str: str) -> np.ndarray:
        """Convert JSON string to embedding array"""
        return np.array(json.loads(json_str))

    @staticmethod
    def embedding_to_bytes(embedding: np.ndarray) -> bytes:
        """Convert embedding to bytes"""
        return embedding.tobytes()

    @staticmethod
    def embedding_from_bytes(embedding_bytes: bytes) -> np.ndarray:
        """Convert bytes to embedding array"""
        # Assuming 128-dimensional embedding (face_recognition default)
        return np.frombuffer(embedding_bytes, dtype=np.float64).reshape(-1)
