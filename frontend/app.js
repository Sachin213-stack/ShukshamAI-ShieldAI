// ===== CONFIG =====
// API_BASE is managed dynamically — see bottom of file (reads from localStorage)
const getAPI = () => localStorage.getItem('shieldai_api_base') || 'http://127.0.0.1:8000/api';

// ===== STATE =====
let currentScanId = null;
let currentTrace  = [];
let currentTab    = 'scan';
let inputType     = 'sms';
let isScanning    = false; // deduplication flag — prevents double-tap API calls

// ===== OFFLINE SCAN QUEUE =====
const QUEUE_KEY = 'shieldai_offline_queue';

function getQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
  catch { return []; }
}
function saveQueue(q) { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }
function enqueue(item) {
  const q = getQueue();
  q.push({ ...item, queued_at: new Date().toISOString() });
  saveQueue(q);
  updateQueueBadge();
  showToast(`📥 Queued! Will send when online. (${q.length} pending)`, 3500);
}
function updateQueueBadge() {
  const count = getQueue().length;
  let badge = document.getElementById('queueBadge');
  if (!badge) return;
  badge.textContent = count;
  badge.style.display = count > 0 ? 'flex' : 'none';
}
async function replayQueue() {
  const q = getQueue();
  if (!q.length) return;
  showToast(`🔄 Back online! Sending ${q.length} queued scan(s)…`, 3000);
  const remaining = [];
  for (const item of q) {
    try {
      const res = await fetch(`${getAPI()}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_text: item.message_text, sender_id: item.sender_id }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderResult(data);
      loadStats();
    } catch(err) {
      if (isNetworkError(err)) remaining.push(item); // still offline, keep in queue
      else console.error('[Queue] Non-network error replaying scan:', err);
    }
  }
  saveQueue(remaining);
  updateQueueBadge();
  if (!remaining.length) showToast('✅ All queued scans sent!', 2500);
}
// Auto-replay when connection returns
window.addEventListener('online', () => {
  replayQueue();
  loadStats();
});

const INPUT_LABELS = {
  sms:   '📱 Paste or type a suspicious SMS',
  email: '📧 Paste a suspicious email body',
  call:  '📞 Paste a call transcript',
  link:  '🔗 Paste a suspicious link or URL',
};

// ===== CLOCK =====
function updateClock() {
  const now = new Date();
  const h = now.getHours().toString().padStart(2,'0');
  const m = now.getMinutes().toString().padStart(2,'0');
  const el = document.getElementById('statusTime');
  if (el) el.textContent = `${h}:${m}`;
}
setInterval(updateClock, 10000);
updateClock();

// ===== CHAR COUNT =====
document.getElementById('messageInput').addEventListener('input', function() {
  document.getElementById('charCount').textContent = this.value.length;
});

// ===== INPUT TYPE =====
function setInputType(type, btn) {
  inputType = type;
  document.querySelectorAll('.type-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('inputTypeLabel').textContent = INPUT_LABELS[type];
  if (type === 'link') {
    document.querySelector('.textarea').rows = 2;
    document.getElementById('messageInput').placeholder = 'e.g. https://amaz0n-login.xyz/verify';
  } else {
    document.querySelector('.textarea').rows = 5;
    document.getElementById('messageInput').placeholder = 'Paste the suspicious message here…';
  }
}

// ===== TABS =====
function switchTab(tab) {
  currentTab = tab;
  ['scan','notifications','history','trace'].forEach(t => {
    document.getElementById(`tab-${t}`).classList.toggle('active', t === tab);
    document.getElementById(`tab-${t}`).setAttribute('aria-selected', t === tab);
    document.getElementById(`panel-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'history') loadHistory();
  if (tab === 'notifications') renderNotifFeed();
}

function goNav(tab) {
  ['scan','notifications','history','trace'].forEach(t => {
    const el = document.getElementById(`nav-${t}`);
    if (el) el.classList.toggle('active', t === tab);
  });
  switchTab(tab);
}

// ===== RESULT SUB-TABS =====
function switchResultTab(tab, btn) {
  document.querySelectorAll('.r-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.r-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(`r-${tab}`).classList.add('active');
}

// ===== TOAST =====
let toastTimer;
function showToast(msg, duration = 2800) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// ===== OVERLAY =====
let stepTimer;
function showOverlay() {
  document.getElementById('scanOverlay').classList.remove('hidden');
  document.getElementById('scanBtn').disabled = true;
  // animate through agent steps
  const steps = ['scanner','researcher','reasoner'];
  let i = 0;
  resetSteps();
  activateStep(steps[i]);
  stepTimer = setInterval(() => {
    markStepDone(steps[i]);
    i++;
    if (i < steps.length) activateStep(steps[i]);
    else clearInterval(stepTimer);
  }, 1800);
}
function hideOverlay() {
  clearInterval(stepTimer);
  document.getElementById('scanOverlay').classList.add('hidden');
  document.getElementById('scanBtn').disabled = false;
}
function resetSteps() {
  ['scanner','researcher','reasoner'].forEach(s => {
    const el = document.getElementById(`step-${s}`);
    el.classList.remove('active','done');
  });
}
function activateStep(s) {
  const el = document.getElementById(`step-${s}`);
  if (el) el.classList.add('active');
}
function markStepDone(s) {
  const el = document.getElementById(`step-${s}`);
  if (el) { el.classList.remove('active'); el.classList.add('done'); }
}

// ===== MAIN SCAN =====
async function runScan() {
  if (isScanning) { showToast('⏳ Already analyzing… please wait'); return; }

  const message = document.getElementById('messageInput').value.trim();
  const sender  = document.getElementById('senderInput').value.trim();

  if (!message) { showToast('⚠️ Please enter a message to analyze'); return; }

  isScanning = true;
  showOverlay();
  document.getElementById('resultCard').classList.add('hidden');

  try {
    const res = await fetch(`${getAPI()}/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_text: message, sender_id: sender || 'unknown' }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    await new Promise(r => setTimeout(r, 600));
    hideOverlay();
    renderResult(data);
    loadStats();

  } catch (err) {
    hideOverlay();
    console.error(err);
    if (isNetworkError(err)) {
      // Offer to queue the scan for when connectivity returns
      showApiOfflineModal(message, sender || 'unknown');
    } else {
      showToast('❌ Error: ' + err.message, 4000);
    }
  } finally {
    isScanning = false;
  }
}

// ===== NETWORK ERROR DETECTION =====
function isNetworkError(err) {
  const msg = (err.message || '').toLowerCase();
  return msg.includes('failed to fetch') ||
         msg.includes('networkerror') ||
         msg.includes('network request failed') ||
         msg.includes('load failed') ||
         msg.includes('err_connection_refused');
}

// Show Settings modal with a helpful offline message + queue option
function showApiOfflineModal(messageText, senderId) {
  const input   = document.getElementById('apiUrlInput');
  const current = getAPI();
  input.value   = current;
  document.getElementById('settingsModal').classList.remove('hidden');
  const hint = document.querySelector('.modal-hint');
  hint.innerHTML = `
    <span style="color:var(--danger);font-weight:700">🚨 Can’t reach the server!</span><br/>
    Tried <code>${current}</code> — no response.<br/><br/>
    <strong>Option A:</strong> Fix the IP below and re-scan.<br/>
    <strong>Option B:</strong>
    <button onclick="queueCurrentScan('${(messageText||'').replace(/'/g, '\'').substring(0,80)}','${(senderId||'unknown').replace(/'/g, '\'')}')" style="background:rgba(108,99,255,.25);border:1px solid #6C63FF;color:#a9a4ff;padding:3px 10px;border-radius:6px;font-size:12px;cursor:pointer;margin-left:4px">📥 Queue for later</button><br/>
    <small style="color:var(--text3)">Queued scans send automatically when you’re back online.</small><br/><br/>
    PC IP: <code>10.195.110.169</code>
  `;
  input.focus();
  input.select();
}

function queueCurrentScan(messageText, senderId) {
  enqueue({ message_text: messageText, sender_id: senderId });
  document.getElementById('settingsModal').classList.add('hidden');
}

// ===== DEMO RESULT (when API is offline) =====
function showDemoResult() {
  const demo = {
    scan_id: 'DEMO-001',
    is_fraud: true,
    confidence_score: 0.94,
    analysis_reason: 'This message exhibits multiple high-risk fraud indicators: urgent financial pressure tactics, suspicious shortened URL, impersonation of a legitimate bank, and a request for sensitive credentials. The sender ID does not match official bank communications.',
    evidence_summary: 'Pattern matches known phishing campaigns targeting banking customers. URL domain registered 3 days ago. Similar messages flagged in threat intelligence databases.',
    urls_found: ['http://b4nk-secure-login.xyz/verify', 'http://bit.ly/3xAbCdE'],
    url_risk_level: 'malicious',
    tools_used: ['web_search', 'url_scanner', 'pattern_db'],
    agent_trace: [
      { agent: 'Scanner', output: 'Detected urgent language, spoofed bank name, and 2 suspicious URLs. Initial risk: HIGH.', tools_used: ['pattern_db'] },
      { agent: 'Researcher', output: 'URL b4nk-secure-login.xyz registered 3 days ago. Found matching phishing kit on VirusTotal. Domain flagged by 18/76 security vendors.', tools_used: ['web_search','url_scanner'] },
      { agent: 'Reasoner', output: 'All evidence converges to a high-confidence phishing attack targeting banking credentials. Confidence: 94%. Do NOT click any links or provide any information.', tools_used: [] },
    ]
  };
  showToast('🔌 API offline — showing demo result', 3500);
  renderResult(demo);
}

// ===== RENDER RESULT =====
function renderResult(data) {
  currentScanId = data.scan_id;
  currentTrace  = data.agent_trace || [];

  const isFraud = data.is_fraud;
  const conf    = Math.round((data.confidence_score || 0) * 100);

  const card   = document.getElementById('resultCard');
  const header = document.getElementById('resultHeader');
  const icon   = document.getElementById('resultIcon');
  const verdict= document.getElementById('resultVerdict');
  const scanId = document.getElementById('resultId');

  card.classList.remove('hidden');
  header.className = 'result-header ' + (isFraud ? 'fraud' : 'safe');
  icon.textContent   = isFraud ? '🚨' : '✅';
  verdict.textContent= isFraud ? 'Fraud Detected!' : 'Looks Safe';
  verdict.style.color= isFraud ? 'var(--danger)' : 'var(--safe)';
  scanId.textContent = `Scan #${data.scan_id}`;

  // Gauge
  document.getElementById('confPct').textContent = conf + '%';
  setTimeout(() => { document.getElementById('gaugeFill').style.width = conf + '%'; }, 80);

  // Badges
  const badgeRow = document.getElementById('badgeRow');
  badgeRow.innerHTML = '';
  if (isFraud) addBadge(badgeRow, '🚨 FRAUD', 'danger');
  else          addBadge(badgeRow, '✅ SAFE',  'safe');
  if (data.url_risk_level === 'malicious') addBadge(badgeRow, '🔴 Malicious URL', 'danger');
  else if (data.url_risk_level === 'suspicious') addBadge(badgeRow, '🟡 Suspicious URL', 'warn');
  if (data.tools_used && data.tools_used.length) {
    data.tools_used.forEach(t => addBadge(badgeRow, '🔧 ' + t, 'info'));
  }
  addBadge(badgeRow, `${conf}% confidence`, conf > 75 ? 'danger' : conf > 45 ? 'warn' : 'safe');

  // Text panels
  document.getElementById('reasonText').textContent   = data.analysis_reason   || '—';
  document.getElementById('evidenceText').textContent = data.evidence_summary  || 'No additional evidence collected.';

  // URLs
  const urlsList = document.getElementById('urlsList');
  urlsList.innerHTML = '';
  if (data.urls_found && data.urls_found.length) {
    data.urls_found.forEach(url => {
      const div = document.createElement('div');
      div.className = 'url-item';
      div.innerHTML = `<span style="font-size:16px">${data.url_risk_level === 'malicious' ? '🔴' : '🟡'}</span><span class="url-item-text">${url}</span>`;
      urlsList.appendChild(div);
    });
  } else {
    urlsList.innerHTML = '<p class="url-no-data">No URLs found in this message.</p>';
  }

  // Scroll into view
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Pre-build trace
  buildTrace(data);
}

function addBadge(container, text, type) {
  const b = document.createElement('div');
  b.className = `badge badge-${type}`;
  b.textContent = text;
  container.appendChild(b);
}

// ===== VIEW TRACE =====
function viewTrace() {
  goNav('trace');
}

function buildTrace(data) {
  const empty     = document.getElementById('traceEmpty');
  const container = document.getElementById('traceContainer');
  const info      = document.getElementById('traceScanInfo');
  const pipeline  = document.getElementById('agentPipeline');

  if (!data.agent_trace || !data.agent_trace.length) return;

  empty.style.display = 'none';
  container.classList.remove('hidden');

  info.innerHTML = `<strong>Scan ID:</strong> ${data.scan_id} &nbsp;|&nbsp; <strong>Verdict:</strong> <span style="color:${data.is_fraud?'var(--danger)':'var(--safe)'}">${data.is_fraud?'FRAUD':'SAFE'}</span> &nbsp;|&nbsp; <strong>Confidence:</strong> ${Math.round((data.confidence_score||0)*100)}%`;

  pipeline.innerHTML = '';

  const AGENT_META = {
    Scanner:    { color: '#6C63FF', bg: 'rgba(108,99,255,0.15)', emoji: '🔍', role: 'First-pass pattern detection' },
    Researcher: { color: '#48C6EF', bg: 'rgba(72,198,239,0.15)', emoji: '🔬', role: 'Deep evidence investigation'  },
    Reasoner:   { color: '#ff6b9d', bg: 'rgba(255,107,157,0.15)',emoji: '🧠', role: 'Final verdict synthesis'       },
  };

  // ── Normalize each step: support both old schema (agent/output) and new (agent_name/action/observation) ──
  const normalizeStep = (step) => {
    const name = step.agent_name || step.agent || 'Agent';
    const agentKey = name.charAt(0).toUpperCase() + name.slice(1).toLowerCase();
    // Extract tool name from "Called extract_urls" pattern
    const toolMatch = (step.action || '').match(/^Called\s+(.+)$/i);
    const tool = toolMatch ? toolMatch[1] : null;
    return {
      agentKey,
      action:      step.action      || step.output || '—',
      observation: step.observation || '',
      tool,
      timestamp:   step.timestamp   || '',
    };
  };

  // ── Group consecutive steps by agent name ──
  const groups = [];
  for (const raw of data.agent_trace) {
    const s = normalizeStep(raw);
    if (groups.length && groups[groups.length - 1].agentKey === s.agentKey) {
      groups[groups.length - 1].steps.push(s);
    } else {
      groups.push({ agentKey: s.agentKey, steps: [s] });
    }
  }

  groups.forEach((group, idx) => {
    const meta = AGENT_META[group.agentKey] || { color: '#8892b0', bg: 'rgba(136,146,176,0.1)', emoji: '🤖', role: 'Agent' };
    const tools = [...new Set(group.steps.map(s => s.tool).filter(Boolean))];

    if (idx > 0) {
      const conn = document.createElement('div');
      conn.className = 'pipeline-connector';
      pipeline.appendChild(conn);
    }

    // Build steps HTML
    const stepsHtml = group.steps.map(s => `
      <div class="trace-step">
        <div class="trace-action">${s.action}</div>
        ${s.observation ? `<div class="trace-obs">${s.observation}</div>` : ''}
      </div>`).join('');

    const toolsHtml = tools.length
      ? `<div class="agent-tools">${tools.map(t => `<span class="tool-tag">🔧 ${t}</span>`).join('')}</div>`
      : '';

    const node = document.createElement('div');
    node.className = 'agent-node';
    node.innerHTML = `
      <div class="agent-node-header" onclick="toggleAgent(this)">
        <div class="agent-avatar" style="background:${meta.bg}; border:1px solid ${meta.color}40">${meta.emoji}</div>
        <div>
          <div class="agent-name" style="color:${meta.color}">${group.agentKey} Agent</div>
          <div class="agent-role">${meta.role} · ${group.steps.length} step${group.steps.length > 1 ? 's' : ''}</div>
        </div>
        <svg class="agent-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="agent-body">
        <div class="trace-steps">${stepsHtml}</div>
        ${toolsHtml}
      </div>`;
    pipeline.appendChild(node);
  });

  // auto-open first node
  const firstHeader = pipeline.querySelector('.agent-node-header');
  if (firstHeader) toggleAgent(firstHeader);
}

function toggleAgent(header) {
  const body    = header.nextElementSibling;
  const chevron = header.querySelector('.agent-chevron');
  const isOpen  = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  chevron.classList.toggle('open', !isOpen);
}

// ===== LOAD STATS =====
async function loadStats() {
  try {
    const res  = await fetch(`${getAPI()}/stats`);
    const data = await res.json();
    document.getElementById('statTotal').textContent = data.total_scans       ?? '—';
    document.getElementById('statFraud').textContent = data.total_fraud_detected ?? '—';
    document.getElementById('statPct').textContent   = (data.fraud_percentage ?? '—') + '%';
  } catch(err) {
    // Silently show dashes — network check happens on scan attempt
  }
}

// ===== LOAD HISTORY =====
async function loadHistory() {
  const list = document.getElementById('historyList');
  list.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading history…</p></div>';
  try {
    const res  = await fetch(`${getAPI()}/history?limit=30`);
    if (!res.ok) throw new Error('API error');
    const data = await res.json();
    if (!data.length) {
      list.innerHTML = '<div class="loading-state"><p style="color:var(--text3)">No scans yet. Run your first scan!</p></div>';
      return;
    }
    list.innerHTML = '';
    data.forEach(item => list.appendChild(buildHistoryItem(item)));
  } catch(err) {
    if (isNetworkError(err)) {
      list.innerHTML = `
        <div class="loading-state" style="gap:16px">
          <p style="color:var(--danger);font-weight:700">🚨 Can’t reach server</p>
          <p style="color:var(--text2);font-size:13px">Make sure your PC & phone are on the<br/>same Wi-Fi, then set your server IP.</p>
          <button onclick="openSettings()" style="padding:10px 22px;background:linear-gradient(135deg,#6C63FF,#48C6EF);border:none;border-radius:10px;color:#fff;font-weight:700;font-size:13px;cursor:pointer">⚙️ Set Server IP</button>
        </div>`;
    } else {
      list.innerHTML = `<div class="loading-state"><p style="color:var(--text3)">⚡ API offline. Run the backend to see history.</p></div>`;
    }
  }
}

function buildHistoryItem(item) {
  const div = document.createElement('div');
  div.className = `history-item ${item.is_fraud ? 'fraud-item' : 'safe-item'}`;
  const conf = Math.round((item.confidence_score||0)*100);
  const time = item.created_at ? new Date(item.created_at).toLocaleString() : '';
  div.innerHTML = `
    <div class="hi-top">
      <div class="hi-sender">${item.sender_id || 'Unknown'}</div>
      <div class="hi-time">${time}</div>
    </div>
    <div class="hi-msg">${item.message_text}</div>
    <div class="hi-bottom">
      <span class="hi-verdict ${item.is_fraud?'fraud':'safe'}">${item.is_fraud ? '🚨 FRAUD' : '✅ SAFE'}</span>
      <span class="hi-conf">${conf}% conf.</span>
    </div>`;
  div.addEventListener('click', () => {
    buildTrace(item);
    goNav('trace');
  });
  return div;
}

// ===== INIT =====
loadStats();
// Restore queue badge count from previous session
window.addEventListener('DOMContentLoaded', updateQueueBadge);
// Also update immediately (if DOMContentLoaded already fired)
setTimeout(updateQueueBadge, 0);

// ===== SETTINGS =====
// Load saved API URL on startup
(function() {
  const saved = localStorage.getItem('shieldai_api_base');
  if (saved) { window.API_BASE = saved; }
})();

function openSettings() {
  const modal = document.getElementById('settingsModal');
  document.getElementById('apiUrlInput').value = window.API_BASE || 'http://127.0.0.1:8000/api';
  modal.classList.remove('hidden');
}

function closeSettings(e) {
  if (e && e.target !== document.getElementById('settingsModal')) return;
  document.getElementById('settingsModal').classList.add('hidden');
}

function saveSettings() {
  let val = document.getElementById('apiUrlInput').value.trim().replace(/\/$/, '');
  if (!val) { showToast('⚠️ Please enter a valid URL'); return; }
  
  if (!val.startsWith('http://') && !val.startsWith('https://')) {
    val = 'http://' + val;
  }
  if (!val.endsWith('/api')) {
    val = val + '/api';
  }

  window.API_BASE = val;
  localStorage.setItem('shieldai_api_base', val);
  document.getElementById('settingsModal').classList.add('hidden');
  showToast('✅ Connected to ' + val, 3000);
  loadStats();
}

// Override API_BASE to use dynamic value
Object.defineProperty(window, 'API_BASE', {
  get() { return localStorage.getItem('shieldai_api_base') || 'http://127.0.0.1:8000'; },
  set(v) { localStorage.setItem('shieldai_api_base', v); },
  configurable: true,
});

// ===== NOTIFICATION LISTENER MODULE =====
// Detects Capacitor native runtime for real notification access,
// falls back to a simulated demo feed on plain web browsers.

const NOTIF_STORE_KEY = 'shieldai_notifications';
const NOTIF_AUTOSCAN_KEY = 'shieldai_autoscan';
const NOTIF_ALERT_SOUND_KEY = 'shieldai_alert_sound';
let isCapacitor = false;

// Known app packages → friendly names + icons
const APP_META = {
  'com.google.android.apps.messaging': { name: 'Messages', icon: '💬' },
  'com.whatsapp': { name: 'WhatsApp', icon: '📱' },
  'org.telegram.messenger': { name: 'Telegram', icon: '✈️' },
  'com.facebook.orca': { name: 'Messenger', icon: '💙' },
  'com.instagram.android': { name: 'Instagram', icon: '📸' },
  'com.google.android.gm': { name: 'Gmail', icon: '📧' },
  'com.microsoft.office.outlook': { name: 'Outlook', icon: '📨' },
  'com.android.mms': { name: 'SMS', icon: '📩' },
  'default': { name: 'App', icon: '🔔' },
};

function getAppMeta(packageName) {
  return APP_META[packageName] || APP_META['default'];
}

// --- Storage ---
function getNotifications() {
  try { return JSON.parse(localStorage.getItem(NOTIF_STORE_KEY) || '[]'); }
  catch { return []; }
}
function saveNotifications(arr) {
  localStorage.setItem(NOTIF_STORE_KEY, JSON.stringify(arr));
}
function getAutoScan() {
  return localStorage.getItem(NOTIF_AUTOSCAN_KEY) === 'true';
}
function getAlertSound() {
  return localStorage.getItem(NOTIF_ALERT_SOUND_KEY) === 'true';
}

// --- Badge Updates ---
function updateNotifBadge() {
  const notifs = getNotifications();
  const unscanned = notifs.filter(n => n.status === 'unscanned').length;
  const badge = document.getElementById('notifBadge');
  const navBadge = document.getElementById('navNotifBadge');
  if (badge) {
    badge.textContent = unscanned;
    badge.style.display = unscanned > 0 ? 'grid' : 'none';
  }
  if (navBadge) {
    navBadge.textContent = unscanned;
    navBadge.style.display = unscanned > 0 ? 'flex' : 'none';
  }
  const feedCount = document.getElementById('notifFeedCount');
  if (feedCount) feedCount.textContent = `${notifs.length} captured`;
}

// --- Render Feed ---
function renderNotifFeed() {
  const feed = document.getElementById('notifFeed');
  const empty = document.getElementById('notifEmpty');
  const notifs = getNotifications();

  if (!notifs.length) {
    feed.innerHTML = '';
    feed.appendChild(empty);
    empty.style.display = 'flex';
    updateNotifBadge();
    return;
  }

  empty.style.display = 'none';
  feed.innerHTML = '';

  // Most recent first
  notifs.slice().reverse().forEach((n, idx) => {
    const realIdx = notifs.length - 1 - idx;
    const meta = getAppMeta(n.packageName);
    const time = n.timestamp ? new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

    const statusClass = n.status || 'unscanned';
    const statusLabels = {
      unscanned: '⏳ Unscanned',
      scanning: '🔍 Scanning…',
      fraud: '🚨 FRAUD',
      safe: '✅ SAFE',
    };

    const div = document.createElement('div');
    div.className = `notif-item status-${statusClass}`;
    div.innerHTML = `
      <div class="notif-item-top">
        <div class="notif-app-icon">${meta.icon}</div>
        <div class="notif-item-meta">
          <div class="notif-app-name">${meta.name}</div>
          <div class="notif-item-title">${escapeHtml(n.title || 'Notification')}</div>
        </div>
        <span class="notif-item-time">${time}</span>
      </div>
      <div class="notif-item-body">${escapeHtml(n.text || '')}</div>
      <div class="notif-item-footer">
        <span class="notif-status-pill ${statusClass}">${statusLabels[statusClass] || statusClass}</span>
        ${statusClass === 'unscanned' ? `<button class="notif-scan-btn" onclick="event.stopPropagation(); scanNotification(${realIdx})">🔍 Scan</button>` : ''}
        ${n.confidence != null ? `<span style="font-size:10px;color:var(--text3);margin-left:auto">${Math.round(n.confidence*100)}% conf.</span>` : ''}
      </div>
    `;
    // Tap the whole item to pre-fill scanner
    div.addEventListener('click', () => prefillFromNotification(n));
    feed.appendChild(div);
  });

  updateNotifBadge();
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Scan a specific notification ---
async function scanNotification(index) {
  const notifs = getNotifications();
  const n = notifs[index];
  if (!n || n.status === 'scanning') return;

  n.status = 'scanning';
  saveNotifications(notifs);
  renderNotifFeed();

  try {
    const res = await fetch(`${getAPI()}/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message_text: `[${(n.title || '')}] ${n.text || ''}`,
        sender_id: n.title || n.packageName || 'notification',
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Update notification status
    const updated = getNotifications();
    if (updated[index]) {
      updated[index].status = data.is_fraud ? 'fraud' : 'safe';
      updated[index].confidence = data.confidence_score;
      updated[index].scanResult = data;
      saveNotifications(updated);
    }

    if (data.is_fraud && getAlertSound()) {
      playFraudAlert();
    }

    renderNotifFeed();
    loadStats();
    showToast(data.is_fraud ? '🚨 Fraud detected in notification!' : '✅ Notification looks safe', 3000);
  } catch (err) {
    const updated = getNotifications();
    if (updated[index]) {
      updated[index].status = 'unscanned';
      saveNotifications(updated);
    }
    renderNotifFeed();
    showToast('❌ Scan failed: ' + err.message, 3000);
  }
}

// --- Pre-fill scanner from notification ---
function prefillFromNotification(n) {
  goNav('scan');
  document.getElementById('senderInput').value = n.title || n.packageName || '';
  document.getElementById('messageInput').value = n.text || '';
  document.getElementById('charCount').textContent = (n.text || '').length;
  showToast('📋 Notification loaded into scanner', 2000);
}

// --- Add a new notification ---
function addNotification(notif) {
  const notifs = getNotifications();
  notifs.push({
    id: Date.now() + '-' + Math.random().toString(36).slice(2,7),
    packageName: notif.packageName || 'unknown',
    title: notif.title || '',
    text: notif.text || notif.body || '',
    timestamp: notif.timestamp || new Date().toISOString(),
    status: 'unscanned',
    confidence: null,
    scanResult: null,
  });
  // Keep max 200 notifications
  if (notifs.length > 200) notifs.splice(0, notifs.length - 200);
  saveNotifications(notifs);
  updateNotifBadge();

  // If currently viewing notifications tab, re-render
  if (currentTab === 'notifications') renderNotifFeed();

  // Auto-scan if enabled
  if (getAutoScan()) {
    const idx = notifs.length - 1;
    setTimeout(() => scanNotification(idx), 500);
  }
}

// --- Clear all notifications ---
function clearNotifications() {
  saveNotifications([]);
  renderNotifFeed();
  showToast('🗑️ Notifications cleared', 2000);
}

// --- Auto-scan toggle ---
function toggleAutoScan(enabled) {
  localStorage.setItem(NOTIF_AUTOSCAN_KEY, enabled ? 'true' : 'false');
  // Sync both toggle switches
  const t1 = document.getElementById('autoScanToggle');
  const t2 = document.getElementById('settingsAutoScan');
  if (t1) t1.checked = enabled;
  if (t2) t2.checked = enabled;
  showToast(enabled ? '🤖 Auto-scan enabled' : '⏸️ Auto-scan disabled', 2000);
}

// --- Alert sound toggle ---
function toggleAlertSound(enabled) {
  localStorage.setItem(NOTIF_ALERT_SOUND_KEY, enabled ? 'true' : 'false');
  const t = document.getElementById('settingsAlertSound');
  if (t) t.checked = enabled;
  showToast(enabled ? '🔊 Alert sound enabled' : '🔇 Alert sound disabled', 2000);
}

// --- Play fraud alert ---
function playFraudAlert() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(660, ctx.currentTime + 0.15);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) { /* silent fail */ }
}

// --- Permission Request ---
function requestNotifPermission() {
  if (isCapacitor && window.NotificationsListener) {
    // Real Capacitor: open Android notification access settings
    window.NotificationsListener.requestPermission();
    showToast('📱 Opening notification access settings…', 3000);
  } else {
    // Web fallback: start demo mode with simulated notifications
    showToast('🌐 Running in web mode — starting demo feed', 3000);
    startDemoNotifications();
    const banner = document.getElementById('notifPermBanner');
    const btn = document.getElementById('grantPermBtn');
    if (btn) {
      btn.textContent = '✅ Demo Active';
      btn.classList.add('granted');
    }
  }
}

// --- Capacitor Integration ---
function initCapacitorNotifListener() {
  if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
    isCapacitor = true;
    try {
      const { NotificationsListener } = window.Capacitor.Plugins;
      if (NotificationsListener) {
        window.NotificationsListener = NotificationsListener;

        // Check if already listening
        NotificationsListener.isListening().then(listening => {
          if (listening) {
            NotificationsListener.startListening();
            markPermissionGranted();
          }
        });

        // Listen for new notifications
        NotificationsListener.addListener('notificationReceivedEvent', (notification) => {
          addNotification({
            packageName: notification.packageName || notification.package || '',
            title: notification.title || '',
            text: notification.text || notification.body || '',
            timestamp: new Date().toISOString(),
          });
        });

        NotificationsListener.addListener('notificationRemovedEvent', () => {
          // Optionally handle removal
        });
      }
    } catch (e) {
      console.warn('[ShieldAI] Capacitor notification listener not available:', e);
    }
  }
}

function markPermissionGranted() {
  const banner = document.getElementById('notifPermBanner');
  const btn = document.getElementById('grantPermBtn');
  if (btn) {
    btn.textContent = '✅ Granted';
    btn.classList.add('granted');
  }
}

// --- Demo Notifications (web fallback) ---
let demoInterval = null;
const DEMO_NOTIFICATIONS = [
  { packageName: 'com.google.android.apps.messaging', title: '+1-800-555-0199', text: 'URGENT: Your bank account has been compromised! Click here immediately to secure your funds: http://b4nk-secure.xyz/verify' },
  { packageName: 'com.whatsapp', title: 'Mom', text: 'Hey sweetie, can you pick up some groceries on the way home? Need milk and bread. Love you! 💕' },
  { packageName: 'com.google.android.gm', title: 'Amazon Support', text: 'Your order #384-2847 has been shipped and will arrive tomorrow by 5 PM. Track your package here.' },
  { packageName: 'com.android.mms', title: '+44-7911-123456', text: 'Congratulations! You\'ve won £50,000 in the UK National Lottery! Claim now at: http://uk-l0ttery-prize.com/claim?id=38291' },
  { packageName: 'org.telegram.messenger', title: 'Work Group', text: 'Meeting moved to 3 PM today. Please update your calendars.' },
  { packageName: 'com.google.android.apps.messaging', title: 'HDFC Bank', text: 'INR 15,000 debited from A/c XX2847. If not done by you, call 1800-266-4332 immediately. Do NOT share OTP with anyone.' },
  { packageName: 'com.whatsapp', title: 'Unknown Number', text: 'Hi! I noticed your profile. I am a crypto trader and can help you earn $5000/day. Just invest $200 to start. DM me now!' },
  { packageName: 'com.google.android.gm', title: 'IT Security Team', text: 'Your company password expires in 24 hours. Update now: http://corp-l0gin.net/reset — IT Support Team' },
  { packageName: 'com.facebook.orca', title: 'John', text: 'Hey, did you see the game last night? What a comeback! 🏀' },
  { packageName: 'com.android.mms', title: 'Delivery Service', text: 'Your package could not be delivered. Pay $1.99 redelivery fee here: http://delivery-rschedule.info/pay' },
];
let demoIndex = 0;

function startDemoNotifications() {
  if (demoInterval) return;
  // Add first one immediately
  addDemoNotification();
  // Then every 8 seconds
  demoInterval = setInterval(addDemoNotification, 8000);
}

function addDemoNotification() {
  if (demoIndex >= DEMO_NOTIFICATIONS.length) {
    clearInterval(demoInterval);
    demoInterval = null;
    showToast('📡 Demo feed complete — all notifications received', 3000);
    return;
  }
  const demo = DEMO_NOTIFICATIONS[demoIndex++];
  addNotification({ ...demo, timestamp: new Date().toISOString() });
  showToast(`🔔 New: ${demo.title}`, 2000);
}

// --- Initialize ---
function initNotifModule() {
  // Restore toggle states
  const autoScanEl = document.getElementById('autoScanToggle');
  const settingsAutoEl = document.getElementById('settingsAutoScan');
  const alertSoundEl = document.getElementById('settingsAlertSound');
  if (autoScanEl) autoScanEl.checked = getAutoScan();
  if (settingsAutoEl) settingsAutoEl.checked = getAutoScan();
  if (alertSoundEl) alertSoundEl.checked = getAlertSound();

  // Update badge on load
  updateNotifBadge();

  // Try Capacitor integration
  initCapacitorNotifListener();
}

window.addEventListener('DOMContentLoaded', initNotifModule);
setTimeout(initNotifModule, 100); // fallback if DOMContentLoaded already fired
