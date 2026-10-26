# Backend Documentation — Face Recognition Camera System SPD II

## Overview

The backend is a REST API built with **FastAPI** (Python) that provides real-time face recognition and scene change detection. It accepts base64-encoded images from the frontend camera feed, processes them using OpenCV and the `face_recognition` library (dlib), and returns detection results including alerts for person changes and scene changes.

---

## Tech Stack

| Component        | Technology                          |
|-----------------|-------------------------------------|
| Framework        | FastAPI                             |
| ASGI Server      | Uvicorn                             |
| ORM              | SQLAlchemy                          |
| Database         | PostgreSQL (SQLite for development) |
| Image Processing | OpenCV (`opencv-python-headless`)   |
| Face Recognition | `face-recognition` (dlib-based)     |
| Auth / Security  | python-jose (JWT), passlib (bcrypt) |
| Validation       | Pydantic, pydantic-settings         |
| Testing          | pytest, httpx                       |

---

## Project Structure

```
backend/
├── app/                          # Main application package
│   ├── __init__.py
│   ├── main.py                   # FastAPI entry point, CORS, app initialization
│   ├── config.py                 # Environment variables (Pydantic BaseSettings)
│   ├── database.py               # PostgreSQL/SQLite connection, SQLAlchemy session
│   ├── models.py                 # SQLAlchemy ORM models (User, FaceEncoding)
│   ├── schemas.py                # Pydantic request/response schemas
│   ├── api/
│   │   └── v1/
│   │       ├── api.py            # Router aggregator
│   │       ├── deps.py           # Dependency injection (DB session, auth)
│   │       └── endpoints/
│   │           ├── faces.py      # /faces/register, /faces/scan, /faces/{id}
│   │           ├── users.py      # /users/{id}
│   │           └── health.py     # /health
│   ├── services/
│   │   ├── face_recognition.py   # OpenCV & face-recognition integration
│   │   └── security.py           # JWT, password hashing, auth handlers
│   └── utils/
│       └── __init__.py           # Helper functions, logging
├── tests/
│   ├── conftest.py               # Pytest fixtures, test DB setup
│   ├── test_faces.py             # Tests for register and scan endpoints
│   └── test_health.py            # Tests for health check endpoint
├── requirements.txt
└── Dockerfile
```

---

## API Endpoints

### `GET /`
Health check root endpoint.

**Response:**
```json
{ "message": "Welcome to Face Recognition API" }
```

---

### `POST /api/recognize`
Main face recognition endpoint. Accepts a base64-encoded image and returns detection results with change alerts.

**Request body:**
```json
{
  "image": "<base64-encoded image string>"
}
```

**Response (face detected):**
```json
{
  "status": "success",
  "faces_found": 1,
  "alert": true,
  "alert_type": "person_changed",
  "scene_changed": false,
  "person_changed": true,
  "message": "Face processed successfully with change detection."
}
```

**Response (no face detected):**
```json
{
  "status": "no face detected",
  "faces_found": 0,
  "alert": false,
  "alert_type": null,
  "scene_changed": false
}
```

**Alert types:**

| alert_type                  | Description                                  |
|----------------------------|----------------------------------------------|
| `person_changed`           | A different person appeared in the frame     |
| `scene_changed`            | Camera view/scene changed significantly      |
| `scene_and_person_changed` | Both scene and person changed simultaneously |
| `person_left`              | Person was present but left the frame        |

---

## Database Models

### `User`
| Column            | Type    | Description              |
|-------------------|---------|--------------------------|
| id                | Integer | Primary key              |
| username          | String  | Unique username          |
| hashed_password   | String  | bcrypt hashed password   |
| is_active         | Boolean | Account active status    |

### `FaceEncoding`
| Column        | Type        | Description                        |
|---------------|-------------|------------------------------------|
| id            | Integer     | Primary key                        |
| user_id       | Integer     | Foreign key → users.id             |
| encoding_data | LargeBinary | Serialized numpy face encoding     |

---

## How to Run Locally

### 1. Navigate to backend folder
```bash
cd backend
```

### 2. Install dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Start the server
```bash
python3 -m uvicorn app.main:app --reload
```

### 4. Access the API
- API root: http://127.0.0.1:8000
- Interactive docs (Swagger): http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

---

## Environment Variables

| Variable       | Default                    | Description               |
|---------------|----------------------------|---------------------------|
| `DATABASE_URL` | `sqlite:///./sql_app.db`  | Database connection string |

For production with PostgreSQL:
```
DATABASE_URL=postgresql://user:password@localhost:5432/face_recognition_db
```

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

---

## CORS

Currently configured to allow all origins (`*`) for development. Restrict `allow_origins` in `app/main.py` before deploying to production.

---

## Notes

- Face encodings are stored in-memory during a session for real-time change detection (the `last_detection_state` dict in `main.py`). This resets on server restart.
- `dlib` compilation during `pip install` takes 10–20 minutes on first install — this is normal.
- The app uses SQLite by default. Switch to PostgreSQL via the `DATABASE_URL` environment variable for production.
