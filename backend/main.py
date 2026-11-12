"""
Main application entry point.
Exposes the FastAPI app from the app package so both:
  uvicorn main:app --reload
  uvicorn app.main:app --reload
work seamlessly.
"""
from app.main import app, get_db, read_root, recognize_face, last_detection_state

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
