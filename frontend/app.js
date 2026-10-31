/**
 * Face Recognition Frontend - API Integration
 * Connects to FastAPI Backend for Real-time Face Detection & Recognition
 */

// API Configuration
const API_URL = 'http://localhost:8000';
const API_V1 = `${API_URL}/api/v1`;

// Global State
let stream = null;
let cameraActive = false;
let capturedImage = null;
let registrationMode = false;

// DOM Elements
const videoElement = document.getElementById('videoElement');
const canvasElement = document.getElementById('canvasElement');
const captureBtn = document.getElementById('captureBtn');
const registerBtn = document.getElementById('registerBtn');
const cameraToggleBtn = document.getElementById('cameraToggleBtn');
const statusText = document.getElementById('statusText');
const resultContent = document.getElementById('resultContent');
const apiStatus = document.getElementById('apiStatus');
const registrationForm = document.getElementById('registrationForm');
const registrationSection = document.getElementById('registrationSection');
const closeRegistration = document.getElementById('closeRegistration');
const refreshUsersBtn = document.getElementById('refreshUsersBtn');
const usersList = document.getElementById('usersList');
const imageModal = document.getElementById('imageModal');
const modalImage = document.getElementById('modalImage');
const closeModal = document.querySelector('.close');

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Face Recognition System Initializing...');
    initializeSystem();
    setupEventListeners();
    checkAPIConnection();
    loadUsers();
});

// ==================== SYSTEM INITIALIZATION ====================

async function initializeSystem() {
    updateStatus('System initializing...');
    try {
        await checkAPIConnection();
    } catch (error) {
        console.error('Failed to initialize:', error);
        updateStatus('System initialization failed. Check console for details.');
    }
}

async function checkAPIConnection() {
    try {
        const response = await fetch(`${API_V1}/health/`);
        if (response.ok) {
            const health = await response.json();
            console.log('✅ API Connected:', health);
            updateAPIStatus(true);
            updateStatus('✅ System ready. Camera waiting to start.');
            return true;
        }
    } catch (error) {
        console.error('❌ API Connection Failed:', error);
        updateAPIStatus(false);
        updateStatus('❌ Backend API not accessible. Ensure server is running at http://localhost:8000');
        return false;
    }
}

function updateAPIStatus(connected) {
    const badge = document.querySelector('.status-badge');
    if (connected) {
        badge.className = 'status-badge connected';
        badge.textContent = '🟢 Connected';
    } else {
        badge.className = 'status-badge disconnected';
        badge.textContent = '🔴 Disconnected';
    }
}

// ==================== CAMERA MANAGEMENT ====================

async function startCamera() {
    if (cameraActive) return;

    try {
        updateStatus('🎥 Starting camera...');
        stream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                facingMode: 'user',
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        });
        
        videoElement.srcObject = stream;
        cameraActive = true;
        captureBtn.disabled = false;
        registerBtn.disabled = false;
        cameraToggleBtn.textContent = '⏹️ Stop Camera';
        updateStatus('✅ Camera started successfully. Ready to scan faces.');
        console.log('✅ Camera initialized');
    } catch (error) {
        console.error('❌ Camera Error:', error);
        updateStatus('❌ Camera access denied. Please check browser permissions.');
    }
}

function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        videoElement.srcObject = null;
        cameraActive = false;
        captureBtn.disabled = true;
        registerBtn.disabled = true;
        cameraToggleBtn.textContent = '🎥 Start Camera';
        updateStatus('🛑 Camera stopped.');
        console.log('⏹️ Camera stopped');
    }
}

// ==================== IMAGE CAPTURE & RECOGNITION ====================

async function captureAndRecognize() {
    if (!cameraActive) {
        updateStatus('❌ Camera not active. Please start camera first.');
        return;
    }

    try {
        updateStatus('📸 Capturing face...');
        
        // Capture image from video
        canvasElement.width = videoElement.videoWidth;
        canvasElement.height = videoElement.videoHeight;
        const ctx = canvasElement.getContext('2d');
        ctx.drawImage(videoElement, 0, 0);
        
        // Convert to blob
        canvasElement.toBlob(async (blob) => {
            await sendFaceToBackend(blob, 'scan');
        }, 'image/jpeg', 0.9);
    } catch (error) {
        console.error('❌ Capture Error:', error);
        updateStatus('❌ Failed to capture image.');
    }
}

async function captureForRegistration() {
    if (!cameraActive) {
        updateStatus('❌ Camera not active. Please start camera first.');
        return;
    }

    try {
        updateStatus('📸 Capturing face for registration...');
        
        canvasElement.width = videoElement.videoWidth;
        canvasElement.height = videoElement.videoHeight;
        const ctx = canvasElement.getContext('2d');
        ctx.drawImage(videoElement, 0, 0);
        
        capturedImage = canvasElement.toDataURL('image/jpeg');
        registrationSection.classList.remove('hidden');
        stopCamera();
        updateStatus('✅ Image captured. Please complete registration form.');
    } catch (error) {
        console.error('❌ Registration Capture Error:', error);
        updateStatus('❌ Failed to capture image for registration.');
    }
}

// ==================== FACE RECOGNITION API ====================

async function sendFaceToBackend(blob, action) {
    try {
        const formData = new FormData();
        formData.append('file', blob, 'face.jpg');

        updateStatus('🔍 Processing face detection...');
        
        const response = await fetch(`${API_V1}/faces/scan`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.status}`);
        }

        const result = await response.json();
        console.log('✅ Recognition Result:', result);
        displayRecognitionResult(result);

    } catch (error) {
        console.error('❌ Recognition Error:', error);
        displayError(`Recognition failed: ${error.message}`);
    }
}

function displayRecognitionResult(result) {
    let html = '<div class="result-item">';
    
    if (result.status === 'success' || result.recognized) {
        html += `
            <strong style="color: var(--success-color);">✅ Face Recognized</strong><br>
            <strong>User ID:</strong> ${result.user_id}<br>
            <strong>Username:</strong> ${result.username}<br>
            <strong>Confidence:</strong> ${(result.confidence * 100).toFixed(2)}%<br>
            <strong>Message:</strong> ${result.message}
        `;
        updateStatus(`✅ Access Granted: ${result.username}`);
    } else {
        html += `
            <strong style="color: var(--danger-color);">❌ Face Not Recognized</strong><br>
            <strong>Status:</strong> ${result.status}<br>
            <strong>Faces Found:</strong> ${result.faces_found}<br>
            <strong>Message:</strong> ${result.message}
        `;
        updateStatus('❌ Access Denied: Face not recognized.');
    }
    
    html += '</div>';
    resultContent.innerHTML = html;
}

function displayError(message) {
    const html = `<div class="result-item error">
        <strong style="color: var(--danger-color);">⚠️ Error</strong><br>
        ${message}
    </div>`;
    resultContent.innerHTML = html;
    updateStatus(`❌ ${message}`);
}

// ==================== USER REGISTRATION ====================

async function registerUser(event) {
    event.preventDefault();

    if (!capturedImage) {
        alert('Please capture an image first.');
        return;
    }

    const username = document.getElementById('username').value;
    const fullName = document.getElementById('fullName').value;
    const password = document.getElementById('password').value;
    const role = document.getElementById('role').value;

    try {
        updateStatus('📝 Registering user...');
        
        const response = await fetch(`${API_V1}/faces/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username,
                full_name: fullName,
                password,
                role,
                image: capturedImage
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Registration failed');
        }

        const result = await response.json();
        console.log('✅ Registration Result:', result);
        
        displayRegistrationResult(result);
        registrationForm.reset();
        registrationSection.classList.add('hidden');
        capturedImage = null;
        await loadUsers();

    } catch (error) {
        console.error('❌ Registration Error:', error);
        displayError(`Registration failed: ${error.message}`);
    }
}

function displayRegistrationResult(result) {
    const html = `<div class="result-item">
        <strong style="color: var(--success-color);">✅ User Registered Successfully</strong><br>
        <strong>User ID:</strong> ${result.user_id}<br>
        <strong>Username:</strong> ${result.username}<br>
        <strong>Status:</strong> ${result.status}<br>
        <strong>Message:</strong> ${result.message}
    </div>`;
    resultContent.innerHTML = html;
    updateStatus(`✅ User '${result.username}' registered successfully!`);
}

// ==================== USERS MANAGEMENT ====================

async function loadUsers() {
    try {
        const response = await fetch(`${API_V1}/users/`);
        if (!response.ok) throw new Error('Failed to load users');

        const users = await response.json();
        displayUsers(users);
    } catch (error) {
        console.error('❌ Load Users Error:', error);
        usersList.innerHTML = '<p>Failed to load users.</p>';
    }
}

function displayUsers(users) {
    if (!users || users.length === 0) {
        usersList.innerHTML = '<p>No users registered yet.</p>';
        return;
    }

    const html = users.map(user => `
        <div class="user-card">
            <h4>👤 ${user.full_name || user.username}</h4>
            <p><strong>Username:</strong> ${user.username}</p>
            <p><strong>Role:</strong> ${user.role}</p>
            <p><strong>Status:</strong> ${user.is_active ? '✅ Active' : '❌ Inactive'}</p>
            <p><strong>Registered:</strong> ${new Date(user.created_at).toLocaleDateString()}</p>
        </div>
    `).join('');
    
    usersList.innerHTML = html;
}

// ==================== STATUS UPDATES ====================

function updateStatus(message) {
    statusText.textContent = message;
    console.log(`📊 Status: ${message}`);
}

// ==================== EVENT LISTENERS ====================

function setupEventListeners() {
    // Camera Controls
    cameraToggleBtn.addEventListener('click', () => {
        if (cameraActive) {
            stopCamera();
        } else {
            startCamera();
        }
    });

    // Capture & Recognition
    captureBtn.addEventListener('click', captureAndRecognize);

    // Registration
    registerBtn.addEventListener('click', () => {
        if (cameraActive) {
            captureForRegistration();
        }
    });

    registrationForm.addEventListener('submit', registerUser);
    closeRegistration.addEventListener('click', () => {
        registrationSection.classList.add('hidden');
        startCamera();
    });

    // Users List
    refreshUsersBtn.addEventListener('click', loadUsers);

    // Modal
    if (closeModal) {
        closeModal.addEventListener('click', () => {
            imageModal.classList.add('hidden');
        });
    }

    window.addEventListener('click', (event) => {
        if (event.target === imageModal) {
            imageModal.classList.add('hidden');
        }
    });
}

// ==================== UTILITY FUNCTIONS ====================

// Auto-check API connection every 10 seconds
setInterval(checkAPIConnection, 10000);

console.log('✅ Face Recognition Frontend Loaded Successfully');
