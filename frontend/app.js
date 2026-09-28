document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('videoElement');
    const canvas = document.getElementById('canvasElement');
    const captureBtn = document.getElementById('captureBtn');
    const startVoiceBtn = document.getElementById('startVoiceBtn');
    const statusText = document.getElementById('statusText');
    const resultPanel = document.getElementById('resultPanel');

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
    captureBtn.addEventListener('click', async () => {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert to base64
        const imageData = canvas.toDataURL('image/jpeg');
        
        statusText.textContent = "Processing image...";

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
                statusText.textContent = "Recognition complete.";
                resultPanel.innerHTML = `<p>Result: ${JSON.stringify(result)}</p>`;
            } else {
                throw new Error("API request failed");
            }
        } catch (error) {
            console.error("Error:", error);
            statusText.textContent = "Error communicating with backend API.";
        }
    });

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
