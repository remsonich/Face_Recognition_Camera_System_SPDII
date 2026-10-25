# Audible Alert System - Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Camera Stream (Video)                      │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │                                         │
│                     ▼                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │   Capture Frame Every 2 Seconds (Continuous Mode)      │ │
│  │            or Manual Capture Button                    │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │ Convert to Base64                      │
│                     ▼                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           POST /api/recognize                          │ │
│  │           { image: base64_data }                       │ │
│  └──────────────────┬─────────────────────────────────────┘ │
└────────────────────┼──────────────────────────────────────┘
                     │ HTTP Request
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            Decode Base64 Image                         │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │                                         │
│                     ▼                                         │
│  ┌─────────────────────────────────────────────┐            │
│  │         PARALLEL PROCESSING                 │            │
│  │  ┌──────────────────┐  ┌──────────────────┐│            │
│  │  │ Scene Detection  │  │ Face Detection   ││            │
│  │  │ (HSV Histogram)  │  │ (Face Encoding)  ││            │
│  │  └────────┬─────────┘  └────────┬─────────┘│            │
│  └───────────┼─────────────────────┼──────────┘            │
│              │                     │                         │
│              ▼                     ▼                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Compare with Last State                      │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │ last_detection_state = {                         │ │ │
│  │  │   person_encoding: face_encoding,                │ │ │
│  │  │   scene_histogram: histogram,                    │ │ │
│  │  │   face_count: number                             │ │ │
│  │  │ }                                                 │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │                                         │
│                     ▼                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            Determine Alert Type                        │ │
│  │  ● scene_changed: Histogram correlation < 0.7         │ │
│  │  ● person_changed: Face encoding mismatch             │ │
│  │  ● scene_and_person_changed: Both conditions          │ │
│  │  ● person_left: Face count dropped to 0               │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │                                         │
│                     ▼                                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │          Return JSON Response                          │ │
│  │  {                                                     │ │
│  │    status: "success",                                 │ │
│  │    faces_found: 1,                                    │ │
│  │    alert: true/false,                                 │ │
│  │    alert_type: "person_changed",                      │ │
│  │    scene_changed: true/false,                         │ │
│  │    person_changed: true/false                         │ │
│  │  }                                                     │ │
│  └──────────────────┬─────────────────────────────────────┘ │
└────────────────────┼──────────────────────────────────────┘
                     │ HTTP Response
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND ALERT SYSTEM                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Check if alert = true                     │ │
│  └──────────────────┬─────────────────────────────────────┘ │
│                     │                                         │
│                     ▼                                         │
│  ┌─────────────────────────────────────────────┐            │
│  │         TRIGGER MULTI-MODAL ALERTS          │            │
│  │                                             │            │
│  │  ┌──────────────────────────────────────┐  │            │
│  │  │  1. AUDIO TONE ALERT                │  │            │
│  │  │  ● Web Audio API                     │  │            │
│  │  │  ● Sine wave oscillator              │  │            │
│  │  │  ● Different frequencies:            │  │            │
│  │  │    - person_changed: 523 Hz (C5)     │  │            │
│  │  │    - scene_changed: 392 Hz (G4)      │  │            │
│  │  │    - both: 659 Hz (E5)               │  │            │
│  │  │    - person_left: 329 Hz (E4)        │  │            │
│  │  └──────────────────────────────────────┘  │            │
│  │                                             │            │
│  │  ┌──────────────────────────────────────┐  │            │
│  │  │  2. VOICE ANNOUNCEMENT               │  │            │
│  │  │  ● Web Speech Synthesis API          │  │            │
│  │  │  ● Natural language description:     │  │            │
│  │  │    - "New person detected"           │  │            │
│  │  │    - "Scene has changed"             │  │            │
│  │  │    - "Scene and person changed"      │  │            │
│  │  │    - "Person has left the frame"     │  │            │
│  │  └──────────────────────────────────────┘  │            │
│  │                                             │            │
│  │  ┌──────────────────────────────────────┐  │            │
│  │  │  3. VISUAL FEEDBACK                  │  │            │
│  │  │  ● Yellow background highlight       │  │            │
│  │  │  ● 2-second duration                 │  │            │
│  │  │  ● Result panel update               │  │            │
│  │  └──────────────────────────────────────┘  │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

## Alert Decision Logic

```
START: New frame captured
│
├─> Decode image
│
├─> Process image
│   ├─> Extract face encodings
│   └─> Calculate scene histogram
│
├─> Compare with previous state
│   │
│   ├─> Is there a face now?
│   │   │
│   │   ├─> NO: Was there a face before?
│   │   │       ├─> YES: Alert = "person_left" ✓
│   │   │       └─> NO: No alert
│   │   │
│   │   └─> YES: Compare face encoding
│   │           ├─> Different? person_changed = true
│   │           └─> Same? person_changed = false
│   │
│   └─> Compare scene histogram
│       ├─> Correlation < 0.7? scene_changed = true
│       └─> Correlation ≥ 0.7? scene_changed = false
│
└─> Determine final alert type
    │
    ├─> scene_changed AND person_changed?
    │   └─> Alert = "scene_and_person_changed" ✓
    │
    ├─> Only person_changed?
    │   └─> Alert = "person_changed" ✓
    │
    ├─> Only scene_changed?
    │   └─> Alert = "scene_changed" ✓
    │
    └─> Neither changed?
        └─> No alert
```

## User Interaction Flow

```
┌──────────────┐
│  User Opens  │
│  Web Page    │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ Camera Initializes   │
│ (getUserMedia API)   │
└──────┬───────────────┘
       │
       ▼
┌────────────────────────────────────────┐
│         User Has Two Options:          │
│                                        │
│  ┌─────────────────────────────────┐  │
│  │ Option 1: Manual Capture        │  │
│  │ ● Click "Capture & Recognize"   │  │
│  │ ● Single frame analysis         │  │
│  │ ● Alert if change detected      │  │
│  └─────────────────────────────────┘  │
│                                        │
│  ┌─────────────────────────────────┐  │
│  │ Option 2: Continuous Monitoring │  │
│  │ ● Click "Start Continuous..."   │  │
│  │ ● Auto-capture every 2 seconds  │  │
│  │ ● Real-time change detection    │  │
│  │ ● Click "Stop Continuous..."    │  │
│  │   to deactivate                 │  │
│  └─────────────────────────────────┘  │
└────────────────────────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Change Detected?    │
└──────┬───────────────┘
       │
       ├─> YES: Multi-modal alert
       │   ├─> Audio tone plays
       │   ├─> Voice announcement
       │   └─> Visual highlight
       │
       └─> NO: Continue monitoring
```

## State Management

```
┌─────────────────────────────────────────────┐
│         Backend State (In Memory)           │
│  ┌───────────────────────────────────────┐  │
│  │  last_detection_state = {             │  │
│  │                                       │  │
│  │    person_encoding: numpy.array       │  │
│  │    // 128-dimensional face encoding   │  │
│  │                                       │  │
│  │    scene_histogram: numpy.array       │  │
│  │    // Normalized HSV histogram        │  │
│  │                                       │  │
│  │    face_count: integer                │  │
│  │    // Number of faces in last frame   │  │
│  │  }                                    │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ⚠️ State resets on backend restart        │
│  ⚠️ Not persisted to database              │
└─────────────────────────────────────────────┘
```

## Audio Frequency Chart

```
Higher Pitch (More Urgent)
    ↑
    │  659.25 Hz ─── scene_and_person_changed (E5)
    │  523.25 Hz ─── person_changed (C5)
    │  392.00 Hz ─── scene_changed (G4)
    │  329.63 Hz ─── person_left (E4)
    ↓
Lower Pitch (Less Urgent)
```

---

This visual representation helps understand how the audible alert system works from camera capture to final alert delivery.
