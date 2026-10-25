# Quick Start: Audible Alert Feature 🔊

## 🎯 What This Does
Your Face Recognition System now alerts you with **sound** and **voice** when it detects:
- A different person in the camera
- A change in the scene/background
- Someone leaving the frame

## ⚡ Quick Start (3 Steps)

### 1️⃣ Start Backend
```bash
cd backend
uvicorn main:app --reload
```

### 2️⃣ Open Frontend
Open `frontend/index.html` in your browser

### 3️⃣ Start Monitoring
Click **"Start Continuous Monitoring"** button

**That's it!** Now walk around or have someone else enter the frame - you'll hear alerts! 🎵

## 🎵 What You'll Hear

| Event | Sound | Voice Says |
|-------|-------|------------|
| 👤 New person | High beep (C5) | "New person detected" |
| 🏞️ Scene changed | Medium beep (G4) | "Scene has changed" |
| 👤+🏞️ Both changed | Higher beep (E5) | "Scene and person changed" |
| 🚪 Person left | Lower beep (E4) | "Person has left the frame" |

## 🎮 Controls

### Continuous Mode (Recommended)
- **Start**: Click "Start Continuous Monitoring"
- Auto-captures every 2 seconds
- Alerts play automatically when changes detected
- **Stop**: Click "Stop Continuous Monitoring"

### Manual Mode
- Click "Capture & Recognize" to check once
- Good for testing specific scenarios

### Voice Control
- Click "Start Voice Command"
- Say "capture" or "recognize" to take a photo

## 📁 Documentation Files

Need more details? Check these files:

| File | What's Inside |
|------|---------------|
| `FEATURE_SUMMARY.md` | Complete feature overview |
| `AUDIBLE_ALERT_FEATURE.md` | Full technical documentation |
| `ALERT_FLOW_DIAGRAM.md` | Visual architecture diagrams |
| `TESTING_GUIDE.md` | Step-by-step testing instructions |
| `QUICK_START_ALERTS.md` | This file! |

## 🔧 Customize Alerts

### Make Detection More/Less Sensitive

**Edit `backend/main.py`:**

```python
# For person detection (lower = stricter)
tolerance=0.6  # Try 0.4 (stricter) or 0.8 (lenient)

# For scene detection (lower = more sensitive)
threshold=0.7  # Try 0.5 (more sensitive) or 0.85 (less sensitive)
```

### Change Monitoring Speed

**Edit `frontend/app.js`:**

```javascript
// Change 2000 to milliseconds you want
setInterval(async () => {
    await captureAndRecognize();
}, 2000);  // 2000 = 2 seconds

// Examples:
// 1000 = 1 second (faster)
// 5000 = 5 seconds (slower)
```

## 🐛 Troubleshooting

### No sound?
1. Check browser isn't muted
2. Check system volume
3. Click on the page first (browsers need user interaction)

### No voice announcements?
1. Try a different browser (Chrome works best)
2. Check internet connection
3. Open browser console for errors (F12)

### Too many alerts?
Increase threshold/tolerance in `backend/main.py`

### Missing real changes?
Decrease threshold/tolerance in `backend/main.py`

### Can't access camera?
- Must use `https://` or `localhost`
- Check browser camera permissions
- Make sure no other app is using the camera

## 🚀 Branch Information

```bash
# Current branch
git branch
# Should show: * audible-alert-feature

# See what changed
git diff main --stat

# Push to remote (optional)
git push -u origin audible-alert-feature

# Merge to main (when ready)
git checkout main
git merge audible-alert-feature
```

## 📊 Files Modified

- ✅ `backend/main.py` - Detection logic
- ✅ `frontend/app.js` - Alert system
- ✅ `frontend/index.html` - UI controls
- ✅ 5 documentation files

## ✨ What's New in Code

### Backend (`main.py`)
```python
# NEW: State tracking
last_detection_state = {
    "person_encoding": None,
    "scene_histogram": None,
    "face_count": 0
}

# NEW: Scene comparison function
def compare_scene_histograms(hist1, hist2, threshold=0.7)

# ENHANCED: /api/recognize now returns alert info
{
    "alert": true,
    "alert_type": "person_changed",
    "scene_changed": false,
    "person_changed": true
}
```

### Frontend (`app.js`)
```javascript
// NEW: Audio alert system
function playAlertSound(alertType)

// NEW: Voice announcement
function speakAlert(alertType)

// NEW: Continuous monitoring
let continuousMonitoring = false;
function toggleContinuousMonitoring()
```

## 🎓 How It Works (Simple)

1. **Camera** captures image every 2 seconds
2. **Backend** compares with previous image:
   - Checks if face encoding changed (different person)
   - Checks if color histogram changed (different scene)
3. **Frontend** receives result:
   - If change detected → Play sound + Speak + Highlight
   - If no change → Continue monitoring silently

## 💡 Pro Tips

- **Better accuracy**: Good lighting + face camera directly
- **Fewer false alerts**: Stay still for first capture to establish baseline
- **Test scenarios**: Have a friend help test person changes
- **Adjust timing**: Longer intervals (3-5 sec) reduce server load

## 🔐 Privacy Note

- ✅ All processing happens on your local machine
- ✅ Face encodings stored in memory only
- ✅ Nothing sent to external servers
- ✅ State resets when backend restarts

## 📞 Need Help?

1. Check `TESTING_GUIDE.md` for common issues
2. Open browser console (F12) to see errors
3. Check backend terminal for errors
4. Review `AUDIBLE_ALERT_FEATURE.md` for details

---

## 🎉 You're Ready!

The feature is fully implemented and documented. Just start the backend, open the frontend, and click "Start Continuous Monitoring" to see it in action!

**Enjoy your new alert system!** 🚀
