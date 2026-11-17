// ===== API Endpoints =====
// Auto-detect host so it connects whether on localhost, 127.0.0.1, or local LAN / Wi-Fi IP
const API = `${window.location.protocol}//${window.location.hostname || 'localhost'}:8000`;
const RECOGNIZE = '/api/recognize';
const REGISTER = '/api/faces/register';
const FACES = '/api/faces';
const TG_CONFIG = '/api/telegram/config';
const TG_TEST = '/api/telegram/test';
const LOGS = '/api/logs';
const CHECK_FRAME = '/api/faces/check_frame';
const INTERVAL = 2200;
const MAX_PHOTOS = 5;

// Helper utilities
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { toast('ទំហំផ្ទុកក្នុង browser ពេញ'); } };

// Labels for alerts
const LABELS = {
  spoof_detected: ['🚨 ការក្លែងបន្លំផ្ទៃមុខ (Spoof / Screen Attack)', 'Warning: Phone screen or photo spoof detected!'],
  unknown_person: ['🚨 ជនមិនស្គាល់អត្តសញ្ញាណ / ជនចម្លែក', 'Warning: Unknown person detected!'],
  person_changed: ['មានមនុស្សថ្មី', 'New person detected'],
  scene_changed: ['ទិដ្ឋភាពប្តូរ', 'Scene has changed'],
  scene_and_person_changed: ['មនុស្ស និងទិដ្ឋភាពប្តូរ', 'Scene and person changed'],
  person_left: ['មនុស្សចាកចេញ', 'Person has left the frame'],
};

// Sound frequencies for oscillator alerts
const TONES = {
  spoof_detected: 987.77,
  unknown_person: 880,
  person_changed: 523.25,
  scene_changed: 392,
  scene_and_person_changed: 659.25,
  person_left: 329.63
};

// Application state
const st = {
  scans: 0,
  alerts: 0,
  intruders: 0,
  faces: 0,
  auto: false,
  timer: null,
  busy: false,
  stream: null,
  photos: []
};

let log = load('frs_log', []);
let totalScans = load('frs_total_scans', 0);
if (!totalScans || totalScans < log.length) {
  totalScans = Math.max(totalScans, log.length);
  save('frs_total_scans', totalScans);
}
let dbPeople = [];

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove('show'), 3500);
}

// ===== View Navigation =====
document.querySelectorAll('.nav').forEach(b => b.onclick = () => show(b.dataset.view));
function show(v) {
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  document.querySelectorAll('.view').forEach(s => s.classList.toggle('on', s.id === v));
  if (v === 'monitor' || v === 'register') initCamera();
  if (v === 'telegram') loadTelegramConfig();
  if (v === 'register') {
    loadRegisteredPeople();
    updateStepperUI(st.photos.length);
  } else {
    stopSmartAutoTrain();
  }
  if (v === 'log') loadLogsFromBackend();
  render();
}

// ===== Camera Streaming =====
async function initCamera() {
  if (!st.stream) {
    try {
      st.stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } }
      });
    } catch (e) {
      return toast('បើកកាមេរ៉ាមិនបាន។ សូមអនុញ្ញាតកាមេរ៉ាក្នុង browser');
    }
  }

  const v1 = $('video1');
  if (v1 && v1.srcObject !== st.stream) {
    v1.srcObject = st.stream;
    v1.play().catch(() => {});
  }

  const v2 = $('video2');
  if (v2 && v2.srcObject !== st.stream) {
    v2.srcObject = st.stream;
    v2.play().catch(() => {});
  }
}

function snap(video, w) {
  if (!video || !video.videoWidth) {
    toast('កាមេរ៉ាកំពុងចាប់ផ្តើម សូមរង់ចាំមួយភ្លែត...');
    return null;
  }
  const c = $('canvas');
  const r = video.videoHeight / video.videoWidth || 0.75;
  c.width = w || video.videoWidth || 640;
  c.height = Math.round(c.width * r);
  const ctx = c.getContext('2d');
  ctx.drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.85);
}

// ===== Backend Connection Health =====
async function health() {
  try {
    const r = await fetch(API + '/');
    if (!r.ok) throw 0;
    setConn('ok', 'Backend ភ្ជាប់ហើយ');
  } catch {
    setConn('off', 'Backend មិនឆ្លើយតប');
  }
}
function setConn(c, t) {
  $('dot').className = c;
  $('connText').textContent = t;
}

// ===== Load Registered Faces from Database =====
async function loadRegisteredPeople() {
  try {
    const r = await fetch(API + FACES);
    if (r.ok) {
      dbPeople = await r.json();
      render();
    }
  } catch (e) {
    console.warn('Could not load faces from database:', e);
  }
}

// ===== Recognition & Monitoring =====
function clearLiveFaceCanvas() {
  const canvas = $('liveFaceCanvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

function drawLiveFaceBoxes(faces, origW, origH) {
  const canvas = $('liveFaceCanvas');
  const v1 = $('video1');
  if (!canvas || !v1) return;

  const w = v1.clientWidth || canvas.parentElement.clientWidth || 640;
  const h = v1.clientHeight || canvas.parentElement.clientHeight || 480;

  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }

  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!faces || faces.length === 0) return;

  const scaleX = w / (origW || 640);
  const scaleY = h / (origH || 480);

  faces.forEach(f => {
    if (!f.box) return;
    const [top, right, bottom, left] = f.box;

    // Because video has scaleX(-1) mirror:
    const drawX = ((origW || 640) - right) * scaleX;
    const drawY = top * scaleY;
    const drawW = (right - left) * scaleX;
    const drawH = (bottom - top) * scaleY;

    const isSpoof = Boolean(f.is_spoof);
    const isKnown = f.matched && !isSpoof;

    let mainColor = '#22c55e';
    let bgTag = 'rgba(22, 101, 52, 0.92)';

    if (isSpoof) {
      mainColor = '#f97316'; // Vibrant cybernetic orange for spoof
      bgTag = 'rgba(194, 65, 12, 0.95)';
    } else if (!isKnown) {
      mainColor = '#ef4444'; // Red for unknown / intruder
      bgTag = 'rgba(185, 28, 28, 0.95)';
    }

    // 1. Cybernetic Bounding Box
    ctx.save();
    ctx.strokeStyle = mainColor;
    ctx.lineWidth = 2.5;
    ctx.shadowColor = mainColor;
    ctx.shadowBlur = isSpoof ? 16 : 12;
    ctx.strokeRect(drawX, drawY, drawW, drawH);

    // 2. 4 Target Corners
    const cornerSize = Math.min(20, drawW / 3);
    ctx.lineWidth = 4;

    // Top-Left
    ctx.beginPath();
    ctx.moveTo(drawX, drawY + cornerSize);
    ctx.lineTo(drawX, drawY);
    ctx.lineTo(drawX + cornerSize, drawY);
    ctx.stroke();

    // Top-Right
    ctx.beginPath();
    ctx.moveTo(drawX + drawW - cornerSize, drawY);
    ctx.lineTo(drawX + drawW, drawY);
    ctx.lineTo(drawX + drawW, drawY + cornerSize);
    ctx.stroke();

    // Bottom-Left
    ctx.beginPath();
    ctx.moveTo(drawX, drawY + drawH - cornerSize);
    ctx.lineTo(drawX, drawY + drawH);
    ctx.lineTo(drawX + cornerSize, drawY + drawH);
    ctx.stroke();

    // Bottom-Right
    ctx.beginPath();
    ctx.moveTo(drawX + drawW - cornerSize, drawY + drawH);
    ctx.lineTo(drawX + drawW, drawY + drawH);
    ctx.lineTo(drawX + drawW, drawY + cornerSize ? drawY + drawH - cornerSize : drawY + drawH);
    ctx.stroke();
    ctx.restore();

    // 3. Name Tag
    let nameStr = '';
    if (isSpoof) {
      nameStr = `📱 ការក្លែងបន្លំ (SCREEN SPOOF)`;
    } else if (isKnown) {
      nameStr = `👤 ${f.name} (${f.confidence || 96}%)`;
    } else {
      nameStr = `🚨 ជនមិនស្គាល់ (INTRUDER)`;
    }

    ctx.font = 'bold 12px "Kantumruy Pro", system-ui, sans-serif';
    const textWidth = ctx.measureText(nameStr).width;
    const tagWidth = textWidth + 18;
    const tagHeight = 24;
    const tagX = Math.max(4, Math.min(drawX, canvas.width - tagWidth - 4));
    const tagY = Math.max(tagHeight + 4, drawY - 6);

    ctx.fillStyle = bgTag;
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(tagX, tagY - tagHeight, tagWidth, tagHeight, 6);
    } else {
      ctx.rect(tagX, tagY - tagHeight, tagWidth, tagHeight);
    }
    ctx.fill();

    ctx.strokeStyle = mainColor;
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.fillText(nameStr, tagX + 9, tagY - 7);
  });
}

async function scan() {
  const v1 = $('video1');
  if (st.busy || !st.stream || !v1 || !v1.videoWidth) {
    if (!st.stream) toast('កាមេរ៉ាមិនទាន់ត្រៀម');
    return;
  }

  st.busy = true;
  $('scanBtn').disabled = true;
  const tStart = performance.now();

  try {
    const imgData = snap(v1);
    if (!imgData) throw new Error('មិនអាចថតរូបពីកាមេរ៉ាបាន');

    const r = await fetch(API + RECOGNIZE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imgData })
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || 'HTTP ' + r.status);
    }

    const d = await r.json();
    const latency = Math.round(performance.now() - tStart);
    if ($('hudTelemetry')) $('hudTelemetry').textContent = `⚡ AI: ${latency}ms • 30 FPS`;

    setConn('ok', 'Backend ភ្ជាប់ហើយ');
    st.scans++;
    totalScans++;
    save('frs_total_scans', totalScans);
    st.faces = d.faces_found || 0;

    // Draw Live Cybernetic Bounding Boxes directly on the camera
    try {
      drawLiveFaceBoxes(d.faces, v1.videoWidth, v1.videoHeight);
    } catch (drawErr) {
      console.warn('Canvas face box rendering warning:', drawErr);
    }

    // Update Live Status Pill
    const pill = $('monitorStatusPill');
    const txt = $('monitorStatusText');
    if (pill && txt) {
      if (d.alert_type === 'spoof_detected' || d.is_spoof) {
        pill.className = 'hud-status-pill warn';
        pill.style.background = 'rgba(234, 88, 12, 0.90)';
        pill.style.borderColor = '#ea580c';
        txt.textContent = '🚨 ការក្លែងបន្លំ! រកឃើញអេក្រង់ទូរស័ព្ទ ឬរូបថត (SPOOF ATTACK BLOCKED)';
        const flash = $('monitorFlash');
        if (flash) {
          flash.classList.add('active');
          setTimeout(() => flash.classList.remove('active'), 200);
        }
      } else if (d.alert_type === 'unknown_person') {
        pill.className = 'hud-status-pill warn';
        pill.style.background = '';
        pill.style.borderColor = '';
        txt.textContent = '🚨 ការព្រមាន! រកឃើញជនមិនស្គាល់អត្តសញ្ញាណ (INTRUDER)';
        const flash = $('monitorFlash');
        if (flash) {
          flash.classList.add('active');
          setTimeout(() => flash.classList.remove('active'), 150);
        }
      } else if (d.faces_found > 0) {
        pill.className = 'hud-status-pill ok';
        pill.style.background = '';
        pill.style.borderColor = '';
        txt.textContent = '✅ ស្គាល់អត្តសញ្ញាណ៖ ' + (d.matched_users.join(', ') || 'Authorized');
      } else {
        pill.className = 'hud-status-pill';
        pill.style.background = '';
        pill.style.borderColor = '';
        txt.textContent = '👁️ រង់ចាំមនុស្សមុខកាមេរ៉ា...';
      }
    }

    if (d.alert && d.alert_type) {
      log.unshift({
        id: d.log_id || undefined,
        type: d.alert_type,
        faces: st.faces,
        matched: d.matched_users,
        telegram: d.telegram_sent,
        time: new Date().toISOString()
      });
      log = deduplicateLogs(log);
      log = log.slice(0, 1000);
      save('frs_log', log);
      alertFx(d.alert_type, d.matched_users);
    }

    showResult(d);
  } catch (e) {
    if (e.message && (e.message.includes('fetch') || e.message.includes('Network') || e.message.includes('Failed to fetch'))) {
      setConn('off', 'Backend មិនឆ្លើយតប');
    }
    $('result').className = 'empty';
    $('result').textContent = 'កំហុស៖ ' + e.message;
    clearLiveFaceCanvas();
  } finally {
    st.busy = false;
    $('scanBtn').disabled = false;
    render();
  }
}

function showResult(d) {
  const el = $('result');
  const isSpoof = d.alert_type === 'spoof_detected' || Boolean(d.is_spoof);
  const isUnknown = d.alert_type === 'unknown_person';
  const isAllKnown = !isSpoof && d.faces_found > 0 && d.unknown_faces_count === 0 && d.matched_users.length > 0;

  el.className = isSpoof ? 'flash intruder' : (isUnknown ? 'flash intruder' : (d.alert ? 'flash' : ''));

  let statusBadge = '';
  if (isSpoof) {
    statusBadge = `<span class="tag bad" style="background:#ea580c; color:#fff">🚨 ការក្លែងបន្លំ (SPOOF ATTACK DETECTED)</span>`;
  } else if (isUnknown) {
    statusBadge = `<span class="tag bad">🚨 ជនមិនស្គាល់អត្តសញ្ញាណ (INTRUDER)</span>`;
  } else if (isAllKnown) {
    statusBadge = `<span class="tag ok">✅ ស្គាល់អត្តសញ្ញាណ (AUTHORIZED)</span>`;
  } else if (d.faces_found === 0) {
    statusBadge = `<span class="tag">គ្មានមនុស្សក្នុងកាមេរ៉ា</span>`;
  } else {
    statusBadge = `<span class="tag warn">${esc(LABELS[d.alert_type]?.[0] || d.alert_type)}</span>`;
  }

  // Intruder, Spoof, or Authorized Banner
  let alertBanner = '';
  if (dbPeople.length === 0) {
    alertBanner = `
      <div class="alert-box warn" style="background:#fef3c7; border:1px solid #f59e0b; color:#92400e; margin:10px 0; padding:12px; border-radius:8px">
        ⚠️ <b>មិនទាន់មានមនុស្សក្នុង Database នៅឡើយទេ!</b><br>
        សូមចូលទៅកាន់ផ្ទាំង <b>«ចុះឈ្មោះមុខ»</b> ដើម្បីថតរូប និងចុះឈ្មោះមុខរបស់អ្នកជាមុនសិន។
      </div>
    `;
  } else if (isSpoof) {
    alertBanner = `
      <div class="alert-box intruder" style="background:#fff7ed; border:1.5px solid #ea580c; color:#c2410c; margin:10px 0; padding:14px; border-radius:8px">
        <b>🚨 ការព្រមានសន្តិសុខ៖ រកឃើញការក្លែងបន្លំផ្ទៃមុខ (Presentation Attack)!</b><br>
        ប្រព័ន្ធបានរកឃើញការប្រើប្រាស់អេក្រង់ទូរស័ព្ទ / Tablet ឬរូបថត 2D ហើយបានទប់ស្កាត់ការអនុញ្ញាតដោយស្វ័យប្រវត្តិ។
        ${d.telegram_sent ? '<br>📱 <b>រូបថតភស្តុតាង និងការព្រមានត្រូវបានផ្ញើទៅ Telegram រួចរាល់!</b>' : ''}
      </div>
    `;
  } else if (isUnknown) {
    alertBanner = `
      <div class="alert-box intruder">
        <b>🚨 ការព្រមានសន្តិសុខ៖</b> រកឃើញជនមិនស្គាល់អត្តសញ្ញាណក្នុងកាមេរ៉ា!
        ${d.telegram_sent ? '<br>📱 <b>រូបថត និងទីតាំងត្រូវបានផ្ញើទៅ Telegram រួចរាល់!</b>' : ''}
      </div>
    `;
  } else if (isAllKnown) {
    alertBanner = `
      <div class="alert-box success">
        <b>✅ អនុញ្ញាត៖</b> ស្គាល់អ្នកប្រើប្រាស់ <b>${esc(d.matched_users.join(', '))}</b>
      </div>
    `;
  }

  // Detected faces list
  let facesListHtml = '';
  if (d.faces && d.faces.length > 0) {
    facesListHtml = '<div class="faces-grid">';
    d.faces.forEach(f => {
      const fIsSpoof = Boolean(f.is_spoof);
      const fIsKnown = f.matched && !fIsSpoof;

      let faceTitle = '';
      let faceTag = '';
      let faceClass = '';

      if (fIsSpoof) {
        faceClass = 'spoof';
        faceTitle = `📱 <b>ការក្លែងបន្លំ (Screen Spoof)</b><br><span class="hint" style="color:#c2410c">${esc(f.spoof_reason || 'Screen bezel edges or 2D photo')}</span>`;
        faceTag = `<span class="tag bad" style="background:#ea580c; color:#fff">ទប់ស្កាត់ (BLOCKED)</span>`;
      } else if (fIsKnown) {
        faceClass = 'known';
        faceTitle = `👤 <b>${esc(f.name)}</b>${f.role ? ` <span class="hint">(${esc(f.role)})</span>` : ''}`;
        faceTag = `<span class="tag ok">${f.confidence}% ផ្ទៀងផ្ទាត់</span>`;
      } else {
        faceClass = 'unknown';
        faceTitle = `❓ <b>ជនមិនស្គាល់ (Unknown)</b>`;
        faceTag = `<span class="tag bad">មិនស្គាល់</span>`;
      }

      facesListHtml += `
        <div class="face-item ${faceClass}" style="${fIsSpoof ? 'border-left: 4px solid #ea580c; background: #fff7ed;' : ''}">
          <div>
            ${faceTitle}
          </div>
          ${faceTag}
        </div>
      `;
    });
    facesListHtml += '</div>';
  }

  el.innerHTML = `
    ${statusBadge}
    ${alertBanner}
    ${facesListHtml}
    <dl class="kv">
      <dt>ស្ថានភាព API</dt><dd>${esc(d.message || d.status)}</dd>
      <dt>ចំនួនមុខសរុប</dt><dd>${d.faces_found}</dd>
      <dt>ជនចម្លែក</dt><dd style="color:${d.unknown_faces_count ? 'var(--bad)' : 'inherit'}; font-weight:600">${d.unknown_faces_count}</dd>
      <dt>Telegram Alert</dt><dd>${d.telegram_sent ? '✅ បានផ្ញើ' : '—'}</dd>
      <dt>ម៉ោងស្កេន</dt><dd>${new Date().toLocaleTimeString()}</dd>
    </dl>
  `;
}

// ===== Audio & Speech Synthesis Alerts =====
let ac;
function alertFx(type, matchedNames) {
  // 1. Audible alert tone / siren
  if ($('optSound').checked) {
    try {
      ac = ac || new (window.AudioContext || window.webkitAudioContext)();
      if (ac.state === 'suspended') ac.resume();

      if (type === 'spoof_detected') {
        // High-priority rapid alarm burst for spoof attack
        [0, 0.12, 0.24, 0.36].forEach(delay => {
          const o = ac.createOscillator();
          const g = ac.createGain();
          const t = ac.currentTime + delay;
          o.type = 'sawtooth';
          o.frequency.setValueAtTime(1150, t);
          o.frequency.exponentialRampToValueAtTime(550, t + 0.09);
          o.connect(g);
          g.connect(ac.destination);
          g.gain.setValueAtTime(0.4, t);
          g.gain.linearRampToValueAtTime(0, t + 0.1);
          o.start(t);
          o.stop(t + 0.1);
        });
      } else if (type === 'unknown_person') {
        // Dual-tone security siren for intruder
        [0, 0.22, 0.44].forEach(delay => {
          const o = ac.createOscillator();
          const g = ac.createGain();
          const t = ac.currentTime + delay;
          o.type = 'sawtooth';
          o.frequency.setValueAtTime(950, t);
          o.frequency.exponentialRampToValueAtTime(450, t + 0.18);
          o.connect(g);
          g.connect(ac.destination);
          g.gain.setValueAtTime(0.35, t);
          g.gain.linearRampToValueAtTime(0, t + 0.2);
          o.start(t);
          o.stop(t + 0.2);
        });
      } else {
        const o = ac.createOscillator();
        const g = ac.createGain();
        const t = ac.currentTime;
        o.frequency.value = TONES[type] || 440;
        o.connect(g);
        g.connect(ac.destination);
        g.gain.setValueAtTime(0, t);
        g.gain.linearRampToValueAtTime(0.25, t + 0.05);
        g.gain.linearRampToValueAtTime(0, t + 0.35);
        o.start(t);
        o.stop(t + 0.35);
      }
    } catch (e) {
      console.warn('AudioContext error:', e);
    }
  }

  // 2. Voice speaking announcement
  if ($('optSpeak').checked && 'speechSynthesis' in window) {
    const lang = $('optLang').value;
    let spokenText = '';
    if (type === 'spoof_detected') {
      spokenText = lang === 'km-KH'
        ? 'ការព្រមាន៖ រកឃើញការក្លែងបន្លំផ្ទៃមុខដោយប្រើអេក្រង់ទូរស័ព្ទ ឬរូបថត!'
        : 'Warning! Presentation spoof attack detected!';
    } else if (type === 'unknown_person') {
      spokenText = lang === 'km-KH'
        ? 'ការព្រមាន៖ រកឃើញជនមិនស្គាល់អត្តសញ្ញាណ!'
        : 'Warning! Unknown person detected!';
    } else if (matchedNames && matchedNames.length > 0) {
      spokenText = lang === 'km-KH'
        ? `សូមស្វាគមន៍ ${matchedNames.join(', ')}`
        : `Welcome ${matchedNames.join(', ')}`;
    } else {
      spokenText = lang === 'km-KH' ? (LABELS[type]?.[0] || 'ការប្តូរ') : (LABELS[type]?.[1] || 'Change detected');
    }

    const u = new SpeechSynthesisUtterance(spokenText);
    u.lang = lang;
    speechSynthesis.speak(u);
  }
}

// ===== Control Buttons =====
$('scanBtn').onclick = scan;

$('autoBtn').onclick = () => {
  st.auto = !st.auto;
  const b = $('autoBtn');
  b.textContent = st.auto ? '⏹️ បញ្ឈប់ការតាមដាន' : '🚀 ចាប់ផ្តើមតាមដានស្វ័យប្រវត្តិ (Smart Auto)';
  b.classList.toggle('stop', st.auto);
  b.classList.toggle('auto-btn-glow', !st.auto);

  const beam = $('monitorScannerBeam');
  if (beam) beam.style.display = st.auto ? 'block' : 'none';

  const pill = $('monitorStatusPill');
  const txt = $('monitorStatusText');
  if (pill && txt) {
    if (st.auto) {
      pill.className = 'hud-status-pill ok';
      txt.textContent = '🟢 កំពុងតាមដានផ្ទាល់ (Live AI Monitoring Active)...';
    } else {
      pill.className = 'hud-status-pill';
      txt.textContent = 'រង់ចាំមនុស្សមុខកាមេរ៉ា...';
      clearLiveFaceCanvas();
    }
  }

  clearInterval(st.timer);
  if (st.auto) {
    scan();
    st.timer = setInterval(scan, INTERVAL);
  }
};

if ($('camFullscreenBtn')) {
  $('camFullscreenBtn').onclick = () => {
    const box = $('monitorCamBox');
    if (!document.fullscreenElement) {
      box.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };
}

// Speech recognition voice command
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  const rec = new SR();
  rec.lang = 'en-US';
  rec.continuous = false;
  rec.interimResults = false;

  rec.onstart = () => {
    $('voiceBtn').classList.add('stop');
    $('voiceBtn').textContent = '🎙️ កំពុងស្តាប់...';
    toast('🎙️ កំពុងស្តាប់... សូមនិយាយថា "scan" ឬ "check"');
  };

  rec.onend = () => {
    $('voiceBtn').classList.remove('stop');
    $('voiceBtn').textContent = 'បញ្ជាដោយសំឡេង';
  };

  rec.onresult = e => {
    const c = e.results[0][0].transcript.toLowerCase();
    toast('ឮ៖ "' + c + '"');
    if (/capture|recognize|scan|check|ស្កេន/.test(c)) {
      scan();
    } else {
      toast('ឮ៖ "' + c + '" (សូមនិយាយពាក្យ "scan" ឬ "check")');
    }
  };

  rec.onerror = e => {
    $('voiceBtn').classList.remove('stop');
    $('voiceBtn').textContent = 'បញ្ជាដោយសំឡេង';
    if (e.error !== 'no-speech') {
      toast('កំហុសសំឡេង៖ ' + e.error);
    }
  };

  $('voiceBtn').onclick = () => {
    try {
      rec.start();
    } catch {
      try { rec.stop(); } catch {}
    }
  };
} else {
  $('voiceBtn').disabled = true;
  $('voiceBtn').title = 'Browser របស់អ្នកមិនគាំទ្រ Web Speech API ទេ (សូមប្រើ Google Chrome ឬ Microsoft Edge)';
}

// ===== Smart Guided Camera Training =====
const TRAIN_STEPS = [
  {
    step: 1,
    title: 'មើលចំកណ្តាលកាមេរ៉ា (Look Straight)',
    tip: 'រក្សាទឹកមុខធម្មតា និងដាក់មុខចំកណ្តាលរង្វង់',
    voice: 'សូមមើលចំកណ្តាលកាមេរ៉ា',
    icon: '👁️'
  },
  {
    step: 2,
    title: 'ងាកក្បាលទៅឆ្វេងបន្តិច (Turn Left Slightly)',
    tip: 'ងាកមុខប្រហែល ១៥ ទៅ ២០ ដឺក្រេទៅខាងឆ្វេង',
    voice: 'សូមងាកក្បាលទៅឆ្វេងបន្តិច',
    icon: '👈'
  },
  {
    step: 3,
    title: 'ងាកក្បាលទៅស្តាំបន្តិច (Turn Right Slightly)',
    tip: 'ងាកមុខប្រហែល ១៥ ទៅ ២០ ដឺក្រេទៅខាងស្តាំ',
    voice: 'សូមងាកក្បាលទៅស្តាំបន្តិច',
    icon: '👉'
  },
  {
    step: 4,
    title: 'ងើបក្បាលឡើងលើបន្តិច (Tilt Head Slightly Up)',
    tip: 'ងើបចង្កាឡើងលើបន្តិច ដើម្បីឱ្យ AI ចាប់យកទម្រង់ចង្កា',
    voice: 'សូមងើបក្បាលឡើងលើបន្តិច',
    icon: '👆'
  },
  {
    step: 5,
    title: 'ញញឹម ឬមើលត្រង់ម្តងទៀត (Smile or Neutral)',
    tip: 'ញញឹមបន្តិចដើម្បីឱ្យ AI ចងចាំទឹកមុខផ្សេងៗ',
    voice: 'ញញឹមបន្តិច ល្អណាស់',
    icon: '😊'
  }
];

let smartTrainState = {
  active: false,
  stepIdx: 0,
  timer: null,
  checking: false,
  countdownTimer: null,
  isCounting: false,
  alignedCount: 0
};

// Web Audio API Synthesizers
function playCameraShutterSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(800, t);
    osc.frequency.exponentialRampToValueAtTime(100, t + 0.05);
    gain.gain.setValueAtTime(0.4, t);
    gain.gain.linearRampToValueAtTime(0.01, t + 0.05);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.05);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sawtooth';
    osc2.frequency.setValueAtTime(500, t + 0.06);
    osc2.frequency.exponentialRampToValueAtTime(80, t + 0.12);
    gain2.gain.setValueAtTime(0.35, t + 0.06);
    gain2.gain.linearRampToValueAtTime(0.01, t + 0.12);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(t + 0.06);
    osc2.stop(t + 0.12);
  } catch(e) {}
}

function playCountdownBeep(freq = 600) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.12);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
  } catch(e) {}
}

function playSuccessChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [523.25, 659.25, 783.99, 1046.50].forEach((freq, idx) => {
      const t = ctx.currentTime + idx * 0.12;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(0.25, t);
      gain.gain.linearRampToValueAtTime(0.01, t + 0.2);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.2);
    });
  } catch(e) {}
}

function speakGuide(text) {
  if ('speechSynthesis' in window && $('optSpeak')?.checked !== false) {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = $('optLang')?.value || 'km-KH';
      window.speechSynthesis.speak(u);
    } catch(e) {}
  }
}

function updateStepperUI(idx) {
  const currentStep = TRAIN_STEPS[Math.min(idx, TRAIN_STEPS.length - 1)];
  if ($('stepBadge')) $('stepBadge').textContent = `🎯 ជំហានទី ${Math.min(idx + 1, 5)} / 5`;
  if ($('stepTitle')) $('stepTitle').textContent = currentStep.title;
  if ($('stepTip')) $('stepTip').textContent = currentStep.tip;
  if ($('stepIcon')) $('stepIcon').textContent = currentStep.icon;

  document.querySelectorAll('#stepperDots .dot-item').forEach((dot, dIdx) => {
    dot.classList.remove('active', 'done');
    if (dIdx < idx) dot.classList.add('done');
    else if (dIdx === idx) dot.classList.add('active');
  });

  if ($('shotCount')) $('shotCount').textContent = `${st.photos.length} / ${MAX_PHOTOS} រូប`;
}

function setHudStatus(type, text) {
  const oval = $('hudOvalGuide');
  const pill = $('hudStatusPill');
  const statusTxt = $('hudStatusText');

  if (oval) {
    oval.classList.remove('aligned', 'warning');
    if (type === 'ok') oval.classList.add('aligned');
    else if (type === 'warn') oval.classList.add('warning');
  }

  if (pill) {
    pill.classList.remove('ok', 'warn');
    if (type === 'ok') pill.classList.add('ok');
    else if (type === 'warn') pill.classList.add('warn');
  }

  if (statusTxt) statusTxt.textContent = text;
}

function triggerCameraFlash() {
  const flash = $('hudFlash');
  if (flash) {
    flash.classList.add('active');
    setTimeout(() => flash.classList.remove('active'), 120);
  }
}

function startSmartAutoTrain() {
  initCamera();
  const v2 = $('video2');
  if (!st.stream || !v2) {
    return toast('កាមេរ៉ាមិនទាន់ត្រៀម សូមរង់ចាំមួយភ្លែត...');
  }

  if (st.photos.length >= MAX_PHOTOS) {
    st.photos = [];
    render();
  }

  smartTrainState.active = true;
  smartTrainState.stepIdx = st.photos.length;
  smartTrainState.alignedCount = 0;
  smartTrainState.isCounting = false;

  const btn = $('smartAutoBtn');
  if (btn) {
    btn.textContent = '⏹️ បញ្ឈប់ការស្កេន';
    btn.classList.remove('auto-btn-glow');
    btn.classList.add('stop');
  }
  if ($('hudScannerBeam')) $('hudScannerBeam').style.display = 'block';

  updateStepperUI(smartTrainState.stepIdx);
  speakGuide(TRAIN_STEPS[smartTrainState.stepIdx].voice);
  setHudStatus('warn', 'សូមដាក់មុខក្នុងរង្វង់...');

  clearInterval(smartTrainState.timer);
  smartTrainState.timer = setInterval(checkSmartFrame, 400);
}

function stopSmartAutoTrain(reset = false) {
  smartTrainState.active = false;
  smartTrainState.isCounting = false;
  clearInterval(smartTrainState.timer);
  clearTimeout(smartTrainState.countdownTimer);

  if ($('hudCountdown')) $('hudCountdown').style.display = 'none';
  if ($('hudScannerBeam')) $('hudScannerBeam').style.display = 'none';

  const btn = $('smartAutoBtn');
  if (btn) {
    btn.textContent = '🚀 ចាប់ផ្តើមស្កេនឆ្លាតវៃ (Auto Smart)';
    btn.classList.add('auto-btn-glow');
    btn.classList.remove('stop');
  }

  if (reset) {
    st.photos = [];
    smartTrainState.stepIdx = 0;
    updateStepperUI(0);
    render();
    setHudStatus('default', 'រង់ចាំចាប់ផ្តើម...');
    toast('បានកំណត់ឡើងវិញ');
  }
}

async function checkSmartFrame() {
  if (!smartTrainState.active || smartTrainState.checking || smartTrainState.isCounting) return;
  const v2 = $('video2');
  if (!v2 || !v2.videoWidth) return;

  const frameB64 = snap(v2, 320);
  if (!frameB64) return;

  smartTrainState.checking = true;
  try {
    const r = await fetch(API + CHECK_FRAME, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: frameB64 })
    });
    if (!r.ok) throw 0;
    const d = await r.json();

    if (d.quality_ok) {
      smartTrainState.alignedCount++;
      setHudStatus('ok', '🟢 មុខចំកណ្តាលល្អ | កំពុងថត...');

      if (smartTrainState.alignedCount >= 2 && !smartTrainState.isCounting) {
        triggerSmartCountdown();
      }
    } else {
      smartTrainState.alignedCount = 0;
      setHudStatus('warn', d.message || 'សូមដាក់មុខក្នុងរង្វង់');
    }
  } catch(e) {
  } finally {
    smartTrainState.checking = false;
  }
}

function triggerSmartCountdown() {
  smartTrainState.isCounting = true;
  let count = 2;
  const cdEl = $('hudCountdown');
  const cdNum = $('hudCountdownNum');

  if (cdEl && cdNum) {
    cdEl.style.display = 'flex';
    cdNum.textContent = count;
  }
  playCountdownBeep(600);

  const stepCountdown = () => {
    count--;
    if (count > 0) {
      if (cdNum) cdNum.textContent = count;
      playCountdownBeep(count === 1 ? 850 : 600);
      smartTrainState.countdownTimer = setTimeout(stepCountdown, 600);
    } else {
      if (cdEl) cdEl.style.display = 'none';
      captureSmartStep();
    }
  };

  smartTrainState.countdownTimer = setTimeout(stepCountdown, 600);
}

function captureSmartStep() {
  const v2 = $('video2');
  if (!v2) return;

  triggerCameraFlash();
  playCameraShutterSound();

  const photo = snap(v2, 480);
  if (photo) {
    st.photos.push(photo);
    render();
  }

  smartTrainState.alignedCount = 0;
  smartTrainState.isCounting = false;
  smartTrainState.stepIdx = st.photos.length;

  if (st.photos.length < MAX_PHOTOS) {
    updateStepperUI(smartTrainState.stepIdx);
    setHudStatus('ok', `📸 ថតបានគំរូទី ${st.photos.length}! ត្រៀមជំហានបន្ទាប់...`);
    speakGuide(TRAIN_STEPS[smartTrainState.stepIdx].voice);

    smartTrainState.checking = true;
    setTimeout(() => {
      smartTrainState.checking = false;
      setHudStatus('warn', 'សូមដាក់មុខក្នុងរង្វង់...');
    }, 1200);

  } else {
    stopSmartAutoTrain();
    updateStepperUI(MAX_PHOTOS - 1);
    setHudStatus('ok', '🎉 ថតគ្រប់ ៥ គំរូជោគជ័យ!');
    playSuccessChime();
    speakGuide('ការថតគំរូមុខទាំងប្រាំបានជោគជ័យ! សូមបញ្ចូលឈ្មោះ និងចុចរក្សាទុក');

    const msg = $('regMsg');
    if (msg) {
      msg.innerHTML = `
        <div class="alert-box success" style="margin:10px 0; font-size:14px">
          🎉 <b>ថតគ្រប់ ៥ គំរូមុខជោគជ័យឥតខ្ចោះ!</b><br>
          សូមបញ្ចូលឈ្មោះអ្នកប្រើប្រាស់ខាងលើ រួចចុចប៊ូតុង <b>«រក្សាទុកការចុះឈ្មោះក្នុង Database»</b>។
        </div>
      `;
    }
    if ($('pName')) $('pName').focus();
    toast('🎉 ថតគ្រប់ ៥ គំរូជោគជ័យ! សូមបញ្ចូលឈ្មោះ');
  }
}

// Action Buttons
if ($('smartAutoBtn')) {
  $('smartAutoBtn').onclick = () => {
    if (smartTrainState.active) {
      stopSmartAutoTrain();
    } else {
      startSmartAutoTrain();
    }
  };
}

if ($('resetTrainBtn')) {
  $('resetTrainBtn').onclick = () => stopSmartAutoTrain(true);
}

$('shotBtn').onclick = () => {
  initCamera();
  const v2 = $('video2');
  if (!st.stream || !v2 || !v2.videoWidth) {
    return toast('កាមេរ៉ាមិនទាន់ត្រៀម សូមរង់ចាំ ២ វិនាទី');
  }
  if (st.photos.length >= MAX_PHOTOS) {
    return toast('ថតបានអតិបរមា ' + MAX_PHOTOS + ' រូប');
  }

  triggerCameraFlash();
  playCameraShutterSound();
  const p = snap(v2, 480);
  if (p) {
    st.photos.push(p);
    toast(`📸 បានថតរូបគំរូទី ${st.photos.length}`);
    updateStepperUI(st.photos.length);
    render();
  }
};

$('saveBtn').onclick = async () => {
  const name = $('pName').value.trim();
  const role = $('pRole').value.trim();
  const msg = $('regMsg');

  if (!name) return toast('សូមបញ្ចូលឈ្មោះអ្នកប្រើប្រាស់');
  if (st.photos.length < 1) return toast('សូមចុច «ថតរូបគំរូ» យ៉ាងតិច ១ រូប (ល្អបំផុត ៣ ទៅ ៥ រូប)');
  if (!$('pConsent').checked) return toast('ត្រូវមានការយល់ព្រមពីម្ចាស់មុខ');

  $('saveBtn').disabled = true;
  msg.textContent = 'កំពុងវិភាគ និងបណ្តុះបណ្តាលមុខ (Training Encodings)...';

  try {
    const r = await fetch(API + REGISTER, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role, images: st.photos })
    });

    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'កំហុសពេលចុះឈ្មោះ');

    toast(`✅ ${res.message || 'បានចុះឈ្មោះជោគជ័យ!'}`);
    msg.innerHTML = `<span style="color:var(--ok); font-weight:600">✅ ${esc(res.message || 'បានរក្សាទុកក្នុង Database ជោគជ័យ')}</span>`;
    st.photos = [];
    $('pName').value = '';
    $('pRole').value = '';
    await loadRegisteredPeople();
  } catch (e) {
    toast('កំហុស៖ ' + e.message);
    msg.innerHTML = `<span style="color:var(--bad); font-weight:600">❌ ${e.message}</span>`;
  } finally {
    $('saveBtn').disabled = false;
    render();
  }
};

// Check duplicate name as user types in registration form
if ($('pName')) {
  $('pName').oninput = () => {
    const val = $('pName').value.trim();
    const existing = dbPeople.find(p => p.name.trim().toLowerCase() === val.toLowerCase());
    const msg = $('regMsg');
    if (existing) {
      msg.innerHTML = `<span style="color:var(--acc)">ℹ️ ឈ្មោះ <b>${esc(existing.name)}</b> មានក្នុង Database រួចហើយ (${existing.samples_count} គំរូ)។ ប្រសិនបើចុះឈ្មោះ វានឹង<b>បន្ថែមរូបថ្មី</b>ទៅមនុស្សនេះ (មិនបង្កើតឈ្មោះជាន់គ្នាទេ)។</span>`;
    } else if (val) {
      msg.innerHTML = `<span style="color:var(--ok)">✨ ឈ្មោះថ្មី៖ នឹងបង្កើតអ្នកប្រើប្រាស់ថ្មីក្នុង Database</span>`;
    } else {
      msg.innerHTML = '';
    }
  };
}

async function deletePerson(id, name) {
  if (!confirm(`តើអ្នកពិតជាចង់លុបទិន្នន័យមុខរបស់ "${name}" ពី Database មែនទេ?`)) return;
  try {
    const r = await fetch(`${API}/api/faces/${id}`, { method: 'DELETE' });
    const res = await r.json();
    if (!r.ok) throw new Error(res.detail || 'កំហុសពេលលុប');
    toast(`បានលុប "${name}" ពី Database រួចរាល់`);
    await loadRegisteredPeople();
  } catch (e) {
    toast('កំហុសពេលលុប៖ ' + e.message);
  }
}

// ===== Telegram Settings Handlers =====
async function loadTelegramConfig() {
  try {
    const r = await fetch(API + TG_CONFIG);
    if (r.ok) {
      const d = await r.json();
      if (d.bot_token_masked) {
        $('tgToken').placeholder = `បានកំណត់រួច៖ (${d.bot_token_masked})`;
      }
      $('tgChatId').value = d.chat_id || '';
      $('tgEnabled').checked = d.enabled;
      $('tgStatusMsg').innerHTML = d.configured
        ? '<span style="color:var(--ok)">✅ Telegram Bot ត្រូវបានកំណត់រួចរាល់ និងសកម្ម។</span>'
        : '<span style="color:var(--warn)">⚠️ សូមបញ្ចូល Bot Token និង Chat ID ដើម្បីបើកការជូនដំណឹង។</span>';
    }
  } catch (e) {
    console.warn('Could not load Telegram config:', e);
  }
}

$('tgSaveBtn').onclick = async () => {
  const bot_token = $('tgToken').value.trim() || undefined;
  const chat_id = $('tgChatId').value.trim() || undefined;
  const enabled = $('tgEnabled').checked;

  try {
    const r = await fetch(API + TG_CONFIG, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token, chat_id, enabled })
    });
    const d = await r.json();
    toast(d.message || 'បានរក្សាទុកការកំណត់ Telegram');
    await loadTelegramConfig();
  } catch (e) {
    toast('កំហុស៖ ' + e.message);
  }
};

$('tgTestBtn').onclick = async () => {
  const bot_token = $('tgToken').value.trim() || undefined;
  const chat_id = $('tgChatId').value.trim() || undefined;

  $('tgTestBtn').disabled = true;
  $('tgStatusMsg').textContent = 'កំពុងផ្ញើសារសាកល្បងទៅ Telegram...';

  try {
    const r = await fetch(API + TG_TEST, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token, chat_id })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'កំហុសពេលផ្ញើសារ');
    toast('✅ ' + d.message);
    $('tgStatusMsg').innerHTML = `<span style="color:var(--ok)">✅ ${d.message}</span>`;
  } catch (e) {
    toast('❌ ' + e.message);
    $('tgStatusMsg').innerHTML = `<span style="color:var(--bad)">❌ ${e.message}</span>`;
  } finally {
    $('tgTestBtn').disabled = false;
  }
};

// ===== Alert Logs & Data Table Management =====
const logFilter = {
  period: 'all',       // 'all', 'today', 'yesterday', 'week', 'month', 'last_month', 'year', 'custom'
  startDate: '',
  endDate: '',
  type: 'all',         // 'all', 'unknown_person', 'person_changed', etc., or 'telegram_only'
  search: '',
  page: 1,
  pageSize: 25         // 10, 25, 50, 100, or 'all'
};

function deduplicateLogs(items) {
  if (!Array.isArray(items)) return [];
  const result = [];
  const seenIds = new Set();

  for (const item of items) {
    if (!item || !item.time) continue;
    if (item.id && seenIds.has(item.id)) continue;

    const itemTimeMs = new Date(item.time).getTime();
    if (isNaN(itemTimeMs)) continue;

    const isDup = result.some(existing => {
      if (item.id && existing.id && item.id === existing.id) return true;

      const existingTimeMs = new Date(existing.time).getTime();
      const diffSec = Math.abs(itemTimeMs - existingTimeMs) / 1000;

      // Same event within 15 seconds
      if (diffSec < 15 && existing.type === item.type) {
        const itemM = (Array.isArray(item.matched) ? item.matched.join(',') : '');
        const existM = (Array.isArray(existing.matched) ? existing.matched.join(',') : '');
        return itemM === existM;
      }

      // Timezone naive vs UTC offset artifact (7 hours = 25200 seconds)
      const tzOffsetDiff = Math.abs(diffSec - 25200);
      if (tzOffsetDiff < 20 && existing.type === item.type) {
        const itemM = (Array.isArray(item.matched) ? item.matched.join(',') : '');
        const existM = (Array.isArray(existing.matched) ? existing.matched.join(',') : '');
        return itemM === existM;
      }

      return false;
    });

    if (!isDup) {
      if (item.id) seenIds.add(item.id);
      result.push(item);
    }
  }

  // Sort newest first
  result.sort((a, b) => new Date(b.time) - new Date(a.time));
  return result;
}

async function loadLogsFromBackend() {
  try {
    const r = await fetch(API + LOGS);
    if (r.ok) {
      const serverLogs = await r.json();
      if (Array.isArray(serverLogs)) {
        log = deduplicateLogs([...log, ...serverLogs]);
        save('frs_log', log);
        render();
      }
    }
  } catch (e) {
    console.warn('Could not sync logs from backend:', e);
  }
}

function matchesPeriod(isoTime, period, customStart, customEnd) {
  if (!isoTime) return true;
  if (period === 'all') return true;

  const d = new Date(isoTime);
  const now = new Date();

  const dDay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const ONE_DAY = 24 * 60 * 60 * 1000;

  if (period === 'today') {
    return dDay === nowDay;
  }
  if (period === 'yesterday') {
    return dDay === (nowDay - ONE_DAY);
  }
  if (period === 'week') {
    return dDay >= (nowDay - 7 * ONE_DAY) && dDay <= nowDay;
  }
  if (period === 'month') {
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }
  if (period === 'last_month') {
    const targetMonth = now.getMonth() === 0 ? 11 : now.getMonth() - 1;
    const targetYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
    return d.getFullYear() === targetYear && d.getMonth() === targetMonth;
  }
  if (period === 'year') {
    return d.getFullYear() === now.getFullYear();
  }
  if (period === 'custom') {
    if (customStart) {
      const s = new Date(customStart + 'T00:00:00').getTime();
      if (d.getTime() < s) return false;
    }
    if (customEnd) {
      const e = new Date(customEnd + 'T23:59:59').getTime();
      if (d.getTime() > e) return false;
    }
    return true;
  }
  return true;
}

function getFilteredLogs() {
  const q = (logFilter.search || '').trim().toLowerCase();

  return log.filter(l => {
    if (!matchesPeriod(l.time, logFilter.period, logFilter.startDate, logFilter.endDate)) {
      return false;
    }
    if (logFilter.type === 'telegram_only') {
      if (!l.telegram) return false;
    } else if (logFilter.type !== 'all' && l.type !== logFilter.type) {
      return false;
    }
    if (q) {
      const typeLabel = (LABELS[l.type]?.[0] || l.type || '').toLowerCase();
      const matchedStr = (Array.isArray(l.matched) ? l.matched.join(' ') : String(l.matched || '')).toLowerCase();
      const timeStr = (when(l.time) || '').toLowerCase();
      if (!typeLabel.includes(q) && !matchedStr.includes(q) && !timeStr.includes(q)) {
        return false;
      }
    }
    return true;
  });
}

function renderLogTable() {
  const filtered = getFilteredLogs();
  const total = filtered.length;

  const intrudersCount = filtered.filter(l => l.type === 'unknown_person').length;
  const spoofsCount = filtered.filter(l => l.type === 'spoof_detected').length;
  const telegramCount = filtered.filter(l => l.telegram).length;
  if ($('filteredCount')) $('filteredCount').textContent = total;
  if ($('filteredIntruders')) $('filteredIntruders').textContent = intrudersCount;
  if ($('filteredSpoofs')) $('filteredSpoofs').textContent = spoofsCount;
  if ($('filteredTelegram')) $('filteredTelegram').textContent = telegramCount;

  const periodNames = {
    all: 'ទាំងអស់ (All Time)',
    today: 'ថ្ងៃនេះ (Today)',
    yesterday: 'ម្សិលមិញ (Yesterday)',
    week: '៧ ថ្ងៃចុងក្រោយ (7 Days)',
    month: 'ខែនេះ (This Month)',
    last_month: 'ខែមុន (Last Month)',
    year: 'ឆ្នាំនេះ (This Year)',
    custom: logFilter.startDate && logFilter.endDate 
      ? `${logFilter.startDate} ដល់ ${logFilter.endDate}` 
      : 'ចន្លោះកាលបរិច្ឆេទ'
  };
  if ($('currentPeriodLabel')) $('currentPeriodLabel').textContent = periodNames[logFilter.period] || 'ទាំងអស់';

  const emptyEl = $('tableEmptyState');
  const tbody = $('logTableBody');
  const paginEl = $('tablePagination');

  if (total === 0) {
    if (tbody) tbody.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'block';
    if (paginEl) paginEl.style.display = 'none';
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';
  if (paginEl) paginEl.style.display = 'flex';

  let pageSize = logFilter.pageSize === 'all' ? total : parseInt(logFilter.pageSize, 10);
  if (isNaN(pageSize) || pageSize < 1) pageSize = 25;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (logFilter.page > totalPages) logFilter.page = totalPages;
  if (logFilter.page < 1) logFilter.page = 1;

  const startIdx = (logFilter.page - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, total);
  const pageItems = filtered.slice(startIdx, endIdx);

  if ($('paginationInfoText')) {
    $('paginationInfoText').textContent = `បង្ហាញ ${startIdx + 1} ដល់ ${endIdx} នៃ ${total} កំណត់ត្រា`;
  }
  if ($('currentPageIndicator')) {
    $('currentPageIndicator').textContent = `ទំព័រ ${logFilter.page} / ${totalPages}`;
  }
  if ($('prevPageBtn')) $('prevPageBtn').disabled = logFilter.page <= 1;
  if ($('nextPageBtn')) $('nextPageBtn').disabled = logFilter.page >= totalPages;

  if (tbody) {
    tbody.innerHTML = pageItems.map((l, idx) => {
      const rowNum = startIdx + idx + 1;
      const isSpoof = l.type === 'spoof_detected';
      const isUnknown = l.type === 'unknown_person';
      const label = LABELS[l.type]?.[0] || l.type;

      const d = new Date(l.time);
      const dateFormatted = isNaN(d) ? '—' : d.toLocaleDateString();
      const timeFormatted = isNaN(d) ? '—' : d.toLocaleTimeString();

      let matchedNames = '<span class="hint">—</span>';
      if (isSpoof) {
        matchedNames = Array.isArray(l.matched) && l.matched.length > 0
          ? `<span class="tag bad" style="background:#ea580c; color:#fff">📱 ក្លែងបន្លំ (${esc(l.matched.join(', '))})</span>`
          : '<span class="tag bad" style="background:#ea580c; color:#fff">📱 អេក្រង់ទូរស័ព្ទ / 2D Photo</span>';
      } else if (Array.isArray(l.matched) && l.matched.length > 0) {
        matchedNames = l.matched.map(n => `<span class="tag ok">👤 ${esc(n)}</span>`).join(' ');
      } else if (isUnknown) {
        matchedNames = '<span class="tag bad">❓ ជនមិនស្គាល់</span>';
      }

      const tgBadge = l.telegram
        ? '<span class="tag ok">✅ បានផ្ញើរូប</span>'
        : '<span class="hint">—</span>';

      const tagClass = isSpoof ? 'bad' : (isUnknown ? 'bad' : 'warn');
      const tagStyle = isSpoof ? 'background:#ea580c; color:#fff;' : '';

      return `
        <tr>
          <td style="text-align: center; color: var(--mute); font-weight: 600;">${rowNum}</td>
          <td>
            <b>${dateFormatted}</b>
            <div class="date-badge">${timeFormatted}</div>
          </td>
          <td>
            <span class="tag ${tagClass}" style="${tagStyle}">${esc(label)}</span>
          </td>
          <td style="text-align: center; font-weight: 600;">${l.faces || 1} មុខ</td>
          <td>${matchedNames}</td>
          <td style="text-align: center;">${tgBadge}</td>
          <td style="text-align: center;">
            <button class="row-del-btn" data-time="${l.time}" data-id="${l.id || ''}" title="លុបកំណត់ត្រានេះ">🗑️</button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('.row-del-btn').forEach(btn => {
      btn.onclick = () => deleteSingleLog(btn.dataset.time, btn.dataset.id);
    });
  }
}

async function deleteSingleLog(time, id) {
  if (!confirm('តើអ្នកពិតជាចង់លុបកំណត់ត្រានេះមែនទេ?')) return;
  log = log.filter(l => l.time !== time);
  save('frs_log', log);

  if (id) {
    try {
      await fetch(`${API}/api/logs/${id}`, { method: 'DELETE' });
    } catch (e) {
      console.warn('Backend log delete failed:', e);
    }
  }

  toast('បានលុបកំណត់ត្រា ១');
  render();
}

async function clearAllLogs() {
  if (!confirm('តើអ្នកពិតជាចង់សម្អាតប្រវត្តិការជូនដំណឹងទាំងអស់មែនទេ? សកម្មភាពនេះមិនអាចត្រឡប់ក្រោយបានឡើយ។')) return;
  log = [];
  save('frs_log', log);

  try {
    await fetch(`${API}/api/logs`, { method: 'DELETE' });
  } catch (e) {
    console.warn('Backend clear logs failed:', e);
  }

  toast('បានសម្អាតប្រវត្តិទាំងអស់');
  render();
}

function exportLogsToCSV() {
  const filtered = getFilteredLogs();
  if (filtered.length === 0) {
    return toast('គ្មានទិន្នន័យដើម្បីទាញយកជា CSV ឡើយ');
  }

  const headers = ['#', 'កាលបរិច្ឆេទ (Date)', 'ម៉ោង (Time)', 'ប្រភេទជូនដំណឹង (Alert Type)', 'ចំនួនមុខ (Faces)', 'អត្តសញ្ញាណ (Names)', 'Telegram (Status)'];
  const rows = filtered.map((l, idx) => {
    const d = new Date(l.time);
    const dateStr = isNaN(d) ? '' : d.toLocaleDateString();
    const timeStr = isNaN(d) ? '' : d.toLocaleTimeString();
    const typeLabel = LABELS[l.type]?.[0] || l.type;
    const names = Array.isArray(l.matched) ? l.matched.join('; ') : (l.type === 'unknown_person' ? 'ជនមិនស្គាល់' : '');
    const tg = l.telegram ? 'បានផ្ញើរូប' : 'មិនបានផ្ញើ';

    return [
      idx + 1,
      `"${dateStr}"`,
      `"${timeStr}"`,
      `"${typeLabel.replace(/"/g, '""')}"`,
      l.faces || 1,
      `"${names.replace(/"/g, '""')}"`,
      `"${tg}"`
    ].join(',');
  });

  const csvContent = '\uFEFF' + [headers.join(','), ...rows].join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const dateTag = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `FaceWatch_Alert_Logs_${dateTag}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast('📥 បានទាញយក File CSV ជោគជ័យ');
}

function initLogTableListeners() {
  const tabs = document.querySelectorAll('#dateFilterTabs .tab-btn');
  tabs.forEach(btn => {
    btn.onclick = () => {
      tabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const p = btn.dataset.period;
      logFilter.period = p;
      logFilter.page = 1;

      const customRow = $('customDateRow');
      if (customRow) {
        customRow.style.display = p === 'custom' ? 'flex' : 'none';
      }
      renderLogTable();
    };
  });

  if ($('applyCustomDateBtn')) {
    $('applyCustomDateBtn').onclick = () => {
      const s = $('customStartDate').value;
      const e = $('customEndDate').value;
      if (!s && !e) return toast('សូមជ្រើសរើសកាលបរិច្ឆេទ');
      logFilter.startDate = s;
      logFilter.endDate = e;
      logFilter.page = 1;
      renderLogTable();
    };
  }

  if ($('typeFilter')) {
    $('typeFilter').onchange = e => {
      logFilter.type = e.target.value;
      logFilter.page = 1;
      renderLogTable();
    };
  }

  if ($('pageSizeSelect')) {
    $('pageSizeSelect').onchange = e => {
      logFilter.pageSize = e.target.value;
      logFilter.page = 1;
      renderLogTable();
    };
  }

  if ($('logSearch')) {
    $('logSearch').oninput = e => {
      logFilter.search = e.target.value;
      logFilter.page = 1;
      const clrBtn = $('clearSearchBtn');
      if (clrBtn) clrBtn.style.display = e.target.value ? 'block' : 'none';
      renderLogTable();
    };
  }

  if ($('clearSearchBtn')) {
    $('clearSearchBtn').onclick = () => {
      $('logSearch').value = '';
      logFilter.search = '';
      logFilter.page = 1;
      $('clearSearchBtn').style.display = 'none';
      renderLogTable();
    };
  }

  if ($('prevPageBtn')) {
    $('prevPageBtn').onclick = () => {
      if (logFilter.page > 1) {
        logFilter.page--;
        renderLogTable();
      }
    };
  }
  if ($('nextPageBtn')) {
    $('nextPageBtn').onclick = () => {
      logFilter.page++;
      renderLogTable();
    };
  }

  if ($('exportCsvBtn')) {
    $('exportCsvBtn').onclick = exportLogsToCSV;
  }

  if ($('clearLog')) {
    $('clearLog').onclick = clearAllLogs;
  }
}

// ===== Render UI =====
const when = t => new Date(t).toLocaleString();

function render() {
  const totalAlerts = log.length;
  const totalIntruders = log.filter(l => l.type === 'unknown_person').length;

  $('sPeople').textContent = dbPeople.length;
  if ($('dbPeopleCount')) $('dbPeopleCount').textContent = dbPeople.length;
  $('sScans').textContent = totalScans;
  $('sAlerts').textContent = totalAlerts;
  if ($('sIntruders')) $('sIntruders').textContent = totalIntruders;

  // Render Alert Distribution Chart Bars
  const counts = {};
  log.forEach(l => counts[l.type] = (counts[l.type] || 0) + 1);
  const max = Math.max(1, ...Object.values(counts));
  if ($('bars')) {
    $('bars').innerHTML = Object.keys(LABELS).map(k => `
      <div class="bar ${k === 'unknown_person' ? 'bad' : ''}">
        <span>${LABELS[k][0]}</span>
        <i style="width:${((counts[k] || 0) / max) * 100}%"></i>
        <b>${counts[k] || 0}</b>
      </div>
    `).join('');
  }

  // Render Recent Alerts for Dashboard
  const item = l => `
    <li>
      <span class="tag ${l.type === 'unknown_person' ? 'bad' : 'warn'}">
        ${esc(LABELS[l.type]?.[0] || l.type)}
      </span>
      <span>${l.faces || 1} មុខ ${l.telegram ? '• 📱 Telegram Sent' : ''}</span>
      <span class="hint x">${when(l.time)}</span>
    </li>
  `;
  if ($('recent')) {
    $('recent').innerHTML = log.slice(0, 5).map(item).join('') || '<li class="empty">មិនទាន់មានការជូនដំណឹង</li>';
  }

  // Render Alert History Table
  renderLogTable();

  // Render Captured Registration Thumbnails
  if ($('shotCount')) $('shotCount').textContent = `${st.photos.length} / ${MAX_PHOTOS} រូប`;
  if ($('thumbs')) {
    $('thumbs').innerHTML = st.photos.map((p, i) => `
      <div>
        <img src="${p}" alt="រូបទី ${i + 1}">
        <button data-i="${i}" aria-label="លុបរូប">×</button>
      </div>
    `).join('');
    $('thumbs').querySelectorAll('button').forEach(b => {
      b.onclick = () => {
        st.photos.splice(+b.dataset.i, 1);
        render();
      };
    });
  }

  // Render Registered People List from Database
  if ($('people')) {
    $('people').innerHTML = dbPeople.map(p => `
      <li>
        <img src="${p.thumbnail || 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 24 24%22 fill=%22%2394a3b8%22><path d=%22M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z%22/></svg>'}" alt="">
        <div>
          <b>${esc(p.name)}</b>
          <div class="hint">${esc(p.role || 'User')} • ${p.samples_count || 1} គំរូមុខ</div>
        </div>
        <span class="tag ok">ក្នុង Database</span>
        <button class="btn ghost x del-person" data-id="${p.id}" data-name="${esc(p.name)}">លុប</button>
      </li>
    `).join('') || '<li class="empty">មិនទាន់មាននរណាចុះឈ្មោះក្នុង Database នៅឡើយ។ ថតរូប ហើយបំពេញព័ត៌មានខាងលើដើម្បីបណ្តុះបណ្តាលមុខ!</li>';

    $('people').querySelectorAll('.del-person').forEach(b => {
      b.onclick = () => deletePerson(b.dataset.id, b.dataset.name);
    });
  }
}

// Initial kickoff
log = deduplicateLogs(log);
save('frs_log', log);
initLogTableListeners();
health();
setInterval(health, 10000);
loadRegisteredPeople();
loadTelegramConfig();
loadLogsFromBackend();
render();

