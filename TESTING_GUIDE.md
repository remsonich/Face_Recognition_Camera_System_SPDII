# Testing Guide for Audible Alert Feature

## Prerequisites

### Backend Requirements
- Python 3.8+
- All dependencies from `backend/requirements.txt` installed
- FastAPI server running

### Frontend Requirements
- Modern web browser (Chrome, Firefox, Edge, or Safari)
- Webcam access permission
- Microphone access (for voice commands)
- HTTPS or localhost (required for camera access)

## Setup Instructions

### 1. Start the Backend

```bash
cd backend
uvicorn main:app --reload
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 2. Open the Frontend

1. Navigate to `frontend` folder
2. Open `index.html` in your browser
3. Grant camera permissions when prompted

## Test Cases

### Test 1: Manual Capture with Person Change
**Objective**: Verify person change detection with manual capture

**Steps**:
1. Position yourself in front of the camera
2. Click "Capture & Recognize"
3. Have someone else sit in front of the camera
4. Click "Capture & Recognize" again

**Expected Result**:
- ✅ Audio tone at 523.25 Hz (C5 note)
- ✅ Voice says "New person detected"
- ✅ Yellow highlight on result panel
- ✅ Result shows: `"alert": true, "alert_type": "person_changed"`

### Test 2: Manual Capture with Scene Change
**Objective**: Verify scene change detection

**Steps**:
1. Capture initial frame
2. Change the background significantly (move to different location, change lighting, or rearrange background)
3. Keep the same person in frame
4. Click "Capture & Recognize"

**Expected Result**:
- ✅ Audio tone at 392.00 Hz (G4 note)
- ✅ Voice says "Scene has changed"
- ✅ Result shows: `"alert": true, "alert_type": "scene_changed"`

### Test 3: Both Scene and Person Change
**Objective**: Verify detection of simultaneous changes

**Steps**:
1. Capture initial frame
2. Move to completely different location with different person
3. Click "Capture & Recognize"

**Expected Result**:
- ✅ Audio tone at 659.25 Hz (E5 note)
- ✅ Voice says "Scene and person changed"
- ✅ Result shows: `"alert": true, "alert_type": "scene_and_person_changed"`

### Test 4: Person Leaving Frame
**Objective**: Verify detection when person exits

**Steps**:
1. Position yourself in front of camera
2. Click "Capture & Recognize"
3. Move out of camera view (empty frame)
4. Click "Capture & Recognize"

**Expected Result**:
- ✅ Audio tone at 329.63 Hz (E4 note)
- ✅ Voice says "Person has left the frame"
- ✅ Result shows: `"alert": true, "alert_type": "person_left"`

### Test 5: Continuous Monitoring Mode
**Objective**: Verify automatic continuous detection

**Steps**:
1. Click "Start Continuous Monitoring"
2. Button should turn red and text changes to "Stop Continuous Monitoring"
3. Status shows "Continuous monitoring active - alerts enabled"
4. Wait 2 seconds
5. Have someone walk into frame
6. Wait for automatic alert

**Expected Result**:
- ✅ Automatic capture every 2 seconds
- ✅ Alert triggers when person enters (no manual click needed)
- ✅ Multiple alerts if person keeps changing
- ✅ Monitoring can be stopped with button click

### Test 6: No Change Detection
**Objective**: Verify no false positives

**Steps**:
1. Capture initial frame
2. Stay still in same position
3. Click "Capture & Recognize" multiple times

**Expected Result**:
- ❌ No audio tone
- ❌ No voice announcement
- ❌ No yellow highlight
- ✅ Result shows: `"alert": false`

### Test 7: Voice Command Integration
**Objective**: Verify voice command works with alerts

**Steps**:
1. Click "Start Voice Command"
2. Say "capture" or "recognize"
3. Change position or person
4. Use voice command again

**Expected Result**:
- ✅ Voice command triggers capture
- ✅ Alerts work same as manual capture
- ✅ Voice recognition feedback appears

## Browser-Specific Testing

### Chrome/Edge
- ✅ Full support expected
- ✅ Test Web Audio API
- ✅ Test Speech Synthesis
- ✅ Test continuous monitoring

### Firefox
- ✅ Full support expected
- ⚠️ Speech Synthesis may require internet connection
- ✅ Test all alert types

### Safari
- ✅ Most features supported
- ⚠️ May need to allow autoplay for audio
- ⚠️ Speech Synthesis may have different voices

## Performance Testing

### Test 8: Response Time
**Objective**: Verify system responsiveness

**Procedure**:
1. Time from button click to result display
2. Time from detection to alert trigger
3. Continuous monitoring interval accuracy

**Expected Performance**:
- Manual capture: < 1 second response
- Alert trigger: < 200ms after result
- Continuous interval: ~2000ms ± 100ms

### Test 9: Memory Usage
**Objective**: Verify no memory leaks

**Procedure**:
1. Open browser DevTools > Memory tab
2. Start continuous monitoring
3. Run for 5 minutes
4. Take memory snapshot
5. Stop monitoring
6. Take another snapshot

**Expected Result**:
- ✅ Memory usage stable
- ✅ No significant growth over time
- ✅ Cleanup on monitoring stop

## Error Handling Tests

### Test 10: Backend Offline
**Steps**:
1. Stop backend server
2. Try to capture image

**Expected Result**:
- ✅ Error message displayed
- ✅ "Error communicating with backend API"
- ❌ No crash or freeze

### Test 11: Camera Blocked
**Steps**:
1. Deny camera permissions
2. Reload page

**Expected Result**:
- ✅ Error message: "Error accessing camera"
- ✅ Clear user instructions
- ❌ No silent failure

### Test 12: Dark/Poor Lighting
**Steps**:
1. Test in very dark environment
2. Test with backlight

**Expected Result**:
- ✅ System attempts detection
- ✅ May return "no face detected"
- ❌ No crash

## Configuration Testing

### Test 13: Adjust Backend Tolerance

**Modify `backend/main.py`**:
```python
# Make more strict
tolerance=0.4

# Make more lenient  
tolerance=0.8
```

**Test**: See how it affects person change detection

### Test 14: Adjust Scene Threshold

**Modify `backend/main.py`**:
```python
# More sensitive to scene changes
threshold=0.85

# Less sensitive
threshold=0.5
```

**Test**: See how it affects scene change detection

### Test 15: Adjust Monitoring Interval

**Modify `frontend/app.js`**:
```javascript
// Faster monitoring
setInterval(..., 1000)

// Slower monitoring
setInterval(..., 5000)
```

**Test**: Verify interval changes work correctly

## Troubleshooting Common Issues

### Issue 1: No Audio Alert Heard

**Possible Causes**:
- Browser muted
- System volume low
- Browser requires user interaction first

**Solution**:
1. Check browser audio permissions
2. Click on page before testing
3. Check system volume mixer
4. Try in different browser

### Issue 2: No Voice Announcement

**Possible Causes**:
- Speech Synthesis not supported
- No internet connection (some browsers need it)
- Voice selection issue

**Solution**:
1. Check browser compatibility
2. Verify internet connection
3. Open console for error messages
4. Try different browser

### Issue 3: Too Many False Positives

**Possible Causes**:
- Threshold too sensitive
- Lighting changes
- Camera auto-adjustment

**Solution**:
1. Increase scene threshold (0.7 → 0.8)
2. Increase face tolerance (0.6 → 0.7)
3. Stabilize lighting
4. Use better quality webcam

### Issue 4: Missing Detections

**Possible Causes**:
- Threshold too strict
- Similar faces
- Subtle scene changes

**Solution**:
1. Decrease scene threshold (0.7 → 0.6)
2. Decrease face tolerance (0.6 → 0.5)
3. Verify face is clearly visible
4. Ensure good lighting

## Test Results Template

```
┌─────────────────────────────────────────────────┐
│         AUDIBLE ALERT FEATURE TEST RESULTS      │
├─────────────────────────────────────────────────┤
│ Date: _________________                         │
│ Tester: _______________                         │
│ Browser: ______________                         │
│ Backend Version: ______                         │
├─────────────────────────────────────────────────┤
│ Test 1: Person Change         [ ] Pass [ ] Fail │
│ Test 2: Scene Change          [ ] Pass [ ] Fail │
│ Test 3: Both Changes          [ ] Pass [ ] Fail │
│ Test 4: Person Left           [ ] Pass [ ] Fail │
│ Test 5: Continuous Mode       [ ] Pass [ ] Fail │
│ Test 6: No False Positives    [ ] Pass [ ] Fail │
│ Test 7: Voice Commands        [ ] Pass [ ] Fail │
│ Test 8: Performance           [ ] Pass [ ] Fail │
│ Test 9: Memory Usage          [ ] Pass [ ] Fail │
│ Test 10: Backend Offline      [ ] Pass [ ] Fail │
│ Test 11: Camera Blocked       [ ] Pass [ ] Fail │
│ Test 12: Poor Lighting        [ ] Pass [ ] Fail │
├─────────────────────────────────────────────────┤
│ Overall Result:       [ ] PASS [ ] FAIL         │
├─────────────────────────────────────────────────┤
│ Notes:                                          │
│ _______________________________________________ │
│ _______________________________________________ │
│ _______________________________________________ │
└─────────────────────────────────────────────────┘
```

## Acceptance Criteria

Feature is considered ready when:
- ✅ All 12 test cases pass
- ✅ Works in at least 2 major browsers
- ✅ No console errors during normal operation
- ✅ Response time < 1 second
- ✅ No memory leaks in 5-minute test
- ✅ Clear error messages for all failure modes
- ✅ Documentation complete and accurate

---

**Happy Testing! 🎯**
