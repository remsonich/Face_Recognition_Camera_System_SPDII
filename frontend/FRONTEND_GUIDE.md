# Frontend Guide - Face Recognition Camera System

## 🎯 Overview

The frontend is a complete web application that connects to your FastAPI backend for real-time face recognition and access control. Built with HTML5, CSS3, and vanilla JavaScript.

---

## 📋 Features

✅ **Real-time Camera Access** - WebRTC integration for live video  
✅ **Face Detection & Recognition** - Scan faces against registered users  
✅ **User Registration** - Register new users with face biometrics  
✅ **User Management** - View all registered users  
✅ **Responsive Design** - Works on desktop, tablet, and mobile  
✅ **Real-time Status Updates** - Live feedback on all operations  
✅ **API Connection Status** - Monitor backend connectivity  

---

## 🚀 How to Run

### 1. Start Backend Server
```bash
cd backend/
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Open Frontend in Browser
Simply open `frontend/index.html` in your web browser:
```bash
# On macOS
open /Users/moengmix/Desktop/Face_Recognition_Camera_System_SPDII/frontend/index.html

# Or drag and drop index.html into your browser
```

Or serve via local web server:
```bash
cd frontend/
python3 -m http.server 8080
# Then open: http://localhost:8080
```

---

## 📁 Frontend Files

```
frontend/
├── index.html          # Main HTML structure
├── app.js              # JavaScript API integration & logic
├── style.css           # Complete styling
└── FRONTEND_GUIDE.md   # This file
```

---

## 🎮 User Interface

### Header Section
- **Status Badge** - Shows API connection status (Connected/Disconnected)
- **Subtitle** - System description

### Video Section
- **Live Video Feed** - Real-time camera stream
- **Scan Face Button** - Capture and recognize face
- **Register User Button** - Start user registration
- **Start/Stop Camera Button** - Toggle camera on/off

### Status Panel
- **System Status** - Current operation status
- **Recognition Results** - Results of face scanning

### Users Panel
- **Registered Users List** - All users in the system
- **Refresh Users Button** - Reload user list

### Registration Form (Hidden by Default)
- **Username** - Unique identifier
- **Full Name** - User's full name
- **Password** - Account password
- **Role** - User role (Employee/Manager/Admin)

---

## 🔌 API Integration

### Backend API Endpoints Used

#### Face Recognition
```javascript
// Scan face for recognition
POST /api/v1/faces/scan
Content-Type: multipart/form-data
Body: { file: <image> }

// Register new user with face
POST /api/v1/faces/register
Content-Type: application/json
Body: {
  username: string,
  full_name: string,
  password: string,
  role: string,
  image: base64string
}
```

#### Users Management
```javascript
// Get all users
GET /api/v1/users/

// Get specific user
GET /api/v1/users/{user_id}

// Create user
POST /api/v1/users/
Content-Type: application/json
Body: {
  username: string,
  password: string,
  full_name: string,
  role: string
}
```

#### Health Check
```javascript
// Check API status
GET /api/v1/health/
```

---

## 📱 Workflow

### 1. Scan Face for Access Control

```
1. Click "Start Camera" button
   ↓
2. Allow camera access in browser permission
   ↓
3. Camera stream appears in video element
   ↓
4. Click "Scan Face" button
   ↓
5. Image captured from video
   ↓
6. Sent to backend /faces/scan endpoint
   ↓
7. Backend processes with YOLO + embeddings
   ↓
8. Result displayed (Recognized/Unknown)
```

### 2. Register New User

```
1. Click "Start Camera" button
   ↓
2. Allow camera access
   ↓
3. Click "Register User" button
   ↓
4. Image captured
   ↓
5. Registration form appears
   ↓
6. Fill in: Username, Full Name, Password, Role
   ↓
7. Click "Register User"
   ↓
8. Sent to backend /faces/register endpoint
   ↓
9. Backend stores user with face embedding
   ↓
10. Success message displayed
   ↓
11. User added to Users list
```

### 3. View Registered Users

```
1. Refresh page or click "Refresh Users"
   ↓
2. Users list loads from backend
   ↓
3. Each user card shows:
   - Username & Full Name
   - Role (Employee/Manager/Admin)
   - Registration date
   - Status (Active/Inactive)
```

---

## 🔧 Configuration

### API Server Address

In `app.js`, line 5-6:
```javascript
const API_URL = 'http://localhost:8000';
const API_V1 = `${API_URL}/api/v1`;
```

**Change if backend runs on different host/port:**
```javascript
// Example: running on 192.168.1.100:3000
const API_URL = 'http://192.168.1.100:3000';
```

### Camera Constraints

In `app.js`, `startCamera()` function:
```javascript
video: { 
    facingMode: 'user',
    width: { ideal: 1280 },
    height: { ideal: 720 }
}
```

---

## 🎨 Customization

### Colors
Edit `style.css` CSS variables:
```css
:root {
    --primary-color: #4a90e2;      /* Main color */
    --success-color: #27ae60;      /* Success messages */
    --danger-color: #e74c3c;       /* Error messages */
    --background-color: #ecf0f1;   /* Page background */
}
```

### Fonts
Change in `style.css`:
```css
body {
    font-family: 'Your-Font-Here', sans-serif;
}
```

### Layout
Modify CSS grid and flexbox in `style.css` for different layouts.

---

## 🐛 Troubleshooting

### Camera Not Working
- **Issue:** Camera permission denied
- **Solution:** 
  1. Check browser permissions (Settings → Privacy → Camera)
  2. Reload page and grant permission
  3. Try different browser (Chrome, Firefox, Safari)

### "Connecting..." Badge Never Disappears
- **Issue:** Backend API not running
- **Solution:**
  1. Verify backend is running: `http://localhost:8000/api/v1/health/`
  2. Check backend logs in terminal
  3. Ensure no firewall blocking port 8000

### Face Recognition Returns "Unknown"
- **Issue:** Face not in database or low confidence
- **Solution:**
  1. Register the face properly using "Register User"
  2. Ensure face is clearly visible in camera
  3. Good lighting is important
  4. Try different angle

### "Failed to load users"
- **Issue:** Users endpoint error
- **Solution:**
  1. Check backend /users/ endpoint is working
  2. Look for errors in browser console (F12)
  3. Check backend server logs

### CORS Errors
- **Issue:** "Access to XMLHttpRequest blocked by CORS"
- **Solution:**
  1. Backend CORS is already configured
  2. Verify API URL is correct in `app.js`
  3. Check if backend is running on correct port

---

## 🔐 Security Notes

✅ **HTTPS Recommended** - Use HTTPS in production  
✅ **CORS Configured** - Backend allows frontend requests  
✅ **Input Validation** - Frontend validates before sending  
✅ **No Secrets in Frontend** - No hardcoded credentials  

---

## 📊 Browser Compatibility

| Feature | Chrome | Firefox | Safari | Edge |
|---------|--------|---------|--------|------|
| WebRTC | ✅ | ✅ | ✅ | ✅ |
| Canvas | ✅ | ✅ | ✅ | ✅ |
| Fetch API | ✅ | ✅ | ✅ | ✅ |
| getUserMedia | ✅ | ✅ | ✅ | ✅ |

**Recommended:** Chrome or Firefox for best compatibility

---

## 📈 Performance Tips

1. **Optimize Images**
   - Frontend compresses images to 0.9 quality
   - Reduces upload size

2. **Connection**
   - Faster network = quicker recognition
   - 1+ Mbps recommended

3. **Camera Quality**
   - 1280x720 optimal resolution
   - Adjust in `startCamera()` function

---

## 🚀 Deployment

### Local Network Access
```bash
# Find your IP
ipconfig getifaddr en0  # macOS
hostname -I             # Linux

# Serve frontend from IP:
python3 -m http.server 8080

# Access from another device:
http://<your-ip>:8080
```

### Production Deployment

1. **Use HTTPS**
   - Get SSL certificate
   - Update API_URL to use HTTPS

2. **Deploy Backend**
   - Use Gunicorn/uWSGI
   - Setup reverse proxy (Nginx)

3. **Serve Frontend**
   - Use web server (Apache, Nginx)
   - Or static hosting (GitHub Pages, Vercel)

---

## 📝 API Response Examples

### Successful Face Recognition
```json
{
  "status": "success",
  "faces_found": 1,
  "recognized": true,
  "user_id": 1,
  "username": "john_doe",
  "confidence": 0.95,
  "message": "Access granted to John Doe"
}
```

### Face Not Recognized
```json
{
  "status": "unknown",
  "faces_found": 1,
  "recognized": false,
  "confidence": 0.45,
  "message": "Face not recognized - Access denied"
}
```

### User Registration Success
```json
{
  "user_id": 1,
  "username": "john_doe",
  "status": "success",
  "message": "User 'john_doe' registered with face recognition",
  "encoding_id": 1
}
```

---

## 📞 Support

For issues:
1. Check browser console (F12) for JavaScript errors
2. Check network tab to see API responses
3. Verify backend logs
4. Review this guide's troubleshooting section

---

## ✨ Frontend Features Summary

✅ Real-time camera integration (WebRTC)  
✅ Face capture and recognition  
✅ User registration with biometrics  
✅ User list management  
✅ API status monitoring  
✅ Responsive mobile-friendly design  
✅ Error handling and user feedback  
✅ Production-ready code  

---

**Frontend Version:** 1.0.0  
**Last Updated:** October 31, 2026  
**Status:** ✅ READY FOR DEPLOYMENT
