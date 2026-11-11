/* Eternal Cabal Night Shift — dashboard frontend */

const PAGES = [
  { id: 'overview', label: 'Overview', icon: '◈', section: 'Main' },
  { id: 'server', label: 'Server Monitor', icon: '◉', section: 'Main' },
  { id: 'characters', label: 'Character Manager', icon: '♦', section: 'Game Data' },
  { id: 'builds', label: 'Build Planner', icon: '⚒', section: 'Game Data' },
  { id: 'equipment', label: 'Equipment Manager', icon: '⛨', section: 'Game Data' },
  { id: 'farming', label: 'Farming Analytics', icon: '⚔', section: 'Game Data' },
  { id: 'dungeons', label: 'Dungeon Planner', icon: '⌂', section: 'Game Data' },
  { id: 'market', label: 'Market Tracker', icon: '⚖', section: 'Game Data' },
  { id: 'events', label: 'Event Calendar', icon: '✦', section: 'Game Data' },
  { id: 'reports', label: 'Telegram Reports', icon: '✉', section: 'Automation' },
  { id: 'scheduler', label: 'Automation Scheduler', icon: '⏱', section: 'Automation' },
  { id: 'health', label: 'Service Health', icon: '♥', section: 'System' },
  { id: 'backups', label: 'Backup Manager', icon: '▣', section: 'System' },
  { id: 'settings', label: 'Settings', icon: '⚙', section: 'System' },
];

const state = { page: 'overview', health: null, data: {} };

// --- API helper ---
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, kind = '') {
  const wrap = document.getElementById('toast-wrap');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function fmtTs(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('en-PH', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtNum(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-PH', { maximumFractionDigits: 0 });
}

// --- Navigation ---
function renderNav() {
  const nav = document.getElementById('nav');
  let html = '';
  let section = '';
  for (const p of PAGES) {
    if (p.section !== section) {
      section = p.section;
      html += `<div class="nav-section">${esc(section)}</div>`;
    }
    html += `<div class="nav-item ${state.page === p.id ? 'active' : ''}" data-page="${p.id}">
      <span class="nav-icon">${p.icon}</span><span>${esc(p.label)}</span>
    </div>`;
  }
  nav.innerHTML = html;
  nav.querySelectorAll('.nav-item').forEach(el => {
    el.onclick = () => navigate(el.dataset.page);
  });
}

function navigate(page) {
  state.page = page;
  const meta = PAGES.find(p => p.id === page);
  document.getElementById('page-title').textContent = meta ? meta.label : page;
  document.getElementById('page-crumb').textContent = 'Night Shift Companion';
  renderNav();
  loadPage(page);
}

async function loadPage(page) {
  const c = document.getElementById('content');
  c.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const fn = PAGES_RENDER[page] || renderOverview;
    c.innerHTML = await fn();
    if (PAGES_AFTER[page]) await PAGES_AFTER[page]();
  } catch (e) {
    c.innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`;
  }
}

// --- Shared fragments ---
function statusPill(h) {
  const s = h.status || 'unknown';
  const label = s === 'running' ? 'Service running' : s === 'stale' ? 'Heartbeat stale' : 'Service stopped';
  return `<div class="status-pill ${s}"><span class="dot"></span><span>${label}</span></div>`;
}

function metric(label, value, cls = '', sub = '') {
  return `<div class="card"><div class="metric">
    <div class="metric-label">${esc(label)}</div>
    <div class="metric-value ${cls}">${esc(value)}</div>
    ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
  </div></div>`;
}

function emptyRow(text, cols = 4) {
  return `<tr><td colspan="${cols}"><div class="empty" style="border:none;padding:18px">${esc(text)}</div></td></tr>`;
}

// --- Pages ---

async function renderOverview() {
  const h = state.health || await api('/health');
  const snap = await api('/server/current').catch(() => ({}));
  const chars = await api('/characters').catch(() => []);
  const farm = await api('/farming/summary?days=7').catch(() => ({}));
  const jobs = await api('/scheduler/jobs').catch(() => []);
  const backups = await api('/backups').catch(() => []);

  const rates = snap.rates || {};
  const rateStr = Object.entries(rates).map(([k, v]) => `${k} ${v}`).join(' · ') || '—';

  return `
    <div class="grid grid-4">
      ${metric('Server Episode', snap.episode || '?', '', `Max Lvl ${snap.max_level || '?'}`)}
      ${metric('Service', h.status === 'running' ? 'Running' : h.status === 'stale' ? 'Stale' : 'Stopped',
        h.status === 'running' ? 'green' : h.status === 'stale' ? '' : 'red',
        h.uptime_human ? `uptime ${h.uptime_human}` : 'no heartbeat')}
      ${metric('Telegram', h.telegram === 'reachable' ? 'Reachable' : 'Unreachable',
        h.telegram === 'reachable' ? 'green' : 'red')}
      ${metric('Disk Free', `${h.disk_free_gb?.toFixed(1) || '?'} GB`, h.disk_free_gb < 5 ? 'red' : 'blue')}
    </div>

    <div class="grid grid-2 section-gap">
      <div class="card">
        <div class="card-title">Server Rates</div>
        <div style="font-size:13px;line-height:2">${rateStr}</div>
        <div class="small muted" style="margin-top:8px">
          Client v${snap.client_version || '?'} · updated ${snap.client_updated || '?'}<br>
          Last checked ${fmtTs(snap.fetched_at)}
        </div>
      </div>
      <div class="card">
        <div class="card-title">This Week</div>
        <div style="display:flex;flex-direction:column;gap:9px;font-size:13px">
          <div>Sessions recorded: <strong>${farm.session_count ?? 0}</strong></div>
          <div>EXP gained: <strong>${fmtNum(farm.total_exp)}</strong></div>
          <div>EXP/hour: <strong>${fmtNum(farm.exp_per_hour)}</strong></div>
          <div>Profit: <strong>${fmtNum(farm.profit)}</strong> Alz</div>
          <div>Characters: <strong>${chars.length}</strong></div>
        </div>
      </div>
    </div>

    <div class="grid grid-2 section-gap">
      <div class="card">
        <div class="card-title">Scheduled Jobs</div>
        <table>
          <thead><tr><th>Job</th><th>Schedule</th><th>Last run</th><th>Status</th></tr></thead>
          <tbody>
            ${jobs.length ? jobs.map(j => `<tr>
              <td>${esc(j.label)}</td>
              <td class="mono">${esc(j.schedule)}</td>
              <td>${fmtTs(j.last_run)}</td>
              <td><span class="tag ${j.last_status === 'ok' ? 'green' : j.last_status === 'error' ? 'red' : ''}">${esc(j.last_status || 'pending')}</span></td>
            </tr>`).join('') : emptyRow('No jobs registered', 4)}
          </tbody>
        </table>
      </div>
      <div class="card">
        <div class="card-title">Recent Backups</div>
        <table>
          <thead><tr><th>When</th><th>Size</th><th>Verified</th></tr></thead>
          <tbody>
            ${backups.length ? backups.slice(0, 5).map(b => `<tr>
              <td>${fmtTs(b.created_at)}</td>
              <td>${(b.size_bytes / 1024).toFixed(0)} KB</td>
              <td><span class="tag ${b.verified ? 'green' : 'red'}">${b.verified ? 'yes' : 'no'}</span></td>
            </tr>`).join('') : emptyRow('No backups yet', 3)}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card section-gap">
      <div class="card-title">Recent Activity</div>
      <pre class="report" style="max-height:200px">${esc((await api('/reports/logs?limit=12').catch(() => []))
        .map(l => `[${l.level}] ${l.component}: ${l.message}`).join('\n') || 'No activity recorded')}</pre>
    </div>
  `;
}

async function renderServer() {
  const snap = await api('/server/current').catch(() => ({}));
  const hist = await api('/server/history?limit=15').catch(() => []);
  const ann = await api('/server/announcements').catch(() => []);
  const ev = await api('/server/events').catch(() => []);
  const rates = snap.rates || {};

  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="refreshServer()">Refresh Now</button>
      <div class="spacer"></div>
      <span class="small muted">Polls every 30 min · cached 30 min</span>
    </div>

    <div class="grid grid-4">
      ${metric('Episode', snap.episode || '?', '', `Region ${snap.region || 'Asean'}`)}
      ${metric('Max Level', snap.max_level || '?', 'blue')}
      ${metric('Client Version', 'v' + (snap.client_version || '?'), 'green', snap.client_size || '')}
      ${metric('Client Updated', snap.client_updated || '?', '', 'Last patch')}
    </div>

    <div class="card section-gap">
      <div class="card-title">Server Rates</div>
      <div class="grid grid-4">
        ${Object.entries(rates).length
          ? Object.entries(rates).map(([k, v]) => `<div class="metric">
              <div class="metric-label">${esc(k)}</div>
              <div class="metric-value blue">${esc(v)}</div>
            </div>`).join('')
          : '<div class="empty" style="grid-column:1/-1">No rate data recorded</div>'}
      </div>
    </div>

    <div class="grid grid-2 section-gap">
      <div class="card">
        <div class="card-title">Announcements</div>
        <table>
          <thead><tr><th>When</th><th>Title</th><th>Source</th></tr></thead>
          <tbody>
            ${ann.length ? ann.map(a => `<tr>
              <td>${fmtTs(a.seen_at)}</td><td>${esc(a.title || '—')}</td><td>${esc(a.source || '')}</td>
            </tr>`).join('') : emptyRow('No announcements detected', 3)}
          </tbody>
        </table>
      </div>
      <div class="card">
        <div class="card-title">Events</div>
        <table>
          <thead><tr><th>Event</th><th>Starts</th><th>Ends</th></tr></thead>
          <tbody>
            ${ev.length ? ev.map(e => `<tr>
              <td>${esc(e.title || '—')}</td><td>${esc(e.starts_at || '—')}</td><td>${esc(e.ends_at || '—')}</td>
            </tr>`).join('') : emptyRow('No events recorded', 3)}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card section-gap">
      <div class="card-title">Snapshot History</div>
      <table>
        <thead><tr><th>When</th><th>Episode</th><th>Rates</th><th>Client</th></tr></thead>
        <tbody>
          ${hist.length ? hist.map(s => `<tr>
            <td>${fmtTs(s.fetched_at)}</td>
            <td>${esc(s.episode || '—')}</td>
            <td class="small">${esc(Object.entries(s.rates || {}).map(([k, v]) => `${k} ${v}`).join(', '))}</td>
            <td>v${esc(s.client_version || '?')}</td>
          </tr>`).join('') : emptyRow('No snapshots recorded', 4)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderCharacters() {
  const chars = await api('/characters').catch(() => []);
  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="showAddCharacter()">Add Character</button>
      <div class="spacer"></div>
      <span class="small muted">${chars.length} character(s)</span>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>Name</th><th>Class</th><th>Level</th><th>Objectives</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          ${chars.length ? chars.map(c => `<tr>
            <td><strong>${esc(c.name)}</strong></td>
            <td>${esc(c.class || '—')}</td>
            <td>${esc(c.level ?? '—')}</td>
            <td>${Array.isArray(c.objectives) ? c.objectives.length : 0}</td>
            <td>${fmtTs(c.updated_at)}</td>
            <td style="white-space:nowrap">
              <button class="btn btn-sm" onclick="editCharacter(${c.id})">Edit</button>
              <button class="btn btn-sm btn-danger" onclick="deleteCharacter(${c.id})">Delete</button>
            </td>
          </tr>`).join('') : emptyRow('No characters yet. Add your first character.', 6)}
        </tbody>
      </table>
    </div>
    <div id="char-modal"></div>
  `;
}

async function renderBuilds() {
  const chars = await api('/characters').catch(() => []);
  return `
    <div class="toolbar"><span class="small muted">Build configurations are stored per character.</span></div>
    <div class="grid grid-2">
      ${chars.length ? chars.map(c => `
        <div class="card">
          <div class="card-title">${esc(c.name)} — Build</div>
          <pre class="report" style="max-height:220px">${esc(JSON.stringify(c.build || {}, null, 2))}</pre>
          <div class="small muted" style="margin-top:8px">
            Skills: ${(c.skills || []).length ? c.skills.map(s => esc(s)).join(', ') : 'none recorded'}
          </div>
        </div>`).join('') : '<div class="empty" style="grid-column:1/-1">No characters recorded</div>'}
    </div>
  `;
}

async function renderEquipment() {
  const chars = await api('/characters').catch(() => []);
  return `
    <div class="toolbar"><span class="small muted">Equipment is stored per character.</span></div>
    <div class="grid grid-2">
      ${chars.length ? chars.map(c => `
        <div class="card">
          <div class="card-title">${esc(c.name)} — Equipment</div>
          ${(c.equipment && c.equipment.length) ? `<table>
            <tbody>${c.equipment.map(e => `<tr><td>${esc(typeof e === 'string' ? e : (e.name || JSON.stringify(e)))}</td></tr>`).join('')}</tbody>
          </table>` : '<div class="empty">No equipment recorded</div>'}
          <div class="small muted" style="margin-top:10px">Stats</div>
          <pre class="report" style="max-height:140px;margin-top:6px">${esc(JSON.stringify(c.stats || {}, null, 2))}</pre>
        </div>`).join('') : '<div class="empty" style="grid-column:1/-1">No characters recorded</div>'}
    </div>
  `;
}

async function renderFarming() {
  const s = await api('/farming/summary?days=7').catch(() => ({}));
  const sessions = await api('/farming/sessions?limit=25').catch(() => []);
  const chars = await api('/characters').catch(() => []);

  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="showAddSession()">Record Session</button>
      <div class="spacer"></div>
      <select id="farm-days" style="width:150px" onchange="loadPage('farming')">
        <option value="1">Last 24h</option>
        <option value="7" selected>Last 7 days</option>
        <option value="30">Last 30 days</option>
      </select>
    </div>

    <div class="grid grid-4">
      ${metric('Sessions', s.session_count ?? 0)}
      ${metric('Hours', (s.total_hours ?? 0).toFixed(2), 'blue')}
      ${metric('EXP / Hour', fmtNum(s.exp_per_hour), 'green')}
      ${metric('Profit', fmtNum(s.profit), (s.profit ?? 0) >= 0 ? 'green' : 'red', 'Alz')}
    </div>

    <div class="card section-gap">
      <div class="card-title">By Location</div>
      <table>
        <thead><tr><th>Location</th><th>Sessions</th><th>Hours</th><th>EXP</th><th>EXP/h</th><th>Profit</th></tr></thead>
        <tbody>
          ${Object.entries(s.by_location || {}).length
            ? Object.entries(s.by_location).map(([loc, a]) => `<tr>
                <td>${esc(loc)}</td><td>${a.sessions}</td>
                <td>${(a.minutes / 60).toFixed(2)}</td>
                <td>${fmtNum(a.exp)}</td><td>${fmtNum(a.exp_per_hour)}</td>
                <td>${fmtNum(a.profit)}</td>
              </tr>`).join('')
            : emptyRow('No farming sessions recorded', 6)}
        </tbody>
      </table>
    </div>

    <div class="card section-gap">
      <div class="card-title">Recent Sessions</div>
      <table>
        <thead><tr><th>When</th><th>Location</th><th>Dungeon</th><th>Duration</th><th>EXP</th><th>Profit</th></tr></thead>
        <tbody>
          ${sessions.length ? sessions.map(x => `<tr>
            <td>${fmtTs(x.started_at)}</td>
            <td>${esc(x.location || '—')}</td>
            <td>${esc(x.dungeon || '—')}</td>
            <td>${(x.duration_min ?? 0).toFixed(0)} min</td>
            <td>${fmtNum(x.exp_gained)}</td>
            <td>${fmtNum((x.revenue || 0) - (x.expenses || 0))}</td>
          </tr>`).join('') : emptyRow('No sessions recorded', 6)}
        </tbody>
      </table>
    </div>
    <div id="farm-modal"></div>
  `;
}

async function renderDungeons() {
  const s = await api('/farming/summary?days=30').catch(() => ({}));
  const byLoc = s.by_location || {};
  const rows = Object.entries(byLoc).sort((a, b) => (b[1].exp_per_hour || 0) - (a[1].exp_per_hour || 0));
  return `
    <div class="toolbar"><span class="small muted">Derived from recorded sessions. Best EXP/h first.</span></div>
    <div class="card">
      <div class="card-title">Location Efficiency — 30 days</div>
      <table>
        <thead><tr><th>Rank</th><th>Location</th><th>Runs</th><th>EXP/h</th><th>Total EXP</th><th>Profit</th></tr></thead>
        <tbody>
          ${rows.length ? rows.map(([loc, a], i) => `<tr>
            <td><span class="tag ${i === 0 ? 'gold' : i < 3 ? 'blue' : ''}">#${i + 1}</span></td>
            <td><strong>${esc(loc)}</strong></td>
            <td>${a.sessions}</td>
            <td>${fmtNum(a.exp_per_hour)}</td>
            <td>${fmtNum(a.exp)}</td>
            <td>${fmtNum(a.profit)}</td>
          </tr>`).join('') : emptyRow('No dungeon data recorded yet', 6)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderMarket() {
  const rep = await api('/market/report').catch(() => ({}));
  const items = await api('/market/items?limit=60').catch(() => []);

  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="showAddItem()">Record Price</button>
      <div class="spacer"></div>
      <input id="market-search" placeholder="Search item…" style="width:200px" onkeyup="searchMarket(this.value)">
    </div>

    <div class="grid grid-4">
      ${metric('Tracked Items', rep.tracked_items ?? 0)}
      ${metric('Price Changes', (rep.changes || []).length, 'blue')}
    </div>

    <div class="card section-gap">
      <div class="card-title">Price Movements</div>
      <table>
        <thead><tr><th>Item</th><th>Previous</th><th>Current</th><th>Change</th></tr></thead>
        <tbody>
          ${(rep.changes || []).length ? rep.changes.map(c => `<tr>
            <td>${esc(c.name)}</td>
            <td>${fmtNum(c.previous)}</td>
            <td>${fmtNum(c.current)}</td>
            <td><span class="tag ${c.delta >= 0 ? 'green' : 'red'}">${c.delta >= 0 ? '+' : ''}${c.percent.toFixed(1)}%</span></td>
          </tr>`).join('') : emptyRow('Record at least two prices for an item to see movement', 4)}
        </tbody>
      </table>
    </div>

    <div class="card section-gap">
      <div class="card-title">Recent Prices</div>
      <table>
        <thead><tr><th>Item</th><th>Price</th><th>Currency</th><th>Source</th><th>Recorded</th></tr></thead>
        <tbody>
          ${items.length ? items.map(i => `<tr>
            <td>${esc(i.name)}</td><td>${fmtNum(i.price)}</td>
            <td>${esc(i.currency || 'Alz')}</td><td>${esc(i.source || '')}</td>
            <td>${fmtTs(i.recorded_at)}</td>
          </tr>`).join('') : emptyRow('No market data recorded', 5)}
        </tbody>
      </table>
    </div>
    <div id="market-modal"></div>
  `;
}

async function renderEvents() {
  const ev = await api('/server/events').catch(() => []);
  const objs = await api('/objectives').catch(() => []);
  return `
    <div class="grid grid-2">
      <div class="card">
        <div class="card-title">Server Events</div>
        <table>
          <thead><tr><th>Event</th><th>Starts</th><th>Ends</th></tr></thead>
          <tbody>
            ${ev.length ? ev.map(e => `<tr>
              <td>${esc(e.title || '—')}</td><td>${esc(e.starts_at || '—')}</td><td>${esc(e.ends_at || '—')}</td>
            </tr>`).join('') : emptyRow('No events recorded', 3)}
          </tbody>
        </table>
      </div>
      <div class="card">
        <div class="card-title">Today's Objectives</div>
        <table>
          <thead><tr><th>Character</th><th>Objective</th><th>Done</th></tr></thead>
          <tbody>
            ${objs.length ? objs.map(o => `<tr>
              <td>${esc(o.character_name || 'General')}</td>
              <td>${esc(o.title || '')}</td>
              <td><span class="tag ${o.done ? 'green' : ''}">${o.done ? 'yes' : 'no'}</span></td>
            </tr>`).join('') : emptyRow('No objectives for today', 3)}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

async function renderReports() {
  const text = (await api('/reports/daily').catch(() => ({ text: 'unavailable' }))).text || '';
  const tel = await api('/telegram/status').catch(() => ({}));
  const logs = await api('/reports/logs?limit=40').catch(() => []);

  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="sendReport()">Send Report Now</button>
      <button class="btn" onclick="loadPage('reports')">Refresh Preview</button>
      <div class="spacer"></div>
      <span class="tag ${tel.reachable ? 'green' : 'red'}">Telegram ${tel.reachable ? 'reachable' : 'unreachable'}</span>
    </div>

    <div class="card">
      <div class="card-title">Daily Report Preview</div>
      <pre class="report">${esc(text)}</pre>
    </div>

    <div class="card section-gap">
      <div class="card-title">Service Log</div>
      <table>
        <thead><tr><th>When</th><th>Level</th><th>Component</th><th>Message</th></tr></thead>
        <tbody>
          ${logs.length ? logs.map(l => `<tr>
            <td style="white-space:nowrap">${fmtTs(l.ts)}</td>
            <td><span class="tag ${l.level === 'ERROR' ? 'red' : l.level === 'WARNING' ? 'gold' : ''}">${esc(l.level)}</span></td>
            <td>${esc(l.component)}</td><td>${esc(l.message)}</td>
          </tr>`).join('') : emptyRow('No log entries', 4)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderScheduler() {
  const jobs = await api('/scheduler/jobs').catch(() => []);
  return `
    <div class="toolbar"><span class="small muted">Jobs run in the background service. Forcing a run does not change the schedule.</span></div>
    <div class="card">
      <table>
        <thead><tr><th>Job</th><th>Schedule</th><th>Enabled</th><th>Last run</th><th>Next run</th><th>Status</th><th></th></tr></thead>
        <tbody>
          ${jobs.length ? jobs.map(j => `<tr>
            <td><strong>${esc(j.label)}</strong></td>
            <td class="mono">${esc(j.schedule)}</td>
            <td><span class="tag ${j.enabled ? 'green' : ''}">${j.enabled ? 'on' : 'off'}</span></td>
            <td>${fmtTs(j.last_run)}</td>
            <td>${fmtTs(j.next_run)}</td>
            <td><span class="tag ${j.last_status === 'ok' ? 'green' : j.last_status === 'error' ? 'red' : ''}">${esc(j.last_status || 'pending')}</span></td>
            <td style="white-space:nowrap">
              <button class="btn btn-sm" onclick="runJob('${esc(j.job_key)}')">Run now</button>
              <button class="btn btn-sm" onclick="toggleJob('${esc(j.job_key)}', ${!j.enabled})">${j.enabled ? 'Disable' : 'Enable'}</button>
            </td>
          </tr>`).join('') : emptyRow('No jobs registered', 7)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderHealth() {
  const h = await api('/health').catch(() => ({}));
  const st = await api('/service/status').catch(() => ({}));
  const logs = await api('/reports/logs?limit=20&level=ERROR').catch(() => []);

  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="controlService('start')">Start Service</button>
      <button class="btn" onclick="controlService('restart')">Restart Service</button>
      <button class="btn btn-danger" onclick="controlService('stop')">Stop Service</button>
    </div>

    <div class="grid grid-4">
      ${metric('Status', h.status === 'running' ? 'Running' : h.status === 'stale' ? 'Stale' : 'Stopped',
        h.status === 'running' ? 'green' : 'red')}
      ${metric('Uptime', h.uptime_human || '—', 'blue')}
      ${metric('Heartbeat Age', st.age_seconds ? `${Math.round(st.age_seconds)}s` : '—',
        st.age_seconds < 300 ? 'green' : 'red')}
      ${metric('PID', h.pid || st.pid || '—')}
    </div>

    <div class="grid grid-3 section-gap">
      ${metric('Database', h.database === 'ok' ? 'OK' : 'Error',
        h.database === 'ok' ? 'green' : 'red')}
      ${metric('Telegram', h.telegram === 'reachable' ? 'Reachable' : 'Unreachable',
        h.telegram === 'reachable' ? 'green' : 'red')}
      ${metric('Disk Free', `${h.disk_free_gb?.toFixed(1) || '?'} GB`,
        h.disk_free_gb < 5 ? 'red' : 'green')}
    </div>

    <div class="card section-gap">
      <div class="card-title">Recent Errors</div>
      <table>
        <thead><tr><th>When</th><th>Component</th><th>Message</th></tr></thead>
        <tbody>
          ${logs.length ? logs.map(l => `<tr>
            <td>${fmtTs(l.ts)}</td><td>${esc(l.component)}</td><td>${esc(l.message)}</td>
          </tr>`).join('') : emptyRow('No errors recorded', 3)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderBackups() {
  const bs = await api('/backups').catch(() => []);
  return `
    <div class="toolbar">
      <button class="btn btn-primary" onclick="runBackup()">Run Backup Now</button>
      <div class="spacer"></div>
      <span class="small muted">Retention: 7 days</span>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>When</th><th>Kind</th><th>Size</th><th>Checksum</th><th>Verified</th><th></th></tr></thead>
        <tbody>
          ${bs.length ? bs.map(b => `<tr>
            <td>${fmtTs(b.created_at)}</td>
            <td>${esc(b.kind || 'daily')}</td>
            <td>${(b.size_bytes / 1024).toFixed(0)} KB</td>
            <td class="mono small">${esc((b.checksum || '').slice(0, 12))}…</td>
            <td><span class="tag ${b.verified ? 'green' : 'red'}">${b.verified ? 'yes' : 'no'}</span></td>
            <td style="white-space:nowrap">
              <button class="btn btn-sm" onclick="verifyBackup(${b.id})">Verify</button>
              <button class="btn btn-sm btn-danger" onclick="restoreBackup(${b.id})">Restore</button>
            </td>
          </tr>`).join('') : emptyRow('No backups yet', 6)}
        </tbody>
      </table>
    </div>
  `;
}

async function renderSettings() {
  const s = await api('/settings').catch(() => ({}));
  return `
    <div class="card" style="max-width:560px">
      <div class="card-title">Report & Scheduling</div>
      <div class="row">
        <div class="field"><label>Daily report hour (24h)</label>
          <input type="number" id="s-hour" min="0" max="23" value="${s.daily_report_hour ?? 6}"></div>
        <div class="field"><label>Minute</label>
          <input type="number" id="s-min" min="0" max="59" value="${s.daily_report_minute ?? 0}"></div>
      </div>
      <div class="field"><label>Server poll interval (minutes)</label>
        <input type="number" id="s-poll" min="5" max="720" value="${s.server_poll_interval_min ?? 30}"></div>
      <div class="field"><label>Cache TTL (seconds)</label>
        <input type="number" id="s-cache" min="60" max="86400" value="${s.cache_ttl_seconds ?? 1800}"></div>
      <div class="field"><label>Backup retention (days)</label>
        <input type="number" id="s-retention" min="1" max="90" value="${s.backup_retention_days ?? 7}"></div>
      <div class="field"><label>Dashboard port</label>
        <input type="number" id="s-port" min="1024" max="65535" value="${s.dashboard_port ?? 8770}"></div>
      <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
    </div>

    <div class="card section-gap" style="max-width:560px">
      <div class="card-title">Automation Policy</div>
      <div class="small muted" style="line-height:1.7">
        In-game automation is <strong style="color:var(--red)">disabled by design</strong>.
        This companion monitors public information and manages records only.<br><br>
        Disabled: auto-combat, auto-farming, auto-movement, auto-dungeon,
        input simulation, packet manipulation, memory modification,
        DLL injection, client modification, anti-cheat bypass.
      </div>
    </div>
  `;
}

const PAGES_RENDER = {
  overview: renderOverview,
  server: renderServer,
  characters: renderCharacters,
  builds: renderBuilds,
  equipment: renderEquipment,
  farming: renderFarming,
  dungeons: renderDungeons,
  market: renderMarket,
  events: renderEvents,
  reports: renderReports,
  scheduler: renderScheduler,
  health: renderHealth,
  backups: renderBackups,
  settings: renderSettings,
};

const PAGES_AFTER = {};

// --- Actions ---

async function refreshServer() {
  toast('Refreshing server info…');
  try {
    const r = await api('/server/refresh', { method: 'POST' });
    const changes = r.changes || [];
    toast(changes.length ? `Changes: ${changes.join(', ')}` : 'No changes detected', 'ok');
    loadPage('server');
  } catch (e) { toast(e.message, 'err'); }
}

async function sendReport() {
  toast('Sending report…');
  try {
    const r = await api('/reports/daily/send', { method: 'POST' });
    toast(r.ok ? 'Report sent' : 'Report failed', r.ok ? 'ok' : 'err');
  } catch (e) { toast(e.message, 'err'); }
}

async function controlService(action) {
  if (action === 'stop' && !confirm('Stop the background service?')) return;
  if (action === 'restart' && !confirm('Restart the background service?')) return;
  try {
    await api(`/service/${action}`, { method: 'POST' });
    toast(`Service ${action} requested`, 'ok');
    setTimeout(() => loadPage('health'), 1500);
  } catch (e) { toast(e.message, 'err'); }
}

async function runJob(key) {
  try {
    const r = await api(`/scheduler/${key}/run`, { method: 'POST' });
    toast(r.ok ? `${key} started` : `${key} not found`, r.ok ? 'ok' : 'err');
    setTimeout(() => loadPage('scheduler'), 1200);
  } catch (e) { toast(e.message, 'err'); }
}

async function toggleJob(key, enabled) {
  try {
    await api(`/scheduler/${key}/toggle?enabled=${enabled}`, { method: 'POST' });
    toast(`${key} ${enabled ? 'enabled' : 'disabled'}`, 'ok');
    loadPage('scheduler');
  } catch (e) { toast(e.message, 'err'); }
}

async function runBackup() {
  toast('Running backup…');
  try {
    const r = await api('/backups/run', { method: 'POST' });
    toast(r.verified ? 'Backup verified' : 'Backup failed verification', r.verified ? 'ok' : 'err');
    loadPage('backups');
  } catch (e) { toast(e.message, 'err'); }
}

async function verifyBackup(id) {
  try {
    const r = await api(`/backups/${id}/verify`, { method: 'POST' });
    toast(r.ok ? 'Backup verified' : 'Checksum mismatch', r.ok ? 'ok' : 'err');
    loadPage('backups');
  } catch (e) { toast(e.message, 'err'); }
}

async function restoreBackup(id) {
  if (!confirm('Restore from this backup? Current data will be safety-backed-up first.')) return;
  try {
    const r = await api(`/backups/${id}/restore`, { method: 'POST' });
    toast(r.ok ? 'Restored' : 'Restore failed', r.ok ? 'ok' : 'err');
  } catch (e) { toast(e.message, 'err'); }
}

async function saveSettings() {
  const payload = {
    daily_report_hour: +document.getElementById('s-hour').value,
    daily_report_minute: +document.getElementById('s-min').value,
    server_poll_interval_min: +document.getElementById('s-poll').value,
    cache_ttl_seconds: +document.getElementById('s-cache').value,
    backup_retention_days: +document.getElementById('s-retention').value,
    dashboard_port: +document.getElementById('s-port').value,
  };
  try {
    await api('/settings', { method: 'POST', body: JSON.stringify(payload) });
    toast('Settings saved', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

async function deleteCharacter(id) {
  if (!confirm('Delete this character? Farming history is kept.')) return;
  try {
    await api(`/characters/${id}`, { method: 'DELETE' });
    toast('Character deleted', 'ok');
    loadPage('characters');
  } catch (e) { toast(e.message, 'err'); }
}

async function editCharacter(id) {
  const c = await api(`/characters/${id}`);
  const ch = c.character || c;
  showCharacterModal(ch);
}

function showAddCharacter() { showCharacterModal(null); }

function showCharacterModal(c) {
  const isEdit = !!c;
  const m = document.getElementById('char-modal');
  m.innerHTML = `
    <div class="card section-gap">
      <div class="card-title">${isEdit ? 'Edit' : 'Add'} Character</div>
      <div class="row">
        <div class="field"><label>Name</label><input id="c-name" value="${esc(c?.name || '')}"></div>
        <div class="field"><label>Class</label><input id="c-class" value="${esc(c?.class || '')}"></div>
        <div class="field" style="max-width:90px"><label>Level</label><input id="c-level" type="number" value="${c?.level ?? 1}"></div>
      </div>
      <div class="field"><label>Objectives (one per line)</label>
        <textarea id="c-objectives" rows="3">${esc((c?.objectives || []).join('\n'))}</textarea></div>
      <div class="field"><label>Equipment (one per line)</label>
        <textarea id="c-equipment" rows="3">${esc((c?.equipment || []).join('\n'))}</textarea></div>
      <div class="field"><label>Skills (comma separated)</label>
        <input id="c-skills" value="${esc((c?.skills || []).join(', '))}"></div>
      <div class="field"><label>Stats (JSON)</label>
        <textarea id="c-stats" rows="3">${esc(JSON.stringify(c?.stats || {}, null, 2))}</textarea></div>
      <div class="field"><label>Build (JSON)</label>
        <textarea id="c-build" rows="3">${esc(JSON.stringify(c?.build || {}, null, 2))}</textarea></div>
      <button class="btn btn-primary" onclick="saveCharacter(${isEdit ? c.id : 'null'})">Save</button>
      <button class="btn" onclick="document.getElementById('char-modal').innerHTML=''">Cancel</button>
    </div>`;
}

async function saveCharacter(id) {
  const parseList = sel => document.getElementById(sel).value.split('\n').map(s => s.trim()).filter(Boolean);
  const parseCsv = sel => document.getElementById(sel).value.split(',').map(s => s.trim()).filter(Boolean);
  const parseJson = sel => { try { return JSON.parse(document.getElementById(sel).value || '{}'); } catch (e) { throw new Error(`Invalid JSON in ${sel}`); } };
  const payload = {
    name: document.getElementById('c-name').value,
    class_name: document.getElementById('c-class').value,
    level: +document.getElementById('c-level').value,
    objectives: parseList('c-objectives'),
    equipment: parseList('c-equipment'),
    skills: parseCsv('c-skills'),
    stats: parseJson('c-stats'),
    build: parseJson('c-build'),
  };
  try {
    if (id) await api(`/characters/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
    else await api('/characters', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('char-modal').innerHTML = '';
    toast('Character saved', 'ok');
    loadPage('characters');
  } catch (e) { toast(e.message, 'err'); }
}

function showAddSession() { showSessionModal(); }

function showSessionModal() {
  const m = document.getElementById('farm-modal');
  const now = Date.now() / 1000;
  m.innerHTML = `
    <div class="card section-gap">
      <div class="card-title">Record Farming Session</div>
      <div class="row">
        <div class="field"><label>Character</label><select id="f-char"><option value="">—</option></select></div>
        <div class="field"><label>Location</label><input id="f-loc" placeholder="e.g. Ice Witch Town"></div>
        <div class="field"><label>Dungeon</label><input id="f-dung" placeholder="e.g. NSD"></div>
      </div>
      <div class="row">
        <div class="field"><label>Start (unix seconds)</label><input id="f-start" type="number" value="${now - 3600}"></div>
        <div class="field"><label>End (unix seconds)</label><input id="f-end" type="number" value="${now}"></div>
        <div class="field"><label>EXP gained</label><input id="f-exp" type="number" value="0"></div>
      </div>
      <div class="row">
        <div class="field"><label>Expenses (Alz)</label><input id="f-cost" type="number" value="0"></div>
        <div class="field"><label>Revenue (Alz)</label><input id="f-rev" type="number" value="0"></div>
      </div>
      <div class="field"><label>Items (one per line)</label><textarea id="f-items" rows="2"></textarea></div>
      <button class="btn btn-primary" onclick="saveSession()">Save Session</button>
      <button class="btn" onclick="document.getElementById('farm-modal').innerHTML=''">Cancel</button>
    </div>`;
  api('/characters').then(chars => {
    const sel = document.getElementById('f-char');
    if (!sel) return;
    sel.innerHTML = '<option value="">—</option>' + chars.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
  }).catch(() => {});
}

async function saveSession() {
  const cid = document.getElementById('f-char').value;
  const items = document.getElementById('f-items').value.split('\n').map(s => s.trim()).filter(Boolean);
  const payload = {
    character_id: cid ? +cid : null,
    location: document.getElementById('f-loc').value,
    dungeon: document.getElementById('f-dung').value,
    started_at: +document.getElementById('f-start').value,
    ended_at: +document.getElementById('f-end').value,
    exp_gained: +document.getElementById('f-exp').value,
    expenses: +document.getElementById('f-cost').value,
    revenue: +document.getElementById('f-rev').value,
    items,
  };
  try {
    await api('/farming/sessions', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('farm-modal').innerHTML = '';
    toast('Session recorded', 'ok');
    loadPage('farming');
  } catch (e) { toast(e.message, 'err'); }
}

function showAddItem() {
  const m = document.getElementById('market-modal');
  m.innerHTML = `
    <div class="card section-gap">
      <div class="card-title">Record Market Price</div>
      <div class="row">
        <div class="field"><label>Item name</label><input id="m-name"></div>
        <div class="field"><label>Price</label><input id="m-price" type="number" value="0"></div>
        <div class="field"><label>Currency</label><input id="m-cur" value="Alz"></div>
      </div>
      <div class="field"><label>Category</label><input id="m-cat" placeholder="e.g. Crafting material"></div>
      <button class="btn btn-primary" onclick="saveItem()">Save Price</button>
      <button class="btn" onclick="document.getElementById('market-modal').innerHTML=''">Cancel</button>
    </div>`;
}

async function saveItem() {
  const payload = {
    name: document.getElementById('m-name').value,
    price: +document.getElementById('m-price').value,
    currency: document.getElementById('m-cur').value,
    category: document.getElementById('m-cat').value,
  };
  try {
    await api('/market/items', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('market-modal').innerHTML = '';
    toast('Price recorded', 'ok');
    loadPage('market');
  } catch (e) { toast(e.message, 'err'); }
}

async function searchMarket(q) {
  if (q.length < 2) return;
  try {
    const items = await api(`/market/items?name=${encodeURIComponent(q)}&limit=20`);
    toast(`${items.length} match(es)`, 'ok');
  } catch (e) {}
}

// --- Top bar actions ---
document.getElementById('btn-test-telegram').onclick = async () => {
  toast('Sending test message…');
  try {
    const r = await api('/telegram/test', { method: 'POST' });
    toast(r.ok ? 'Test message sent' : 'Failed to send', r.ok ? 'ok' : 'err');
  } catch (e) { toast(e.message, 'err'); }
};

document.getElementById('btn-send-report').onclick = sendReport;

// --- Clock ---
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-PH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}, 1000);

// --- Health polling ---
async function pollHealth() {
  try {
    const h = await api('/health');
    state.health = h;
    const pill = document.getElementById('service-pill');
    const s = h.status || 'unknown';
    pill.className = `status-pill ${s}`;
    pill.querySelector('span:last-child').textContent =
      s === 'running' ? 'Service running' : s === 'stale' ? 'Heartbeat stale' : 'Service stopped';
    document.getElementById('sidebar-meta').innerHTML =
      `EP${h.episode || '?'} · v${h.client_version || '?'}<br>${h.uptime_human || ''}`;
  } catch (e) {
    document.getElementById('service-pill').className = 'status-pill stopped';
  }
}

// --- Boot ---
renderNav();
navigate('overview');
pollHealth();
setInterval(pollHealth, 30000);
