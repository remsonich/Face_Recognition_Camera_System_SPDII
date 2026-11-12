// ===== API Endpoints =====
const API = 'http://localhost:8000';
const RECOGNIZE = '/api/recognize';
const REGISTER = '/api/faces/register';
const FACES = '/api/faces';
const TG_CONFIG = '/api/telegram/config';
const TG_TEST = '/api/telegram/test';
const INTERVAL = 2200;
const MAX_PHOTOS = 5;

// Helper utilities
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { toast('ទំហំផ្ទុកក្នុង browser ពេញ'); } };

// Labels for alerts
const LABELS = {
  unknown_person: ['🚨 ជនមិនស្គាល់អត្តសញ្ញាណ / ជនចម្លែក', 'Warning: Unknown person detected!'],
  person_changed: ['មានមនុស្សថ្មី', 'New person detected'],
  scene_changed: ['ទិដ្ឋភាពប្តូរ', 'Scene has changed'],
  scene_and_person_changed: ['មនុស្ស និងទិដ្ឋភាពប្តូរ', 'Scene and person changed'],
  person_left: ['មនុស្សចាកចេញ', 'Person has left the frame'],
};

// Sound frequencies for oscillator alerts
const TONES = {
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
  if (v === 'register') loadRegisteredPeople();
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
async function scan() {
  if (st.busy || !st.stream || !$('video1').videoWidth) {
    if (!st.stream) toast('កាមេរ៉ាមិនទាន់ត្រៀម');
    return;
  }

  st.busy = true;
  $('scanBtn').disabled = true;

  try {
    const imgData = snap($('video1'));
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
    setConn('ok', 'Backend ភ្ជាប់ហើយ');
    st.scans++;
    st.faces = d.faces_found || 0;

    if (d.alert_type === 'unknown_person') {
      st.intruders++;
    }

    if (d.alert && d.alert_type) {
      st.alerts++;
      log.unshift({
        type: d.alert_type,
        faces: st.faces,
        matched: d.matched_users,
        telegram: d.telegram_sent,
        time: new Date().toISOString()
      });
      log = log.slice(0, 100);
      save('frs_log', log);
      alertFx(d.alert_type, d.matched_users);
    }

    showResult(d);
  } catch (e) {
    setConn('off', 'Backend មិនឆ្លើយតប');
    $('result').className = 'empty';
    $('result').textContent = 'កំហុស៖ ' + e.message;
  }

  st.busy = false;
  $('scanBtn').disabled = false;
  render();
}

function showResult(d) {
  const el = $('result');
  const isUnknown = d.alert_type === 'unknown_person';
  const isAllKnown = d.faces_found > 0 && d.unknown_faces_count === 0 && d.matched_users.length > 0;

  el.className = isUnknown ? 'flash intruder' : (d.alert ? 'flash' : '');

  let statusBadge = '';
  if (isUnknown) {
    statusBadge = `<span class="tag bad">🚨 ជនមិនស្គាល់អត្តសញ្ញាណ (INTRUDER)</span>`;
  } else if (isAllKnown) {
    statusBadge = `<span class="tag ok">✅ ស្គាល់អត្តសញ្ញាណ (AUTHORIZED)</span>`;
  } else if (d.faces_found === 0) {
    statusBadge = `<span class="tag">គ្មានមនុស្សក្នុងកាមេរ៉ា</span>`;
  } else {
    statusBadge = `<span class="tag warn">${esc(LABELS[d.alert_type]?.[0] || d.alert_type)}</span>`;
  }

  // Intruder or Authorized Banner
  let alertBanner = '';
  if (dbPeople.length === 0) {
    alertBanner = `
      <div class="alert-box warn" style="background:#fef3c7; border:1px solid #f59e0b; color:#92400e; margin:10px 0; padding:12px; border-radius:8px">
        ⚠️ <b>មិនទាន់មានមនុស្សក្នុង Database នៅឡើយទេ!</b><br>
        សូមចូលទៅកាន់ផ្ទាំង <b>«ចុះឈ្មោះមុខ»</b> ដើម្បីថតរូប និងចុះឈ្មោះមុខរបស់អ្នកជាមុនសិន។
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
      facesListHtml += `
        <div class="face-item ${f.matched ? 'known' : 'unknown'}">
          <div>
            <b>${f.matched ? '👤 ' + esc(f.name) : '❓ ជនមិនស្គាល់ (Unknown)'}</b>
            ${f.role ? `<span class="hint"> (${esc(f.role)})</span>` : ''}
          </div>
          <span class="tag ${f.matched ? 'ok' : 'bad'}">
            ${f.matched ? f.confidence + '% ផ្ទៀងផ្ទាត់' : 'មិនស្គាល់'}
          </span>
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

      if (type === 'unknown_person') {
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
    if (type === 'unknown_person') {
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
  b.textContent = st.auto ? 'បញ្ឈប់ការតាមដាន' : 'ចាប់ផ្តើមតាមដានស្វ័យប្រវត្តិ';
  b.classList.toggle('stop', st.auto);
  b.classList.toggle('ghost', !st.auto);
  clearInterval(st.timer);
  if (st.auto) {
    scan();
    st.timer = setInterval(scan, INTERVAL);
  }
};

// Speech recognition voice command
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  const rec = new SR();
  rec.lang = 'en-US';
  rec.onresult = e => {
    const c = e.results[0][0].transcript.toLowerCase();
    toast('ឮ៖ ' + c);
    if (/capture|recognize|scan|check/.test(c)) scan();
  };
  rec.onerror = e => toast('កំហុសសំឡេង៖ ' + e.error);
  $('voiceBtn').onclick = () => rec.start();
} else {
  $('voiceBtn').disabled = true;
}

// ===== Face Registration =====
$('shotBtn').onclick = () => {
  initCamera();
  const v2 = $('video2');
  if (!st.stream || !v2 || !v2.videoWidth) {
    return toast('កាមេរ៉ាមិនទាន់ត្រៀម សូមរង់ចាំ ២ វិនាទី');
  }
  if (st.photos.length >= MAX_PHOTOS) {
    return toast('ថតបានអតិបរមា ' + MAX_PHOTOS + ' រូប');
  }

  const p = snap(v2, 480);
  if (p) {
    st.photos.push(p);
    toast(`📸 បានថតរូបគំរូទី ${st.photos.length}`);
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

    toast(`✅ បានចុះឈ្មោះ ${name} ជោគជ័យ!`);
    msg.innerHTML = `<span style="color:var(--ok); font-weight:600">✅ បានរក្សាទុកក្នុង Database ជោគជ័យ (${res.encodings_saved} គំរូមុខ)! ឥឡូវចូលទៅកាន់ «តាមដានផ្ទាល់» ដើម្បីសាកល្បង។</span>`;
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

$('clearLog').onclick = () => {
  log = [];
  save('frs_log', log);
  render();
};

// ===== Render UI =====
const when = t => new Date(t).toLocaleString();

function render() {
  $('sPeople').textContent = dbPeople.length;
  $('dbPeopleCount').textContent = dbPeople.length;
  $('sScans').textContent = st.scans;
  $('sAlerts').textContent = st.alerts;
  if ($('sIntruders')) $('sIntruders').textContent = st.intruders;

  // Render Alert Distribution Chart Bars
  const counts = {};
  log.forEach(l => counts[l.type] = (counts[l.type] || 0) + 1);
  const max = Math.max(1, ...Object.values(counts));
  $('bars').innerHTML = Object.keys(LABELS).map(k => `
    <div class="bar ${k === 'unknown_person' ? 'bad' : ''}">
      <span>${LABELS[k][0]}</span>
      <i style="width:${((counts[k] || 0) / max) * 100}%"></i>
      <b>${counts[k] || 0}</b>
    </div>
  `).join('');

  // Render Recent Alerts and Log
  const item = l => `
    <li>
      <span class="tag ${l.type === 'unknown_person' ? 'bad' : 'warn'}">
        ${esc(LABELS[l.type]?.[0] || l.type)}
      </span>
      <span>${l.faces} មុខ ${l.telegram ? '• 📱 Telegram Sent' : ''}</span>
      <span class="hint x">${when(l.time)}</span>
    </li>
  `;
  $('recent').innerHTML = log.slice(0, 5).map(item).join('') || '<li class="empty">មិនទាន់មានការជូនដំណឹង</li>';
  $('logList').innerHTML = log.map(item).join('') || '<li class="empty">ប្រវត្តិទទេ</li>';

  // Render Captured Registration Thumbnails
  $('shotCount').textContent = `${st.photos.length} / ${MAX_PHOTOS} រូប`;
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

  // Render Registered People List from Database
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

// Initial kickoff
health();
setInterval(health, 10000);
loadRegisteredPeople();
loadTelegramConfig();
render();
