document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('videoElement');
    const canvas = document.getElementById('canvasElement');
    const captureBtn = document.getElementById('captureBtn');
    const startVoiceBtn = document.getElementById('startVoiceBtn');
    const statusText = document.getElementById('statusText');
    const resultPanel = document.getElementById('resultPanel');

    let continuousMonitoring = false;
    let monitoringInterval = null;

    // Audio Alert System
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    function playAlertSound(alertType) {
        // Create different tones for different alert types
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // Configure sound based on alert type
        let frequency = 440; // Default A4 note
        let duration = 0.3;
        
        switch(alertType) {
            case 'person_changed':
                frequency = 523.25; // C5 - Higher pitch for person change
                duration = 0.4;
                break;
            case 'scene_changed':
                frequency = 392.00; // G4 - Medium pitch for scene change
                duration = 0.3;
                break;
            case 'scene_and_person_changed':
                frequency = 659.25; // E5 - Even higher pitch for both
                duration = 0.5;
                break;
            case 'person_left':
                frequency = 329.63; // E4 - Lower pitch for person leaving
                duration = 0.4;
                break;
        }
        
        oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime);
        oscillator.type = 'sine';
        
        // Fade in and out for smoother sound
        gainNode.gain.setValueAtTime(0, audioContext.currentTime);
        gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05);
        gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + duration);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + duration);
    }
    
    function speakAlert(alertType) {
        if ('speechSynthesis' in window) {
            const utterance = new SpeechSynthesisUtterance();
            utterance.volume = 0.8;
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            
            switch(alertType) {
                case 'person_changed':
                    utterance.text = "New person detected";
                    break;
                case 'scene_changed':
                    utterance.text = "Scene has changed";
                    break;
                case 'scene_and_person_changed':
                    utterance.text = "Scene and person changed";
                    break;
                case 'person_left':
                    utterance.text = "Person has left the frame";
                    break;
                default:
                    utterance.text = "Change detected";
            }
            
            window.speechSynthesis.speak(utterance);
        }
    }

    // WebRTC: Initialize camera
    async function initCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            statusText.textContent = "Camera initialized successfully.";
        } catch (err) {
            console.error("Error accessing camera:", err);
            statusText.textContent = "Error accessing camera. Please ensure permissions are granted.";
        }
    }

    // Capture Image and Send via Fetch API
    async function captureAndRecognize() {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert to base64
        const imageData = canvas.toDataURL('image/jpeg');
        
        if (!continuousMonitoring) {
            statusText.textContent = "Processing image...";
        }

        try {
            // Replace with actual backend API endpoint when deployed
            const response = await fetch('http://localhost:8000/api/recognize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // 'Authorization': 'Bearer <token>' // If JWT is used
                },
                body: JSON.stringify({ image: imageData })
            });

            if (response.ok) {
                const result = await response.json();
                if (!continuousMonitoring) {
                    statusText.textContent = "Recognition complete.";
                }
                resultPanel.innerHTML = `<p>Result: ${JSON.stringify(result)}</p>`;
                
                // Trigger alert if change detected
                if (result.alert && result.alert_type) {
                    playAlertSound(result.alert_type);
                    speakAlert(result.alert_type);
                    
                    // Visual feedback
                    resultPanel.style.backgroundColor = '#fff3cd';
                    setTimeout(() => {
                        resultPanel.style.backgroundColor = '';
                    }, 2000);
                }
            } else {
                throw new Error("API request failed");
            }
        } catch (error) {
            console.error("Error:", error);
            statusText.textContent = "Error communicating with backend API.";
        }
    }
    
    captureBtn.addEventListener('click', async () => {
        await captureAndRecognize();
    });

    // Continuous Monitoring Toggle
    function toggleContinuousMonitoring() {
        continuousMonitoring = !continuousMonitoring;
        
        if (continuousMonitoring) {
            statusText.textContent = "Continuous monitoring active - alerts enabled";
            toggleMonitoringBtn.textContent = "Stop Continuous Monitoring";
            toggleMonitoringBtn.style.backgroundColor = "#dc3545";
            monitoringInterval = setInterval(async () => {
                await captureAndRecognize();
            }, 2000); // Check every 2 seconds
        } else {
            statusText.textContent = "Continuous monitoring stopped";
            toggleMonitoringBtn.textContent = "Start Continuous Monitoring";
            toggleMonitoringBtn.style.backgroundColor = "";
            if (monitoringInterval) {
                clearInterval(monitoringInterval);
                monitoringInterval = null;
            }
        }
    }
    
    // Add toggle button listener if exists
    const toggleMonitoringBtn = document.getElementById('toggleMonitoringBtn');
    if (toggleMonitoringBtn) {
        toggleMonitoringBtn.addEventListener('click', toggleContinuousMonitoring);
    }

    // Web Speech API
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'en-US';

        recognition.onstart = function() {
            statusText.textContent = "Listening for voice command...";
        };

        recognition.onresult = function(event) {
            const command = event.results[0][0].transcript;
            statusText.textContent = `Voice command received: "${command}"`;
            
            if (command.toLowerCase().includes("capture") || command.toLowerCase().includes("recognize")) {
                captureBtn.click();
            }
        };

        recognition.onerror = function(event) {
            statusText.textContent = `Voice recognition error: ${event.error}`;
        };

        startVoiceBtn.addEventListener('click', () => {
            recognition.start();
        });
    } else {
        startVoiceBtn.disabled = true;
        startVoiceBtn.title = "Web Speech API not supported in this browser.";
    }

    // Initialize
    initCamera();
});
