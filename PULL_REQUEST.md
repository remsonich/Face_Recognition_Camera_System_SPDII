# Pull Request: Backend Structure Refactor & Import Fix

## Summary

Restructured the backend codebase to follow a clean, production-ready layout and fixed a critical import error that prevented the server from starting.

---

## Changes Made

### 1. Fixed broken imports in `app/main.py`
- **Problem:** `main.py` used flat imports (`import models, schemas, database, auth`) that no longer resolved after the codebase was moved into the `app/` package.
- **Fix:** Updated to package-relative imports (`from app import models, schemas, database`) and removed the unused `import auth` line.

### 2. Created `app/models.py`
- This file was missing entirely — the ORM models only existed at `backend/models.py` (root level, stale).
- Created `app/models.py` with `User` and `FaceEncoding` SQLAlchemy models using the correct import path (`from app.database import Base`).

### 3. Moved `tests/` to correct location
- Moved `backend/app/tests/` → `backend/tests/`
- Tests should live outside the `app/` package per standard FastAPI/Python project convention.

### 4. Added backend documentation
- Created `backend/BACKEND_DOC.md` covering:
  - Tech stack
  - Project structure
  - API endpoints with request/response examples
  - Database models
  - How to run locally
  - Environment variables
  - Test instructions

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/main.py` | Fixed imports |
| `backend/app/models.py` | Created (was missing) |
| `backend/tests/` | Moved from `backend/app/tests/` |
| `backend/BACKEND_DOC.md` | Created (new documentation) |

---

## Files Still Pending Cleanup

| File | Action Needed |
|------|---------------|
| `backend/models.py` | Delete — replaced by `app/models.py` |
| `backend/config.py` | Delete or merge into `app/config.py` |
| `backend/Dockerfile` | Create — needed for containerization |

---

## How to Test

```bash
cd backend
python3 -m uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000/docs to verify the API is running.

---

## Notes for Reviewer

- The `app/config.py` file exists but is currently empty — it should be populated with Pydantic `BaseSettings` to manage environment variables (e.g., `DATABASE_URL`, `SECRET_KEY`).
- CORS is currently open (`allow_origins=["*"]`) — should be restricted before production deployment.
- The `SECRET_KEY` in `backend/config.py` is hardcoded — this must be moved to an environment variable before production.
- `app/services/security.py` and all endpoint files under `app/api/v1/endpoints/` are currently empty stubs — they need to be implemented in a follow-up.
