// ===== ការកំណត់ =====
const API = 'http://localhost:8000';          // អាស័យដ្ឋាន backend
const RECOGNIZE = '/api/recognize';            // មានរួចហើយក្នុង backend
const REGISTER = '/api/faces/register';        // backend ត្រូវបន្ថែម endpoint នេះ
const INTERVAL = 2000, MAX_PHOTOS = 5;

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { toast('ទំហំផ្ទុកក្នុង browser ពេញ'); } };

const LABELS = {
  person_changed: ['មានមនុស្សថ្មី', 'New person detected'],
  scene_changed: ['ទិដ្ឋភាពប្តូរ', 'Scene has changed'],
  scene_and_person_changed: ['មនុស្ស និងទិដ្ឋភាពប្តូរ', 'Scene and person changed'],
  person_left: ['មនុស្សចាកចេញ', 'Person has left the frame'],
};
const TONES = { person_changed: 523.25, scene_changed: 392, scene_and_person_changed: 659.25, person_left: 329.63 };

const st = { scans: 0, alerts: 0, faces: 0, auto: false, timer: null, busy: false, stream: null, photos: [] };
let log = load('frs_log', []), people = load('frs_people', []);

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), 2800);
}

// ===== ការរុករក =====
document.querySelectorAll('.nav').forEach(b => b.onclick = () => show(b.dataset.view));
function show(v) {
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  document.querySelectorAll('.view').forEach(s => s.classList.toggle('on', s.id === v));
  if (v === 'monitor' || v === 'register') initCamera();
  render();
}

// ===== កាមេរ៉ា =====
async function initCamera() {
  if (!st.stream) {
    try { st.stream = await navigator.mediaDevices.getUserMedia({ video: true }); }
    catch { return toast('បើកកាមេរ៉ាមិនបាន។ សូមអនុញ្ញាតកាមេរ៉ាក្នុង browser'); }
  }
  $('video1').srcObject = st.stream; $('video2').srcObject = st.stream;
}
function snap(video, w) {
  const c = $('canvas'), r = video.videoHeight / video.videoWidth || .75;
  c.width = w || video.videoWidth; c.height = Math.round(c.width * r);
  c.getContext('2d').drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', .85);
}

// ===== ការតភ្ជាប់ Backend =====
async function health() {
  try { const r = await fetch(API + '/'); if (!r.ok) throw 0; setConn('ok', 'Backend ភ្ជាប់ហើយ'); }
  catch { setConn('off', 'Backend មិនឆ្លើយតប'); }
}
function setConn(c, t) { $('dot').className = c; $('connText').textContent = t; }

// ===== ស្កេន =====
async function scan() {
  if (st.busy || !st.stream || !$('video1').videoWidth) return !st.stream && toast('កាមេរ៉ាមិនទាន់ត្រៀម');
  st.busy = true; $('scanBtn').disabled = true;
  try {
    const r = await fetch(API + RECOGNIZE, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: snap($('video1')) }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'HTTP ' + r.status);
    const d = await r.json(); setConn('ok', 'Backend ភ្ជាប់ហើយ');
    st.scans++; st.faces = d.faces_found || 0;
    if (d.alert && d.alert_type) {
      st.alerts++; log.unshift({ type: d.alert_type, faces: st.faces, time: new Date().toISOString() });
      log = log.slice(0, 100); save('frs_log', log); alertFx(d.alert_type);
    }
    showResult(d);
  } catch (e) { setConn('off', 'Backend មិនឆ្លើយតប'); $('result').className = 'empty'; $('result').textContent = 'កំហុស៖ ' + e.message; }
  st.busy = false; $('scanBtn').disabled = false; render();
}
function showResult(d) {
  const a = d.alert_type, el = $('result');
  el.className = d.alert ? 'flash' : '';
  el.innerHTML = `<span class="tag ${d.alert ? 'warn' : 'ok'}">${d.alert ? esc(LABELS[a]?.[0] || a) : 'គ្មានការប្តូរ'}</span>
  <dl class="kv"><dt>ស្ថានភាព</dt><dd>${d.faces_found ? 'រកឃើញមុខ' : 'មិនឃើញមុខ'}</dd>
  <dt>ចំនួនមុខ</dt><dd>${esc(d.faces_found ?? 0)}</dd>
  <dt>មនុស្សប្តូរ</dt><dd>${d.person_changed ? 'បាទ/ចាស' : 'ទេ'}</dd>
  <dt>ទិដ្ឋភាពប្តូរ</dt><dd>${d.scene_changed ? 'បាទ/ចាស' : 'ទេ'}</dd>
  <dt>ម៉ោង</dt><dd>${new Date().toLocaleTimeString()}</dd></dl>`;
}

// ===== សម្លេង និងសំឡេងនិយាយ =====
let ac;
function alertFx(type) {
  if ($('optSound').checked) {
    ac = ac || new (window.AudioContext || window.webkitAudioContext)();
    const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime;
    o.frequency.value = TONES[type] || 440; o.connect(g); g.connect(ac.destination);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.3, t + .05); g.gain.linearRampToValueAtTime(0, t + .4);
    o.start(t); o.stop(t + .4);
  }
  if ($('optSpeak').checked && 'speechSynthesis' in window) {
    const u = new SpeechSynthesisUtterance(LABELS[type]?.[1] || 'Change detected');
    u.lang = $('optLang').value;
    if (u.lang === 'km-KH') u.text = LABELS[type]?.[0] || 'ការប្តូរ';
    speechSynthesis.speak(u);
  }
}
$('scanBtn').onclick = scan;
$('autoBtn').onclick = () => {
  st.auto = !st.auto; const b = $('autoBtn');
  b.textContent = st.auto ? 'បញ្ឈប់ការតាមដាន' : 'ចាប់ផ្តើមតាមដានស្វ័យប្រវត្តិ';
  b.classList.toggle('stop', st.auto); b.classList.toggle('ghost', !st.auto);
  clearInterval(st.timer); if (st.auto) { scan(); st.timer = setInterval(scan, INTERVAL); }
};
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  const rec = new SR(); rec.lang = 'en-US';
  rec.onresult = e => { const c = e.results[0][0].transcript.toLowerCase(); toast('ឮ៖ ' + c); if (/capture|recognize|scan/.test(c)) scan(); };
  rec.onerror = e => toast('កំហុសសំឡេង៖ ' + e.error);
  $('voiceBtn').onclick = () => rec.start();
} else $('voiceBtn').disabled = true;

// ===== ការចុះឈ្មោះមុខ =====
$('shotBtn').onclick = () => {
  if (!st.stream) return toast('កាមេរ៉ាមិនទាន់ត្រៀម');
  if (st.photos.length >= MAX_PHOTOS) return toast('ថតបានអតិបរមា ' + MAX_PHOTOS + ' រូប');
  st.photos.push(snap($('video2'), 480)); render();
};
$('saveBtn').onclick = async () => {
  const name = $('pName').value.trim(), msg = $('regMsg');
  if (!name) return toast('សូមបញ្ចូលឈ្មោះ');
  if (st.photos.length < 3) return toast('សូមថតយ៉ាងតិច ៣ រូប');
  if (!$('pConsent').checked) return toast('ត្រូវមានការយល់ព្រមពីម្ចាស់មុខ');
  $('saveBtn').disabled = true; let where = 'local';
  try {
    const r = await fetch(API + REGISTER, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, role: $('pRole').value.trim(), images: st.photos }) });
    if (r.ok) where = 'server';
  } catch {}
  const th = new Image(); th.src = st.photos[0]; await th.decode().catch(() => {});
  const c = document.createElement('canvas'); c.width = c.height = 80;
  c.getContext('2d').drawImage(th, (th.width - th.height) / 2, 0, th.height, th.height, 0, 0, 80, 80);
  people.unshift({ id: Date.now(), name, role: $('pRole').value.trim(), thumb: c.toDataURL('image/jpeg', .7), where, time: new Date().toISOString() });
  save('frs_people', people); st.photos = []; $('pName').value = $('pRole').value = ''; $('pConsent').checked = false;
  msg.textContent = where === 'server' ? 'បានរក្សាទុកក្នុង backend។' : 'Backend មិនទាន់មាន endpoint ចុះឈ្មោះ៖ រក្សាទុកក្នុង browser នេះតែប៉ុណ្ណោះ។';
  toast('បានចុះឈ្មោះ ' + name); $('saveBtn').disabled = false; render();
};
$('clearLog').onclick = () => { log = []; save('frs_log', log); render(); };

// ===== បង្ហាញ =====
const when = t => new Date(t).toLocaleString();
function render() {
  $('sPeople').textContent = people.length; $('sScans').textContent = st.scans;
  $('sAlerts').textContent = st.alerts; $('sFaces').textContent = st.faces;
  const counts = {}; log.forEach(l => counts[l.type] = (counts[l.type] || 0) + 1);
  const max = Math.max(1, ...Object.values(counts));
  $('bars').innerHTML = Object.keys(LABELS).map(k => `<div class="bar"><span>${LABELS[k][0]}</span><i style="width:${(counts[k] || 0) / max * 100}%"></i><b>${counts[k] || 0}</b></div>`).join('');
  const item = l => `<li><span class="tag warn">${esc(LABELS[l.type]?.[0] || l.type)}</span><span>${l.faces} មុខ</span><span class="hint x">${when(l.time)}</span></li>`;
  $('recent').innerHTML = log.slice(0, 5).map(item).join('') || '<li class="empty">មិនទាន់មានការជូនដំណឹង</li>';
  $('logList').innerHTML = log.map(item).join('') || '<li class="empty">ប្រវត្តិទទេ</li>';
  $('shotCount').textContent = st.photos.length + ' / ' + MAX_PHOTOS + ' រូប';
  $('thumbs').innerHTML = st.photos.map((p, i) => `<div><img src="${p}" alt="រូបទី ${i + 1}"><button data-i="${i}" aria-label="លុបរូប">×</button></div>`).join('');
  $('thumbs').querySelectorAll('button').forEach(b => b.onclick = () => { st.photos.splice(+b.dataset.i, 1); render(); });
  $('people').innerHTML = people.map(p => `<li><img src="${p.thumb}" alt=""><div><b>${esc(p.name)}</b><div class="hint">${esc(p.role || '—')}</div></div>
    <span class="tag ${p.where === 'server' ? 'ok' : 'warn'}">${p.where === 'server' ? 'ក្នុង backend' : 'ក្នុង browser'}</span>
    <button class="btn ghost x" data-id="${p.id}">លុប</button></li>`).join('') || '<li class="empty">មិនទាន់មាននរណាចុះឈ្មោះ។ ថតរូប ហើយបំពេញព័ត៌មានខាងលើ។</li>';
  $('people').querySelectorAll('button').forEach(b => b.onclick = () => { people = people.filter(p => p.id != b.dataset.id); save('frs_people', people); render(); });
}
health(); setInterval(health, 10000); render();