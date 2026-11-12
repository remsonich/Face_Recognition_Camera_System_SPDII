# Face Recognition & Intruder Alert System (SPD II)

A real-time intelligent face recognition and security surveillance system built with **FastAPI**, **dlib / face_recognition**, **OpenCV**, and a responsive modern web dashboard.

---

## 🌟 Key Features

1. **Face Training & Database Storage**:
   - Register users with their name, role, and multiple sample face photos (1–5 photos recommended).
   - Generates 128-dimensional facial embeddings and stores them securely in an SQLite database.
   - Stores user thumbnails and allows reviewing or deleting registered profiles directly from the dashboard.

2. **Real-Time Recognition & Authorized Verification**:
   - Compares detected faces against database encodings using Euclidean distance matching.
   - Shows authorized badges with user identity, role, and verification confidence score.

3. **Intruder / Unknown Person Alert**:
   - Instantly triggers an alert when an unrecognized (anonymous) face appears in the camera frame.
   - Dual-tone audible security siren and synthetic voice warning in English or Khmer.
   - Visual red warning cards on the live monitor and logged to alert history.

4. **Telegram Bot Real-Time Alerts**:
   - Sends an instant security notification directly to your Telegram with the intruder's photo, timestamp, and detected details.
   - Built-in rate limiting (30-second cooldown) to avoid spamming alerts.
   - Configure your Bot Token and Chat ID directly in the UI with a one-click test message button!

---

## 🚀 Quick Start Guide

### 1. Start the Backend (Terminal 1)

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```
- API Server: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Start the Frontend (Terminal 2)

```powershell
cd frontend
python -m http.server 8080
```
- Open your browser at: 👉 **[http://localhost:8080](http://localhost:8080)**

---

## 🤖 Telegram Bot Setup (1 Minute)

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`, name your bot, and copy your **Bot Token** (e.g. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
3. Search for **@userinfobot** or click Start on your new bot to find your **Chat ID** (e.g. `987654321`).
4. In the web dashboard, click **កំណត់ Telegram (Telegram Settings)** in the left sidebar.
5. Paste your Bot Token and Chat ID, and click **«ផ្ញើសារសាកល្បង» (Send Test Message)** to verify!
