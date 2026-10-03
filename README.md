# Face Recognition Camera System SPD II

just start communication 
sonet xxx
sonet gg

## Setup Instructions

### Backend (FastAPI)

1. Navigate to the backend folder:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the backend server:
   ```bash
   uvicorn main:app --reload
   ```

### Frontend

1. Navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Open `index.html` in your browser or run a simple local web server:
   ```bash
   python -m http.server 8080
   ```
