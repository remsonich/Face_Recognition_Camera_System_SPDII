# Audible Alert Feature

## Overview
This feature provides audible alerts to inform you of changes when the camera detects a different scene or a different person.

## Features

### 1. **Person Change Detection**
- Detects when a different person appears in the camera view
- Uses face encoding comparison to identify if the person has changed
- Tolerance: 0.6 (configurable in backend)

### 2. **Scene Change Detection**
- Monitors the overall scene using HSV color histogram analysis
- Detects significant changes in the environment
- Threshold: 0.7 correlation (configurable in backend)

### 3. **Multi-Modal Alerts**
When a change is detected, the system provides:
- **Audio Tone Alert**: Different frequency tones for different alert types
- **Voice Announcement**: Text-to-speech announces the type of change detected
- **Visual Feedback**: Yellow highlight on the result panel for 2 seconds

### 4. **Alert Types**
The system distinguishes between:
- `person_changed`: A new person detected (523.25 Hz - C5)
- `scene_changed`: Background/environment changed (392.00 Hz - G4)
- `scene_and_person_changed`: Both changed simultaneously (659.25 Hz - E5)
- `person_left`: Person left the frame (329.63 Hz - E4)

### 5. **Continuous Monitoring Mode**
- Toggle continuous monitoring with a single button
- Automatically captures and analyzes frames every 2 seconds
- Real-time alerts for any detected changes
- Can be started/stopped at any time

## Technical Implementation

### Backend Changes (`main.py`)
- Added `last_detection_state` dictionary to track:
  - Previous person's face encoding
  - Previous scene histogram
  - Previous face count
- Implemented `compare_scene_histograms()` function for scene comparison
- Enhanced `/api/recognize` endpoint to return:
  - `alert`: Boolean indicating if alert should be triggered
  - `alert_type`: Type of change detected
  - `scene_changed`: Boolean for scene change
  - `person_changed`: Boolean for person change

### Frontend Changes (`app.js`)
- **Audio System**: Web Audio API for tone generation
  - Different frequencies for different alert types
  - Smooth fade-in/fade-out envelope
- **Voice System**: Web Speech Synthesis API
  - Natural language announcements
  - Clear descriptions of detected changes
- **Continuous Monitoring**: 
  - Interval-based automatic capture
  - Toggle functionality with visual feedback
- **Visual Feedback**: Background color change on detection

### UI Changes (`index.html`)
- Added "Start/Stop Continuous Monitoring" button
- Button color changes based on monitoring state

## Usage

### Manual Mode
1. Click "Capture & Recognize" to analyze a single frame
2. If a change is detected, you'll hear a tone and voice alert

### Continuous Monitoring Mode
1. Click "Start Continuous Monitoring"
2. The system will automatically check for changes every 2 seconds
3. You'll receive alerts whenever a person or scene changes
4. Click "Stop Continuous Monitoring" to deactivate

### Voice Command (Optional)
1. Click "Start Voice Command"
2. Say "capture" or "recognize" to trigger recognition

## Configuration

### Backend Configuration
In `backend/main.py`, you can adjust:
```python
# Face recognition tolerance (lower = more strict)
face_recognition.compare_faces(..., tolerance=0.6)

# Scene change threshold (lower = more sensitive)
def compare_scene_histograms(hist1, hist2, threshold=0.7)
```

### Frontend Configuration
In `frontend/app.js`, you can adjust:
```javascript
// Monitoring interval (in milliseconds)
setInterval(async () => { ... }, 2000);

// Alert tone frequencies and durations
frequency = 523.25;  // Adjust tone pitch
duration = 0.4;      // Adjust tone length
```

## Browser Compatibility
- **Web Audio API**: Supported in all modern browsers
- **Web Speech Synthesis API**: Supported in Chrome, Edge, Safari, Firefox
- **getUserMedia API**: Requires HTTPS or localhost

## Security Considerations
- Face encodings are stored in memory only (not persisted)
- State resets when backend restarts
- All processing happens on your local machine/server

## Future Enhancements
- Configurable alert volume
- Custom alert sounds (upload .wav/.mp3 files)
- Email/SMS notifications on detection
- Recording of change events with timestamps
- Alert sensitivity adjustment via UI
- Multiple person tracking
- Integration with database for persistent tracking

## Testing
1. Start the backend: `uvicorn main:app --reload`
2. Open `index.html` in a browser
3. Enable continuous monitoring
4. Move in front of the camera or change the scene
5. Verify audio and voice alerts trigger

## Troubleshooting

### No Audio Alert
- Check browser audio permissions
- Ensure volume is not muted
- Try clicking on the page first (some browsers require user interaction)

### No Voice Alert
- Check if Web Speech API is supported in your browser
- Verify browser has internet connection (some browsers require it for TTS)

### Alerts Too Sensitive/Not Sensitive Enough
- Adjust `threshold` in `compare_scene_histograms()` (backend)
- Adjust `tolerance` in `face_recognition.compare_faces()` (backend)

## Dependencies
No new dependencies required! The feature uses:
- Existing OpenCV and face_recognition libraries (backend)
- Built-in Web APIs (frontend)
