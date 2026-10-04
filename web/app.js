// Career OS — front end (plain JS, no build step)
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
};
const post = (p, b = {}) => api(p, { method: 'POST', body: b });
const put = (p, b = {}) => api(p, { method: 'PUT', body: b });
const patch = (p, b = {}) => api(p, { method: 'PATCH', body: b });
const toast = (m, ms = 2800) => { const t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('on'), ms); };
const modal = html => { $('#modalBody').innerHTML = html; $('#modal').classList.add('on'); };
const closeModal = () => $('#modal').classList.remove('on');
$('#modalX').onclick = closeModal;
$('#modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
const d10 = s => s ? String(s).slice(0, 10) : '';
const daysTo = d => d ? Math.round((new Date(d.slice(0, 10)) - new Date(new Date().toISOString().slice(0, 10))) / 864e5) : null;
const scoreCls = s => s >= 70 ? 'hi' : s >= 50 ? 'mid' : '';
const debounce = (fn, ms = 300) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };
const store = { get(k, d) { try { const v = localStorage.getItem('careeros.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem('careeros.' + k, JSON.stringify(v)); } catch (e) {} } };
const ICON = {
  folder: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  plus: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  cap: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 7l10-4 10 4-10 4z"/><path d="M6 9v5c0 2 3 4 6 4s6-2 6-4V9"/></svg>',
  ext: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/></svg>',
};
const COUNTRY = { UK: 'United Kingdom', IN: 'India', US: 'United States', REMOTE: 'Remote', IE: 'Ireland', DE: 'Germany', NL: 'Netherlands', CH: 'Switzerland', FR: 'France', IT: 'Italy', ES: 'Spain', PL: 'Poland', SE: 'Sweden', DK: 'Denmark', PT: 'Portugal', AT: 'Austria', BE: 'Belgium', SG: 'Singapore', HK: 'Hong Kong', AE: 'UAE', AU: 'Australia', CA: 'Canada', JP: 'Japan', CN: 'China', IL: 'Israel', KR: 'Korea', TW: 'Taiwan', CZ: 'Czechia', BG: 'Bulgaria', RO: 'Romania', NO: 'Norway', FI: 'Finland', BR: 'Brazil', EE: 'Estonia', OTHER: 'Other' };
const KINDS = { job: 'Jobs', internship: 'Internships', graduate: 'Graduate', apprenticeship: 'Apprenticeships', fellowship: 'Fellowships', scholarship: 'Scholarships', parttime: 'Part-time', competition: 'Competitions' };
const TRACKS = { swe: 'Software', ml: 'ML / AI', research: 'Research', quant: 'Quant', data: 'Data', systems: 'Systems', salesforce: 'Salesforce', slack: 'Slack' };

let ST = {}, SET = {}, VIEW = 'apply';
const theme = store.get('theme', 'system');
if (theme !== 'system') document.documentElement.dataset.theme = theme;

// ================= shell =================
function show(view) {
  VIEW = view;
  $$('.rail [data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === view));
  $$('.view').forEach(v => v.classList.toggle('on', v.id === 'v-' + view));
  if (location.hash.slice(1) !== view) history.replaceState(null, '', '#' + view);
  ({ apply: Apply.load, track: Track.load, learn: Learn.load, agents: Agents.load, settings: Settings.load, sources: Sources.load, usage: Usage.load, me: Me.load, extra: Extra.load })[view]();
}
$$('.rail [data-view]').forEach(b => b.onclick = () => show(b.dataset.view));
$('#me').onclick = () => ($('#me').classList.contains('bad') && !HEALTH.server) ? AIFix.open() : show('me');
$('#bell').onclick = async () => {
  const rows = await api('/api/notifications');
  modal(`<h2 style="font-size:18px;margin-bottom:12px">Notifications</h2><div class="card list">${rows.map(n => `<div class="item"><b>${esc(n.title)}</b><div class="muted small">${esc(n.body)} · ${esc(d10(n.created_at))}</div></div>`).join('') || '<div class="empty">Nothing yet.</div>'}</div>`);
  post('/api/notifications/seen').then(status);
};
function authBar() {
  const el = $('#authbar'), b = ST.brain || {}, err = b.auth_error;
  const hid = store.get('authHide', {});
  if (!err || (hid.err === err && Date.now() < (hid.until || 0))) { el.classList.add('hidden'); return; }
  if (!el.classList.contains('hidden') && el.dataset.err === err) return;
  el.dataset.err = err; el.classList.remove('hidden');
  el.innerHTML = `<div class="grow"><b>${esc(b.name || 'Your AI')} isn’t signed in — its sign-in has expired</b><div class="m">So it can’t read application pages, write answers or run the finders. ${AIPick.hint(b.provider)} Then press Test.</div><div class="m" id="abOut"></div></div>
    <button class="btn" id="abLogin">Sign in</button><button class="btn ghost" id="abTest">Test</button><button class="btn ghost" id="abX" aria-label="Hide">Hide</button>`;
  $('#abLogin').onclick = async () => { const r = await post('/api/claude/login'); $('#abOut').textContent = r.manual || 'A black window opened — follow the line at its top, then press Test here.'; };
  $('#abTest').onclick = async () => { $('#abOut').textContent = 'Testing…'; try { const r = await post('/api/claude/test'); if (r.ok) { $('#abOut').textContent = 'Connected ✓'; setTimeout(() => el.classList.add('hidden'), 1500); ST.brain.auth_error = ''; health(); } else $('#abOut').textContent = 'Unexpected reply: ' + r.reply; } catch (e) { $('#abOut').textContent = e.message; } };
  $('#abX').onclick = () => { store.set('authHide', { err, until: Date.now() + 3600e3 }); el.classList.add('hidden'); toast('Hidden for an hour — click your initials (bottom left) to sign in any time', 4500); };
}
// The fix-it dialog: sign in / install / test your AI. Opened from the red ring, the red bar or About me.
const AIFix = {
  async open() {
    await status(); const b = ST.brain || {};
    const prob = !b.available ? `${esc(b.app || 'Your AI app')} isn’t installed on this computer (or can’t be found).` : b.auth_error ? `${esc(b.name || 'Your AI')} is signed out — its sign-in expired.` : b.limited ? `${esc(b.name)} reached your plan’s limit. Agents carry on when it resets.` : `${esc(b.name || 'Your AI')} is connected.`;
    modal(`<h2 style="font-size:18px;margin-bottom:6px">${esc(b.name || 'Your AI')} connection</h2><p class="muted" style="margin:0 0 14px">${prob}</p>
      <div class="card list">
        <div class="item row gap"><div class="grow"><b>1 · Install ${esc(b.app || '')}</b><div class="small muted">${b.available ? 'Installed — ' + esc(b.version || '') : 'Opens the official installer in a new window.'}</div></div><button class="btn sm" id="fxI" ${b.available ? 'disabled' : ''}>Install</button></div>
        <div class="item row gap"><div class="grow"><b>2 · Sign in</b><div class="small muted">${AIPick.hint(b.provider)}</div></div><button class="btn sm primary" id="fxL" ${b.available ? '' : 'disabled'}>Sign in</button></div>
        <div class="item row gap"><div class="grow"><b>3 · Test</b><div class="small muted">One tiny request to check it works.</div><div id="fxO" class="small" style="margin-top:4px"></div></div><button class="btn sm" id="fxT" ${b.available ? '' : 'disabled'}>Test</button></div></div>
      <div class="row gap" style="margin-top:12px"><span class="small muted grow">Want ChatGPT or Gemini instead? Settings → Your AI.</span><button class="btn sm ghost" id="fxS">Open Settings</button></div>`);
    $('#fxI').onclick = async () => { const r = await post('/api/claude/install'); $('#fxO').textContent = r.manual || 'Installer opened in a new window. When it finishes, press Sign in.'; };
    $('#fxL').onclick = async () => { const r = await post('/api/claude/login'); $('#fxO').innerHTML = r.manual ? esc(r.manual) : 'A black window opened. Follow the line at the top of it, then come back and press <b>Test</b>.'; };
    $('#fxT').onclick = async () => { $('#fxO').innerHTML = '<span class="spin"></span> Testing…'; try { const r = await post('/api/claude/test'); $('#fxO').innerHTML = r.ok ? '<span style="color:var(--good)">✓ Connected</span>' : esc('Unexpected reply: ' + r.reply); if (r.ok) { store.set('authHide', {}); await status(); } } catch (e) { $('#fxO').innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; } };
    $('#fxS').onclick = () => { closeModal(); show('settings'); };
  },
};
// Red ring around your profile circle + a short pop-up whenever something you rely on stops working.
let HEALTH = { key: 'ok', first: true };
function health(serverDown = false) {
  const b = ST.brain || {};
  let key = 'ok', msg = '', lvl = 'ok';
  if (serverDown) { key = 'server'; lvl = 'bad'; msg = 'Career OS has stopped. Run start.bat (or the Career OS shortcut) to start it again — nothing is lost.'; }
  else if (!b.available) { key = 'noapp'; lvl = 'bad'; msg = `${b.app || 'Your AI app'} isn’t installed or can’t be found — agents that need ${b.name || 'the AI'} are paused. Settings → Your AI.`; }
  else if (b.auth_error) { key = 'auth'; lvl = 'bad'; msg = `${b.name || 'Your AI'} is signed out — it can’t read pages or write answers until you sign in again.`; }
  else if (b.limited) { key = 'limit'; lvl = 'warn'; msg = `${b.name || 'Your AI'} reached your plan’s limit — AI agents pause and carry on when it resets.`; }
  const me = $('#me');
  me.classList.toggle('bad', lvl === 'bad'); me.classList.toggle('warn', lvl === 'warn'); me.classList.toggle('good', lvl === 'ok' && !!b.available);
  me.dataset.tip = lvl === 'ok' ? `About me · ${b.name || 'AI'} connected` : msg + (key === 'server' ? '' : ' Click to fix.');
  if (key !== HEALTH.key) {
    if (lvl !== 'ok') popup(msg, lvl);
    else if (!HEALTH.first) popup(HEALTH.key === 'server' ? 'Career OS is running again.' : `${b.name || 'Your AI'} is connected again.`, 'ok');
  }
  HEALTH = { key, first: false, server: key === 'server' };
}
function popup(text, lvl = 'bad', ms = 7000) {
  let el = $('#popup');
  if (!el) { el = document.createElement('div'); el.id = 'popup'; el.setAttribute('role', 'alert'); document.body.appendChild(el); }
  el.className = 'popup on ' + lvl; el.innerHTML = `<span class="pi">${lvl === 'ok' ? '✓' : '!'}</span><div>${esc(text)}</div>`;
  clearTimeout(el._h); el._h = setTimeout(() => el.classList.remove('on'), ms);
}
async function status() {
  try { ST = await api('/api/status'); } catch (e) { $('#authbar').classList.add('hidden'); health(true); return; }
  authBar(); health();
  const dot = $('#bell .dot'); if (ST.unseen && !dot) $('#bell').insertAdjacentHTML('beforeend', '<span class="dot"></span>'); else if (!ST.unseen && dot) dot.remove();
  return ST;
}
async function settingsLoad() { const d = await api('/api/settings'); SET = d.settings; return d; }

// ================= APPLY =================
const Apply = { matchN: null, totalN: null, _landed: false,
  sub: store.get('applySub', 'ready'), F: null, offset: 0, sel: new Set(), built: false,
  async load() {
    await Promise.all([status(), settingsLoad()]);
    if (!Apply.F) {
      const f = SET.filters || {};
      Apply.F = { countries: f.countries || [], kinds: f.kinds || [], tracks: f.tracks || [], min_score: f.min_score ?? SET.min_score ?? 55,
        posted_days: f.posted_days ?? 30, sponsor_only: !!f.sponsor_only, q: '', order: f.order || 'score' };
    }
    Apply.build();
    Apply.renderFilters();
    Apply.renderSub();
  },
  build() {
    if (Apply.built) return; Apply.built = true;
    $('#v-apply').innerHTML = `
      <aside class="filters" aria-label="Filters and automation"><div class="hd"><div class="grow"><div style="font-size:15px;font-weight:600">Filters</div><div class="small muted" id="fView">Saved view</div></div><button class="btn sm" id="fReset">Reset</button></div>
        <div style="padding:14px 20px 0"><label class="search">${ICON.search}<input id="aQ" placeholder="Search roles, companies, places" aria-label="Search"></label></div>
        <div class="bd" id="fBody"></div><div class="ft"><span class="st ok"></span><span id="fSaved">Filters and switches save automatically</span></div></aside>
      <div class="main">
        <header class="header"><h1>Apply</h1>
          <div class="seg-tabs" id="aTabs">
            <button data-s="ready">Ready for you<span class="n" id="nReady"></span></button>
            <button data-s="matches">Matches<span class="n" id="nMatch"></span></button>
            <button data-s="answers">Learned answers</button>
</div>
          <div class="grow"></div>
          <button class="btn" id="aScan">Run scan now</button>
          <button class="btn primary" id="aFillAll">Autofill ready</button>
        </header>
        <div class="content" id="aBody"></div>
      </div>`;
    $$('#aTabs button').forEach(b => b.onclick = () => Apply.go(b.dataset.s));
    $('#aQ').oninput = debounce(e => { Apply.F.q = e.target.value; Apply.go('matches'); }, 300);
    $('#aScan').onclick = async () => { await post('/api/agents/run-scouts'); toast('Scan started — new matches appear here in a few minutes'); };
    $('#aFillAll').onclick = Apply.fillReady;
    $('#fReset').onclick = () => { Apply.F = { countries: [], kinds: [], tracks: [], min_score: SET.min_score || 55, posted_days: 30, sponsor_only: false, q: '', order: 'score' }; Apply.saveFilters(); Apply.renderFilters(); Apply.renderSub(); };
  },
  saveFilters: debounce(() => { const { q, ...f } = Apply.F; put('/api/filters', { filters: f }).then(() => { $('#fSaved').textContent = 'Saved'; setTimeout(() => $('#fSaved').textContent = 'Filters and switches save automatically', 1500); }); }, 500),
  async renderFilters() {
    const F = Apply.F;
    const facets = await api('/api/facets?min_score=' + (F.min_score || 0));
    const codes = [...new Set([...F.countries, ...Object.entries(facets.country).sort((a, b) => b[1] - a[1]).map(x => x[0])])].slice(0, 14);
    const chip = (group, key, label, count) => `<button class="chip ${F[group].includes(key) ? 'on' : ''}" data-g="${group}" data-k="${esc(key)}" aria-pressed="${F[group].includes(key)}">${esc(label)}${count != null ? `<span class="c">${count}</span>` : ''}</button>`;
    const sw = (key, label, on, small = '', disabled = false) => `<button class="switch" data-sw="${key}" aria-pressed="${!!on}" ${disabled ? 'disabled' : ''}><span class="lbl">${esc(label)}${small ? `<small>${small}</small>` : ''}</span><span class="tr"></span></button>`;
    const e = SET.email || {};
    $('#fBody').innerHTML = `
      <div class="fgroup"><div class="label">Countries</div><div class="chips">${codes.map(c => chip('countries', c, COUNTRY[c] || c, facets.country[c] || 0)).join('')}</div>
        <select class="input" id="fMoreC" aria-label="Add a country"><option value="">+ Add a country…</option>${Object.entries(COUNTRY).filter(([k]) => !codes.includes(k)).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div>
      <div class="fgroup"><div class="label">Opportunity type</div><div class="chips">${Object.entries(KINDS).map(([k, v]) => chip('kinds', k, v, facets.kind[k] || 0)).join('')}</div></div>
      <div class="fgroup"><div class="label">Role family</div><div class="chips">${Object.entries(TRACKS).map(([k, v]) => chip('tracks', k, v, facets.track[k] || 0)).join('')}</div></div>
      <div class="fgroup"><div class="row"><div class="label grow">Minimum match score</div><span class="mono" style="font-weight:600" id="fMinV">${F.min_score}</span></div><input type="range" class="range" id="fMin" min="0" max="95" step="5" value="${F.min_score}" aria-label="Minimum match score"></div>
      <div class="fgroup"><div class="label">Posted within</div><div class="seg" id="fPosted">${[[1, '24 h'], [7, '7 days'], [30, '30 days'], [0, 'Any']].map(([v, l]) => `<button data-v="${v}" class="${+F.posted_days === v ? 'on' : ''}">${l}</button>`).join('')}</div></div>
      ${sw('sponsor_only', "Hide roles that won't sponsor visas", F.sponsor_only)}
      <div class="fgroup" style="border-top:1px solid var(--line);padding-top:14px;gap:2px">
        <div class="row" style="margin-bottom:6px"><div class="label grow">Automation</div><label class="small muted">Scans <input class="input mono" id="fTimes" value="${esc((SET.scout_times || []).join(', '))}" style="height:28px;width:110px;margin-left:4px" aria-label="Scan times"></label></div>
        ${sw('auto_prepare', 'Draft cover letters after each scan', SET.auto_prepare !== false)}
        ${sw('auto_open_autofill', 'Open ready ones in autofill each evening', SET.auto_open_autofill !== false, `at ${esc((SET.notify || {}).daily_digest || '20:00')}`)}
        ${sw('ai_fill_unknown', "Claude drafts answers I don't know", SET.ai_fill_unknown !== false)}
        ${sw('email_enabled', 'Gmail tracking + follow-ups', e.enabled && e.app_password, e.app_password ? '' : 'Connect Gmail in Settings first', !e.app_password)}
        ${sw('toast', 'Deadline & interview pop-ups', (SET.notify || {}).toast !== false)}
        ${sw('remember_filters', 'Remember my filters', SET.remember_filters !== false)}
      </div>`;
    $$('#fBody .chip').forEach(b => b.onclick = () => { const g = b.dataset.g, k = b.dataset.k, a = F[g]; F[g] = a.includes(k) ? a.filter(x => x !== k) : [...a, k]; b.classList.toggle('on'); Apply.saveFilters(); Apply.refresh(); });
    $('#fMoreC').onchange = e => { if (e.target.value) { F.countries.push(e.target.value); Apply.saveFilters(); Apply.renderFilters(); Apply.refresh(); } };
    $('#fMin').oninput = e => { $('#fMinV').textContent = e.target.value; };
    $('#fMin').onchange = e => { F.min_score = +e.target.value; Apply.saveFilters(); Apply.renderFilters(); Apply.refresh(); };
    $$('#fPosted button').forEach(b => b.onclick = () => { F.posted_days = +b.dataset.v; $$('#fPosted button').forEach(x => x.classList.toggle('on', x === b)); Apply.saveFilters(); Apply.refresh(); });
    $('#fTimes').onchange = e => { const t = e.target.value.split(',').map(x => x.trim()).filter(x => /^\d{1,2}:\d{2}$/.test(x)).map(x => x.padStart(5, '0')); put('/api/filters', { scout_times: t }).then(() => { SET.scout_times = t; toast('Scan times saved: ' + t.join(' and ')); }); };
    $$('#fBody .switch').forEach(b => b.onclick = async () => {
      const k = b.dataset.sw, on = b.getAttribute('aria-pressed') !== 'true'; b.setAttribute('aria-pressed', on);
      if (k === 'sponsor_only') { F.sponsor_only = on; Apply.saveFilters(); Apply.refresh(); return; }
      await put('/api/filters', { [k]: on }); await settingsLoad(); toast('Saved');
    });
  },
  refresh: debounce(() => { Apply.offset = 0; if (Apply.sub === 'matches') Apply.renderSub(); else Apply.counts(); }, 250),
  query(extra = {}) {
    const F = Apply.F, p = new URLSearchParams({ status: 'new,shortlisted', country: F.countries.join(','), kind: F.kinds.join(','), track: F.tracks.join(','),
      min_score: F.min_score, posted_days: F.posted_days, sponsor_only: F.sponsor_only ? 1 : 0, q: F.q, order: F.order, limit: 100, offset: Apply.offset, ...extra });
    [...p.keys()].forEach(k => { if (p.get(k) === '') p.delete(k); });
    return '/api/opps?' + p;
  },
  async counts() {
    const s = ST.stats?.by_status || {};
    $('#nReady').textContent = (s.ready || 0) + (s.filling || 0);
    const r = await api(Apply.query({ offset: 0 }).replace('/api/opps?', '/api/count-opps?'));
    Apply.matchN = r.n; Apply.totalN = r.total;
    $('#nMatch').textContent = r.n.toLocaleString();
    const ml = $('#mLine'); if (ml) ml.innerHTML = Apply.matchLine();
    const k = $('#kMatch'); if (k) k.textContent = r.n.toLocaleString();
    return r;
  },
  matchLine() { return `<b>${(Apply.matchN ?? 0).toLocaleString()}</b> of ${(Apply.totalN ?? 0).toLocaleString()} jobs found so far match your filters · <a href="#sources">How and where we search →</a>`; },
  go(sub) { Apply.sub = sub; store.set('applySub', sub); Apply.offset = 0; Apply.renderSub(); },
  async renderSub() {
    if (!Apply._landed) { Apply._landed = true; const s = ST.stats?.by_status || {}; if (Apply.sub === 'ready' && !((s.ready || 0) + (s.filling || 0) + (s.preparing || 0))) Apply.sub = store.get('applySub', 'matches') === 'ready' ? 'matches' : store.get('applySub', 'matches'); }
    $$('#aTabs button').forEach(b => b.classList.toggle('on', b.dataset.s === Apply.sub));
    Apply.counts();
    (({ ready: Apply.ready, matches: Apply.matches, answers: Apply.answers })[Apply.sub] || Apply.matches)();
  },
  kpis(queue) {
    const s = ST.stats || {}, times = SET.scout_times || [], done = ST.slots_done_today || [];
    const next = times.find(t => !done.includes(t)) || (times[0] ? times[0] + ' tmrw' : '—');
    const week = queue.filter(o => { const d = daysTo(o.deadline); return d !== null && d >= 0 && d <= 7; }).length;
    const b = ST.brain || {};
    return `<div class="kpis">
      <div class="card kpi"><div class="l">Ready to submit</div><div class="n">${(s.by_status?.ready || 0) + (s.by_status?.filling || 0)}</div><div class="s">Cover letters drafted</div></div>
      <div class="card kpi"><div class="l">Matches for your filters</div><div class="n" id="kMatch">${(Apply.matchN ?? 0).toLocaleString()}</div><div class="s">${(s.new_today ?? 0).toLocaleString()} new today · score ${Apply.F.min_score}+</div></div>
      <div class="card kpi"><div class="l">Closing in 7 days</div><div class="n" style="color:var(--warn)">${week}</div><div class="s">Pop-up reminders ${(SET.notify || {}).toast !== false ? 'on' : 'off'}</div></div>
      <div class="card kpi"><div class="l">Next scan</div><div class="n">${esc(next)}</div><div class="s">${b.available ? `Claude · ${b.active || 0} of ${b.max_parallel} agents busy` : '<span style="color:var(--bad)">Claude Code not connected</span>'}</div></div></div>`;
  },
  async ready() {
    const [queue, soon] = await Promise.all([api('/api/opps?status=ready,filling,preparing&limit=200&order=deadline'), api('/api/opps?status=new,shortlisted,ready&order=deadline&limit=300')]);
    $('#aBody').innerHTML = Apply.kpis(soon) + `
      <div class="section-title"><h2>Ready for you</h2><span class="small muted">Autofill stops before Submit — <b style="color:var(--good)">green</b> is yours, <b style="color:var(--warn)">amber</b> is Claude's draft, <b style="color:var(--bad)">red</b> is yours to fill. Your edits are learned.</span></div>
      <div class="row gap"><label class="search grow">${ICON.plus}<input id="anyUrl" placeholder="Paste any application link to autofill or track it"></label><button class="btn" id="anyFill">Autofill link</button><button class="btn ghost" id="anyTrack">Just track it</button></div>
      ${queue.length ? `<div class="cards">${queue.map(Apply.card).join('')}</div>` : `<div class="empty"><div style="font-size:15px;font-weight:600;color:var(--ink)">Nothing ready to submit yet</div><div style="margin:6px 0 14px">After each scan (${esc((SET.scout_times || []).join(' and '))}) Claude drafts cover letters for your best new matches and they appear here. ${ST.brain?.available ? 'You can also start it now.' : 'Claude Code isn’t connected yet — connect it in Settings to get drafts.'}</div><div class="row gap" style="justify-content:center"><button class="btn primary" id="prepTop" ${ST.brain?.available ? '' : 'disabled'}>Draft letters for my top 10 now</button><button class="btn" id="goMatches">Browse matches</button></div></div>`}`;
    Apply.bind($('#aBody'));
    const gm = $('#goMatches'); if (gm) gm.onclick = () => Apply.go('matches');
    const pt = $('#prepTop'); if (pt) pt.onclick = async () => { pt.disabled = true; pt.innerHTML = '<span class="spin"></span> Drafting…'; await post('/api/prepare-top', { n: 10 }); toast('Claude is drafting cover letters for your top 10 — they appear here as they finish'); setTimeout(() => Apply.ready(), 20000); };
    $('#anyFill').onclick = async () => { const url = $('#anyUrl').value.trim(); if (!url) return; await post('/api/fill', { url }); toast('Opening in the autofill browser…'); $('#anyUrl').value = ''; };
    $('#anyTrack').onclick = async () => { const url = $('#anyUrl').value.trim(); if (!url) return; await post('/api/opps', { url, status: 'submitted' }); toast('Added to Track as submitted'); $('#anyUrl').value = ''; };
  },
  tags(o) {
    const d = daysTo(o.deadline), t = [`<span class="tag blue">${esc(KINDS[o.kind] || o.kind)}</span>`];
    if (o.track) t.push(`<span class="tag">${esc(TRACKS[o.track] || o.track)}</span>`);
    if (d !== null && d >= 0) t.push(`<span class="tag ${d <= 3 ? 'red' : d <= 7 ? 'amber' : ''}">closes ${esc(d10(o.deadline))} · ${d}d</span>`);
    if (o.sponsorship === 'yes') t.push('<span class="tag green">sponsors visas</span>');
    if (o.sponsorship === 'no') t.push('<span class="tag red">no sponsorship</span>');
    if (o.salary) t.push(`<span class="tag">${esc(String(o.salary).slice(0, 50))}</span>`);
    return `<div class="chips">${t.join('')}</div>`;
  },
  card(o) {
    const state = o.status === 'preparing' ? '<span class="spin"></span> Claude is drafting the cover letter…' : o.status === 'filling' ? 'Open in the autofill browser — waiting for your Submit' : 'Cover letter drafted';
    return `<div class="card opp" data-id="${o.id}">
      <div class="row gap" style="align-items:flex-start"><span class="score ${scoreCls(o.score)}">${o.score}</span><div class="grow" style="min-width:0"><div class="t">${esc(o.title)}</div><div class="o">${esc(o.org)} · ${esc(o.location || COUNTRY[o.country] || '')}</div></div></div>
      ${Apply.tags(o)}
      ${o.eligibility ? `<div class="small" style="color:var(--warn-ink)">⚠ ${esc(o.eligibility)}</div>` : ''}
      <div class="small muted row gap">${state}</div>
      <div class="acts"><button class="btn primary sm" data-a="fill">Autofill</button><button class="btn sm" data-a="details">Letter & details</button>
        <a class="btn sm ghost" href="${esc(o.url || o.apply_url)}" target="_blank" rel="noopener">Open ${ICON.ext}</a><button class="btn sm ghost" data-a="submitted">I submitted</button><button class="btn sm ghost" data-a="skipped">Skip</button></div></div>`;
  },
  bind(root) {
    $$('[data-a]', root).forEach(b => b.onclick = async () => {
      const id = +b.closest('[data-id]').dataset.id, a = b.dataset.a;
      if (a === 'fill') { await post('/api/fill', { ids: [id] }); toast('Opening the autofill browser…'); }
      else if (a === 'details') return Apply.details(id);
      else if (a === 'prepare') { await post(`/api/opps/${id}/prepare`); toast('Claude is drafting — it will move to Ready for you'); }
      else { await patch(`/api/opps/${id}`, { status: a }); toast(`Marked ${a}`); }
      setTimeout(() => { status().then(() => Apply.renderSub()); }, 400);
    });
  },
  async fillReady() {
    const rows = await api('/api/opps?status=ready&limit=30&order=deadline');
    if (!rows.length) return toast('Nothing ready yet');
    const r = await post('/api/fill', { ids: rows.map(r => r.id) }); toast(`${r.queued} applications opening in the autofill browser`);
  },
  async matches(append = false) {
    const rows = await api(Apply.query());
    const head = `<div class="tr th"><span><input type="checkbox" id="selAll" aria-label="Select all"></span><span>Score</span><span>Role</span><span>Type</span><span>Where</span><span>Deadline</span><span>Visa</span><span></span></div>`;
    const row = o => `<div class="tr" data-id="${o.id}"><span><input type="checkbox" class="sel" ${Apply.sel.has(o.id) ? 'checked' : ''} aria-label="Select"></span>
      <span class="score ${scoreCls(o.score)}">${o.score}</span>
      <span><a class="tt" href="${esc(o.url || o.apply_url)}" target="_blank" rel="noopener" style="color:var(--ink)">${esc(o.title)}</a><div class="ts">${esc(o.org)} · ${esc(o.source)}${o.status !== 'new' ? ' · ' + esc(o.status) : ''}</div></span>
      <span>${esc(KINDS[o.kind] || o.kind)}<div class="ts">${esc(TRACKS[o.track] || o.track || '')}</div></span>
      <span>${esc((o.location || '').slice(0, 60))}<div class="ts">${esc(COUNTRY[o.country] || o.country)}</div></span>
      <span class="mono small">${esc(d10(o.deadline)) || '<span class="muted">—</span>'}</span>
      <span class="small">${o.sponsorship === 'yes' ? '<span class="tag green">sponsors</span>' : o.sponsorship === 'no' ? '<span class="tag red">no</span>' : '<span class="muted">unknown</span>'}</span>
      <span class="row gap"><button class="btn sm" data-a="prepare">Draft letter</button><button class="btn sm ghost" data-a="details" aria-label="Details">•••</button></span></div>`;
    if (!append) {
      $('#aBody').innerHTML = `<div class="row gap wrap"><div class="section-title grow"><h2>Matches</h2><span class="small muted" id="mLine">${Apply.matchLine()}</span></div>
        <select class="input" id="mOrder" aria-label="Sort">${[['score', 'Best match first'], ['deadline', 'Deadline first'], ['new', 'Newest first']].map(([v, l]) => `<option value="${v}" ${Apply.F.order === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div class="bulk hidden" id="bulk"><b id="selN">0</b> selected<div class="grow"></div><button class="btn sm" data-b="prepare">Draft cover letters</button><button class="btn sm" data-b="fill">Autofill now</button><button class="btn sm" data-b="shortlisted">Shortlist</button><button class="btn sm ghost" data-b="skipped">Skip</button></div>
        <div class="card tbl" id="mTbl">${head}</div><div id="mMore"></div>`;
      $('#mOrder').onchange = e => { Apply.F.order = e.target.value; Apply.saveFilters(); Apply.offset = 0; Apply.matches(); };
      $$('#bulk [data-b]').forEach(b => b.onclick = () => Apply.bulk(b.dataset.b));
    }
    const tbl = $('#mTbl');
    if (!rows.length && !append) { tbl.insertAdjacentHTML('beforeend', '<div class="empty" style="margin:16px">No matches with these filters. Widen the countries or lower the score — or run a scan.</div>'); return; }
    tbl.insertAdjacentHTML('beforeend', rows.map(row).join(''));
    Apply.bind(tbl);
    $$('.sel', tbl).forEach(c => c.onchange = () => { const id = +c.closest('[data-id]').dataset.id; c.checked ? Apply.sel.add(id) : Apply.sel.delete(id); Apply.selUI(); });
    $('#selAll').onchange = e => { $$('.sel', tbl).forEach(c => { c.checked = e.target.checked; const id = +c.closest('[data-id]').dataset.id; e.target.checked ? Apply.sel.add(id) : Apply.sel.delete(id); }); Apply.selUI(); };
    $('#mMore').innerHTML = rows.length === 100 ? '<div style="text-align:center"><button class="btn" id="more">Load more</button></div>' : '';
    const more = $('#more'); if (more) more.onclick = () => { Apply.offset += 100; Apply.matches(true); };
  },
  selUI() { $('#selN').textContent = Apply.sel.size; $('#bulk').classList.toggle('hidden', !Apply.sel.size); },
  async bulk(act) {
    const ids = [...Apply.sel]; if (!ids.length) return;
    if (act === 'prepare') { for (const id of ids) await post(`/api/opps/${id}/prepare`); toast(`Claude is drafting ${ids.length} cover letters (a few at a time)`); }
    else if (act === 'fill') { await post('/api/fill', { ids }); toast('Opening the autofill browser…'); }
    else { await post('/api/opps/bulk', { ids, status: act }); toast(`${ids.length} marked ${act}`); }
    Apply.sel.clear(); Apply.offset = 0; Apply.matches(); status();
  },
  async details(id) {
    const o = await api(`/api/opps/${id}`), p = o.prepared || {};
    const pdf = (o.files || []).find(f => f.endsWith('.pdf'));
    modal(`<div style="font-size:12px" class="muted">${esc(o.org)} · ${esc(o.location)} · score ${o.score} · ${esc(o.status)}</div>
      <h2 style="font-size:22px;margin:4px 0 10px">${esc(o.title)}</h2>${Apply.tags(o)}
      <div class="row gap wrap" style="margin:14px 0"><a class="btn sm" href="${esc(o.url || o.apply_url)}" target="_blank" rel="noopener">Open job page ${ICON.ext}</a>
        <button class="btn sm primary" id="dFill">Autofill</button><button class="btn sm" id="dPrep">${p.cover_letter ? 'Redraft' : 'Draft'} letter with Claude</button>
        ${pdf ? `<a class="btn sm ghost" target="_blank" href="/api/opps/${id}/file/${encodeURIComponent(pdf)}">Letter PDF</a>` : ''}
        <div class="grow"></div><select class="input" id="dStatus" aria-label="Status">${['new', 'shortlisted', 'ready', 'filling', 'submitted', 'responded', 'assessment', 'interviewing', 'offer', 'rejected', 'withdrawn', 'skipped'].map(s => `<option ${s === o.status ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      ${p.fit_score != null ? `<div class="two"><div class="card" style="padding:12px 14px"><b>Fit ${p.fit_score}/100</b><ul style="margin:6px 0 0;padding-left:18px">${(p.fit_reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div><div class="card" style="padding:12px 14px"><b>Gaps</b><ul style="margin:6px 0 0;padding-left:18px">${(p.gaps || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>${(p.eligibility_flags || []).length ? `<b>Eligibility</b><ul style="margin:6px 0 0;padding-left:18px">${p.eligibility_flags.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div></div>` : ''}
      <h3 style="font-size:14px;margin:16px 0 6px">Cover letter</h3><textarea class="input" id="dLetter" style="width:100%;min-height:260px">${esc(p.cover_letter || '')}</textarea>
      <div class="row gap" style="margin-top:6px"><button class="btn sm" id="dSave">Save letter (rebuilds the PDF)</button><span class="small muted">This is exactly what gets uploaded.</span></div>
      ${p.pitch ? `<h3 style="font-size:14px;margin:16px 0 6px">Pitch</h3><div class="fb">${esc(p.pitch)}</div>` : ''}${p.why_company ? `<h3 style="font-size:14px;margin:16px 0 6px">Why this company</h3><div class="fb">${esc(p.why_company)}</div>` : ''}
      <div class="two" style="margin-top:16px"><label class="field">Notes<textarea class="input" id="dNotes" rows="3">${esc(o.notes || '')}</textarea></label><label class="field">Recruiter contact<input class="input" id="dContact" value="${esc(o.contact || '')}"><button class="btn sm" id="dMeta" style="align-self:flex-start;margin-top:6px">Save</button></label></div>
      <h3 style="font-size:14px;margin:16px 0 6px">Timeline</h3><div class="card list">${(o.events || []).map(e => `<div class="item"><span class="mono small muted">${esc(d10(e.created_at))}</span> <b>${esc(e.kind)}</b> ${esc(e.detail)}</div>`).join('') || '<div class="item muted">—</div>'}</div>
      <details style="margin-top:14px"><summary>Job description</summary><div class="fb" style="max-height:340px;overflow:auto">${esc((o.description || '').slice(0, 12000))}</div></details>`);
    $('#dFill').onclick = async () => { await post('/api/fill', { ids: [id] }); toast('Opening…'); };
    $('#dPrep').onclick = async () => { await post(`/api/opps/${id}/prepare`); toast('Drafting… reopen in a minute'); closeModal(); };
    $('#dSave').onclick = async () => { await put(`/api/opps/${id}/cover`, { text: $('#dLetter').value }); toast('Letter saved'); };
    $('#dMeta').onclick = async () => { await patch(`/api/opps/${id}`, { notes: $('#dNotes').value, contact: $('#dContact').value }); toast('Saved'); };
    $('#dStatus').onchange = async e => { await patch(`/api/opps/${id}`, { status: e.target.value }); toast('Status updated'); };
  },
  async answers() {
    const d = await api('/api/answers');
    $('#aBody').innerHTML = `<div class="section-title"><h2>What autofill has learned from you</h2><span class="small muted">Every correction or red field you fill is saved here and reused. Edit or delete anything.</span></div>
      <div class="row gap"><input class="input grow" id="nl" placeholder="Question, e.g. 'Are you legally authorised to work in the UK?'"><input class="input" id="nv" placeholder="Your answer" style="width:260px"><button class="btn" id="na">Add answer</button></div>
      <div class="two"><div class="card"><div class="answer-row" style="font-weight:600;color:var(--muted);font-size:12px"><span>Question</span><span>Answer</span><span>From</span><span></span></div>
        ${d.answers.map(a => `<div class="answer-row" data-aid="${a.id}"><span>${esc(a.label)}</span><input class="input" value="${esc(a.value)}"><span class="tag">${esc(a.source)} · ${a.uses}×</span><button class="btn sm ghost" data-del aria-label="Delete">✕</button></div>`).join('') || '<div class="empty" style="margin:14px">Nothing learned yet — it fills up as you correct forms.</div>'}</div>
      <div class="card list"><div class="item" style="font-weight:600">Corrections — what I got wrong</div>${d.corrections.map(c => `<div class="item"><div class="small muted">${esc(c.org || '')} · ${esc(c.label)}</div><s class="muted">${esc(String(c.filled).slice(0, 120))}</s> → <b>${esc(String(c.final).slice(0, 160))}</b></div>`).join('') || '<div class="item muted">No corrections yet.</div>'}</div></div>`;
    $$('[data-aid]').forEach(r => { $('input', r).onchange = e => put(`/api/answers/${r.dataset.aid}`, { value: e.target.value }).then(() => toast('Saved')); $('[data-del]', r).onclick = () => api(`/api/answers/${r.dataset.aid}`, { method: 'DELETE' }).then(Apply.answers); });
    $('#na').onclick = async () => { if (!$('#nl').value) return; await post('/api/answers', { label: $('#nl').value, value: $('#nv').value }); Apply.answers(); };
  },
};

// ================= EXTRA (your own job platforms) =================
const Extra = {
  async load() {
    const D = await api('/api/boards'); Extra.D = D;
    const C = D.catalogue, mine = D.boards, ag = D.agent || {};
    const rec = C.boards.filter(x => x.recommended && !x.added), sugg = rec.slice(0, 12), more = [...rec.slice(12), ...C.boards.filter(x => !x.recommended && !x.added)];
    const st = b => !b.enabled ? ['', 'Paused'] : b.needs_login && !b.last_run ? ['warn', 'Sign in first'] : /sign in/i.test(b.last_status || '') ? ['bad', 'Needs sign-in'] : /error|x |fail|timeout/i.test(b.last_status || '') ? ['bad', 'Problem'] : b.last_run ? ['ok', 'Working'] : ['run', 'Ready'];
    const LS = { traced: ['ok', 'In Matches'], new: ['run', 'Tracing…'], board_only: ['warn', 'Only on the board'], not_found: ['', 'Not on their site'] };
    $('#v-extra').innerHTML = `<div class="main"><header class="header"><h1>Extra</h1><span class="small muted" style="margin-left:8px">Your own job platforms — separate from the scouts</span><div class="grow"></div>${ag.running ? '<span class="pill run"><span class="spin"></span>Searching your platforms…</span>' : ''}<button class="btn primary" id="bRun" ${mine.length && !ag.running ? '' : 'disabled'}>Search my platforms now</button></header><div class="content" style="max-width:1180px">
      <div class="how" style="grid-template-columns:repeat(4,minmax(0,1fr))"><div class="card step"><span class="k">01</span><b>You add platforms</b><span class="small muted">Any job site you like — LinkedIn, TargetJobs, a niche board. We check it’s real.</span></div><div class="card step"><span class="k">02</span><b>You sign in once</b><span class="small muted">In Extra’s own browser window, yourself. Your password never passes through Career OS.</span></div><div class="card step"><span class="k">03</span><b>Extra searches</b><span class="small muted">${esc(D.settings.times.join(' and '))}: your roles × places, scrolling like a person. It never applies.</span></div><div class="card step"><span class="k">04</span><b>Found on the company’s site</b><span class="small muted">Each job is looked up on the employer’s own careers page, then added to Matches (source “extra”).</span></div></div>
      <div class="card" style="padding:16px 18px"><b>Add a job platform</b><div class="small muted">Type its name or address — e.g. <span class="mono">linkedin.com</span>, <span class="mono">targetjobs.co.uk</span> — or paste a results link you like. ${D.ai ? esc(D.ai_name) + ' checks it’s a real job platform and works out how to search it.' : 'Connect your AI so unknown sites can be checked.'}</div>
        <div class="row gap" style="margin-top:10px"><input class="input grow" id="bSite" placeholder="linkedin.com, gradcracker.com, a results link…"><button class="btn primary" id="bAdd">Add</button></div><div id="bMsg" class="small" style="margin-top:6px"></div>
        ${sugg.length ? `<div class="small muted" style="margin-top:12px">Suggested for your goals</div><div class="chips" style="margin-top:6px">${sugg.map(x => `<button class="chip" data-add="${esc(x.url.replace('{indeed}', 'www.indeed.com').split('?')[0])}" data-tip="${esc(x.where)} · ${esc(x.note || x.for)}">+ ${esc(x.name)}</button>`).join('')}</div>` : ''}
        ${more.length ? `<details style="margin-top:10px"><summary class="small muted" style="cursor:pointer">More boards (${more.length})</summary><div class="chips" style="margin-top:8px">${more.map(x => `<button class="chip" data-add="${esc(x.url.replace('{indeed}', 'www.indeed.com').split('?')[0])}">+ ${esc(x.name)} <span class="muted">· ${esc(x.where)}</span></button>`).join('')}</div></details>` : ''}</div>
      ${mine.length ? `<div class="card list">${mine.map(b => { const [c, t] = st(b); return `<div class="item row gap" style="align-items:center">
          <div class="grow" style="min-width:0"><div class="row gap"><b>${esc(b.name)}</b><span class="pill ${c}"><span class="d"></span>${t}</span>${b.verified ? '' : '<span class="tag">unchecked</span>'}</div>
            <div class="small muted" style="margin-top:3px">${esc(b.what || b.host)}${b.fixed_url ? ' · your saved search' : b.template ? ' · searches by link' : ' · searches with its search box'}</div>
            <div class="small" style="margin-top:3px;color:var(--ink-2)">${b.last_run ? `Last: ${esc(b.last_status || '')} · ` : ''}${b.leads} leads · <b>${b.traced}</b> found on company sites · ${b.board_only} only on ${esc(b.name)}</div>${b.warning ? `<div class="small" style="color:var(--warn-ink)">${esc(b.warning)}</div>` : ''}</div>
          <button class="btn sm" data-login="${b.id}">Sign in</button><button class="btn sm ghost" data-tog="${b.id}" data-en="${b.enabled}">${b.enabled ? 'Pause' : 'Resume'}</button><button class="btn sm ghost" data-del="${b.id}" aria-label="Remove">✕</button></div>`; }).join('')}</div>
        <div class="small muted" style="padding:0 4px">Sign in opens Career OS’s own board browser — you sign in there yourself and close it; your password never goes through Career OS. Heads-up: sites like LinkedIn don’t allow automated reading, even of your own signed-in view, so there’s some risk they restrict your account. The Extra agent keeps it slow and small (${esc(String((D.settings.searches_per_board) || 4))} searches per board per run, human pace).</div>` : ''}
      ${D.leads.length ? `<div class="section-title" style="margin-top:6px"><h2 style="font-size:15px">Leads from boards</h2><span class="small muted">${D.leads.length} most recent</span></div>
        <div class="card tbl"><div class="tr th" style="grid-template-columns:minmax(0,2.2fr) minmax(0,1.3fr) minmax(0,1.2fr) 110px 130px minmax(0,1.6fr)"><span>Role</span><span>Company</span><span>Place</span><span>Board</span><span>Status</span><span>What happened</span></div>
        ${D.leads.map(l => { const [c, t] = LS[l.status] || ['', l.status]; return `<div class="tr" style="grid-template-columns:minmax(0,2.2fr) minmax(0,1.3fr) minmax(0,1.2fr) 110px 130px minmax(0,1.6fr)"><span class="tt">${l.url ? `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a>` : esc(l.title)}</span><span>${esc(l.org)}</span><span class="small">${esc(l.location || '')}</span><span class="small muted">${esc(l.site)}</span><span><span class="pill ${c}"><span class="d"></span>${t}</span></span><span class="small muted">${esc(l.detail || '')}</span></div>`; }).join('')}</div>` : ''}
      <div class="card" style="padding:16px 18px"><b>Extra’s schedule & pace</b><div class="form" style="margin-top:10px">
        <label class="field">First run<input class="input" type="time" id="xT1" value="${esc(D.settings.times[0] || '08:40')}"></label><label class="field">Second run<input class="input" type="time" id="xT2" value="${esc(D.settings.times[1] || '18:40')}"></label>
        <label class="field">Searches per platform each run<input class="input" type="number" min="1" max="12" id="xN" value="${esc(String(D.settings.searches_per_board))}"><small>Rotates through all your roles × places across runs. Lower = gentler on the site.</small></label>
        <div class="field" style="gap:8px"><label class="row gap small"><input type="checkbox" id="xW" ${D.settings.show_window ? 'checked' : ''}> Show the browser window while it searches</label><label class="row gap small"><input type="checkbox" id="xU" ${D.settings.add_untraced ? 'checked' : ''}> Also add jobs only found on the platform (you apply there yourself)</label></div></div>
        <div class="row gap" style="margin-top:8px"><div class="grow small muted">${ag.last_run ? `Last run ${esc(ag.last_run.slice(0, 16).replace('T', ' '))} · ${esc(ag.last_status || '')}` : 'Not run yet.'}</div><button class="btn" id="xSave">Save</button></div></div>
      </div></div>`;
    $('#xSave').onclick = async () => { await put('/api/extra/settings', { times: [$('#xT1').value, $('#xT2').value].filter(Boolean), searches_per_board: +$('#xN').value || 4, show_window: $('#xW').checked, add_untraced: $('#xU').checked }); toast('Saved'); Extra.load(); };
    const add = async site => { $('#bMsg').innerHTML = `<span class="spin"></span> ${D.ai ? 'Checking the site…' : 'Adding…'}`; try { const r = await post('/api/boards', { site }); if (!r.ok) { $('#bMsg').innerHTML = `<span style="color:var(--bad)">${esc(r.error)}</span>`; return; } toast(`${r.board.name} added${r.board.needs_login ? ' — press Sign in on it' : ''}`); Extra.load(); } catch (e) { $('#bMsg').innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; } };
    $('#bAdd').onclick = () => $('#bSite').value.trim() && add($('#bSite').value.trim());
    $('#bSite').onkeydown = e => { if (e.key === 'Enter') $('#bAdd').click(); };
    $$('#v-extra [data-add]').forEach(x => x.onclick = () => add(x.dataset.add));
    $$('#v-extra [data-tip]').forEach(x => tipOn(x, esc(x.dataset.tip)));
    $$('#v-extra [data-login]').forEach(x => x.onclick = async () => { await post(`/api/boards/${x.dataset.login}/login`); toast('A browser window opened — sign in there, then close it', 5000); });
    $$('#v-extra [data-tog]').forEach(x => x.onclick = async () => { await patch(`/api/boards/${x.dataset.tog}`, { enabled: x.dataset.en === '1' ? 0 : 1 }); Extra.load(); });
    $$('#v-extra [data-del]').forEach(x => x.onclick = async () => { await api(`/api/boards/${x.dataset.del}`, { method: 'DELETE' }); Extra.load(); });
    const rb = $('#bRun'); if (rb) rb.onclick = async () => { await post('/api/boards/run'); toast('Extra is searching your platforms — this takes a few minutes'); setTimeout(() => VIEW === 'extra' && Extra.load(), 1500); };
    if (ag.running) setTimeout(() => VIEW === 'extra' && Extra.load(), 8000);
  },
};

// ================= TRACK =================
const COLS = [['submitted', 'Submitted'], ['responded', 'Responded'], ['assessment', 'Assessment'], ['interviewing', 'Interviewing'], ['offer', 'Offer'], ['closed', 'Closed']];
const Track = {
  sel: null,
  async load() {
    await Promise.all([status(), settingsLoad()]);
    const d = await api('/api/track');
    const P = d.pipeline.filter(o => o.status !== 'filling');
    const by = s => P.filter(o => s === 'closed' ? ['rejected', 'withdrawn'].includes(o.status) : o.status === s);
    const resp = P.filter(o => ['responded', 'assessment', 'interviewing', 'offer'].includes(o.status)).length;
    const fu = P.filter(o => o.followup_at).length;
    const e = SET.email || {};
    $('#v-track').innerHTML = `<div class="main">
      <header class="header"><h1>Track</h1>${e.enabled && e.app_password ? `<span class="pill ok" style="margin-left:8px"><span class="d"></span>Gmail synced${ST.email_last_check ? ' · ' + esc(ST.email_last_check.slice(11, 16)) + ' UTC' : ''}</span>` : '<span class="pill warn" style="margin-left:8px">Gmail not connected</span>'}
        <div class="grow"></div><button class="btn" id="tAdd">Add application</button><button class="btn" id="tMail">Check email now</button></header>
      <div class="content">
        <div class="kpis" style="grid-template-columns:repeat(5,minmax(0,1fr))">${[[P.length, 'Applied'], [P.length ? Math.round(100 * resp / P.length) + '%' : '—', 'Response rate'], [by('interviewing').length, 'Interviewing'], [by('offer').length, 'Offers'], [fu, 'Follow-ups drafted']].map(([n, l]) => `<div class="card kpi"><div class="l">${l}</div><div class="n">${n}</div></div>`).join('')}</div>
        ${e.enabled && e.app_password ? '' : `<div class="card" style="padding:14px 16px" ><b>Connect Gmail</b> and Track updates itself: confirmations, rejections, assessments and interview invites move cards along, and applications you made anywhere else get added. After 14 quiet days a polite follow-up is saved in your Gmail Drafts. <a href="#settings" id="tConn">Connect in Settings →</a></div>`}
        <div class="board">${COLS.map(([s, n]) => { const items = by(s); return `<div class="col"><h4>${n}<span class="mono">${items.length}</span></h4>${items.map(o => `<button class="mini ${Track.sel === o.id ? 'on' : ''}" data-id="${o.id}"><b>${esc(o.org)}</b><span>${esc(String(o.title).slice(0, 80))}</span><div class="s">${o.days_since_submit != null ? `sent ${o.days_since_submit}d ago` : ''}${o.followup_at ? ' · follow-up drafted' : ''}${o.days_since_contact != null ? ` · contact ${o.days_since_contact}d ago` : ''}</div></button>`).join('') || '<div class="muted small" style="padding:4px 6px">—</div>'}</div>`; }).join('')}</div>
        <div class="two"><div><div class="section-title" style="margin-bottom:8px"><h2>Deadlines coming up</h2></div><div class="card list">${d.deadlines.map(o => { const n = daysTo(o.deadline); return `<div class="item row gap"><span class="tag ${n <= 3 ? 'red' : n <= 7 ? 'amber' : ''}">${n}d</span><div class="grow"><b>${esc(o.org)}</b> · ${esc(o.title)}<div class="small muted">${esc(o.deadline)} · ${esc(o.status)}</div></div><button class="btn sm" data-open="${o.id}">Open</button></div>`; }).join('') || '<div class="item muted">No dated deadlines. Many roles are rolling — apply early.</div>'}</div></div>
          <div><div class="section-title" style="margin-bottom:8px"><h2>Recruiter emails</h2></div><div class="card list">${d.emails.map(m => `<div class="item"><span class="tag ${m.category === 'rejected' ? 'red' : m.category === 'offer' || m.category === 'interviewing' ? 'green' : m.category === 'assessment' ? 'amber' : ''}">${esc(m.category)}</span> <b>${esc(m.subject)}</b><div class="small muted">${esc(m.org || m.sender)} · ${esc(d10(m.received_at))}</div></div>`).join('') || '<div class="item muted">No recruiter emails matched yet.</div>'}</div></div></div>
      </div></div><aside class="drawer ${Track.sel ? '' : 'hidden'}" id="tDrawer" aria-label="Application detail"></aside>`;
    $$('#v-track .mini').forEach(b => b.onclick = () => { Track.sel = +b.dataset.id; $$('#v-track .mini').forEach(x => x.classList.toggle('on', x === b)); Track.drawer(); });
    $$('#v-track [data-open]').forEach(b => b.onclick = () => Apply.details(+b.dataset.open));
    $('#tMail').onclick = async () => { const a = (await api('/api/agents')).agents.find(x => x.kind === 'email'); if (a) { await post(`/api/agents/${a.id}/run`); toast('Checking Gmail…'); setTimeout(Track.load, 8000); } };
    $('#tAdd').onclick = () => { modal(`<h2 style="font-size:18px;margin-bottom:12px">Add an application you made</h2><div class="form"><label class="field full">Link to the job<input class="input" id="naU" placeholder="https://…"></label><label class="field">Company<input class="input" id="naO"></label><label class="field">Role<input class="input" id="naT"></label></div><div class="row gap" style="margin-top:14px"><button class="btn primary" id="naS">Add to Track</button></div>`); $('#naS').onclick = async () => { await post('/api/opps', { url: $('#naU').value, org: $('#naO').value, title: $('#naT').value, status: 'submitted' }); closeModal(); Track.load(); }; };
    const tc = $('#tConn'); if (tc) tc.onclick = e => { e.preventDefault(); show('settings'); };
    if (Track.sel) Track.drawer();
  },
  async drawer() {
    const o = await api(`/api/opps/${Track.sel}`), dr = $('#tDrawer'); dr.classList.remove('hidden');
    const days = o.submitted_at ? Math.round((Date.now() - new Date(o.submitted_at)) / 864e5) : null;
    const fu = (o.files || []).includes('followup.txt') ? await fetch(`/api/opps/${o.id}/file/followup.txt`).then(r => r.text()) : '';
    const color = k => ({ status: 'var(--accent)', email: 'var(--good)', followup: 'var(--warn)', learned: 'var(--accent)' }[k] || 'var(--nav-icon)');
    dr.innerHTML = `<div class="row"><div class="grow"><div class="small muted">${esc(o.title)}</div><div style="font-size:20px;font-weight:600">${esc(o.org)}${o.location ? ' · ' + esc(o.location.split(',')[0]) : ''}</div></div><button class="btn ghost sm" id="drX" aria-label="Close">✕</button></div>
      <div class="chips"><span class="tag ${o.status === 'offer' || o.status === 'interviewing' ? 'green' : o.status === 'rejected' ? 'red' : 'blue'}">${esc(o.status)}</span>${days != null && o.status === 'submitted' ? `<span class="tag ${days >= 14 ? 'amber' : ''}">${o.last_contact_at ? 'last contact ' + d10(o.last_contact_at) : 'no reply · ' + days + ' days'}</span>` : ''}</div>
      ${fu ? `<div class="card" style="padding:14px;background:var(--surface-2)"><div class="row"><b class="grow">Follow-up draft</b><span class="small muted">${SET.email?.create_drafts ? 'Saved in Gmail Drafts' : 'Copy and send'}</span></div><div class="small" style="white-space:pre-wrap;margin-top:8px;color:var(--ink-2)">${esc(fu.slice(0, 700))}</div><div class="row gap" style="margin-top:8px"><a class="btn sm primary" href="https://mail.google.com/mail/u/0/#drafts" target="_blank" rel="noopener">Open Gmail drafts</a><button class="btn sm" id="drCopy">Copy</button></div></div>` : ''}
      <label class="field">Status<select class="input" id="drSt">${['submitted', 'responded', 'assessment', 'interviewing', 'offer', 'rejected', 'withdrawn'].map(s => `<option ${s === o.status ? 'selected' : ''}>${s}</option>`).join('')}</select></label>
      <div><b>Timeline</b><ol class="timeline" style="margin-top:10px">${(o.events || []).slice(0, 12).map(e => `<li><span class="b" style="background:${color(e.kind)}"></span><div><b>${esc(e.kind)}</b> <span class="mono small muted">${esc(d10(e.created_at))}</span><div class="muted">${esc(e.detail)}</div></div></li>`).join('')}</ol></div>
      ${(o.emails || []).length ? `<div><b>Emails</b><div class="card list" style="margin-top:8px">${o.emails.map(m => `<div class="item"><b>${esc(m.subject)}</b><div class="small muted">${esc(m.sender)} · ${esc(d10(m.received_at))}</div></div>`).join('')}</div></div>` : ''}
      <label class="field">Notes<textarea class="input" id="drN" rows="3">${esc(o.notes || '')}</textarea></label>
      <label class="field">Recruiter<input class="input" id="drC" value="${esc(o.contact || '')}"></label>
      <div class="row gap"><button class="btn sm" id="drSave">Save</button><button class="btn sm ghost" id="drMore">Full details</button></div>`;
    $('#drX').onclick = () => { Track.sel = null; dr.classList.add('hidden'); $$('#v-track .mini').forEach(x => x.classList.remove('on')); };
    $('#drSt').onchange = async e => { await patch(`/api/opps/${o.id}`, { status: e.target.value }); Track.load(); };
    $('#drSave').onclick = async () => { await patch(`/api/opps/${o.id}`, { notes: $('#drN').value, contact: $('#drC').value }); toast('Saved'); };
    $('#drMore').onclick = () => Apply.details(o.id);
    const cp = $('#drCopy'); if (cp) cp.onclick = () => { navigator.clipboard?.writeText(fu); toast('Copied'); };
  },
};

// ================= LEARN =================
const Learn = {
  D: null, sel: store.get('learnSel', null), level: 1, chats: store.get('learnChats', {}), sessions: store.get('learnSessions', {}), mock: {}, focus: {}, poll: null,
  async load() {
    Learn.D = await api('/api/learn');
    const D = Learn.D, T = id => D.tracks.find(t => t.id === id);
    if (!Learn.sel || (!T(Learn.sel) && !Learn.sel.startsWith('__'))) Learn.sel = D.selected[0] || D.tracks[0].id;
    const t = T(Learn.sel);
    if (t && !Learn._lvlSet) { const lv = t.levels.find(l => l.total && l.done < l.total); Learn.level = lv ? lv.n : 1; Learn._lvlSet = true; }
    Learn.render();
    const running = Object.values(D.jobs || {}).some(j => j.status === 'running');
    clearTimeout(Learn.poll); if (running && VIEW === 'learn') Learn.poll = setTimeout(Learn.load, 8000);
  },
  pick(id) { Learn.sel = id; store.set('learnSel', id); Learn._lvlSet = false; Learn.load(); },
  render() {
    const D = Learn.D, sel = new Set(D.selected);
    const item = t => `<button class="it ${t.id === Learn.sel ? 'on' : ''}" data-t="${esc(t.id)}"><span class="grow">${esc(t.title)}</span><span class="p">${t.done}/${t.total}</span></button>`;
    const mine = D.tracks.filter(t => sel.has(t.id));
    const core = mine.filter(t => t.for_degree), roles = mine.filter(t => !t.for_degree && t.category !== 'custom'), custom = mine.filter(t => t.category === 'custom');
    const jobs = Object.entries(D.jobs || {}).filter(([k, j]) => j.status === 'running' && k.startsWith('track:'));
    $('#v-learn').innerHTML = `
      <aside class="lnav" aria-label="Your tracks"><div class="hd"><div style="font-size:15px;font-weight:600">Learn</div>
        <label class="search">${ICON.plus}<input id="lAdd" placeholder="Add any subject — e.g. Quantum computing" aria-label="Add any subject"></label></div>
        <div class="bd">
          ${core.length ? `<div class="grp core">Core for your degree</div>${core.map(item).join('')}` : ''}
          ${roles.length ? `<div class="grp role">From your target roles</div>${roles.map(item).join('')}` : ''}
          ${custom.length || jobs.length ? `<div class="grp other">Added by you</div>${custom.map(item).join('')}${jobs.map(([k, j]) => `<div class="it" style="cursor:default"><span class="grow">${esc(j.detail.replace('Building a track for ', ''))}</span><span class="spin"></span></div>`).join('')}` : ''}
          <div class="grp other">More</div>
          <button class="it" id="lBrowse"><span class="grow">Browse all tracks</span><span class="p">${D.tracks.length}</span></button>
          <button class="it ${Learn.sel === '__library' ? 'on' : ''}" data-t="__library"><span class="grow">My library</span><span class="p">${D.library.length}</span></button>
          <button class="it ${Learn.sel === '__history' ? 'on' : ''}" data-t="__history"><span class="grow">Test history</span><span class="p">${D.test_history.length}</span></button>
        </div></aside>
      <div class="lmain" id="lMain"></div>
      <aside class="teacher" aria-label="AI teacher"><div class="hd"><div style="width:32px;height:32px;border-radius:50%;background:var(--nav);display:grid;place-items:center">${ICON.cap}</div><div class="grow"><div style="font-weight:600">AI teacher</div><div class="small muted" id="tFocus">Open sources + your books · cites everything</div></div><button class="btn sm ghost" id="tClear" title="Start a fresh conversation">New chat</button></div>
        <div class="bd" id="tBody"></div>
        <div class="quick" style="padding:0 20px 10px">${[['simpler', 'Explain simpler'], ['deeper', 'Go deeper'], ['quiz', 'Quiz me'], ['papers', 'Newest papers'], ['mock', 'Mock interview']].map(([k, l]) => `<button class="chip" data-q="${k}">${l}</button>`).join('')}</div>
        <div class="ft"><textarea class="input grow" id="tIn" rows="2" placeholder="Ask anything about this track… (Ctrl+Enter)" aria-label="Ask the teacher"></textarea><button class="btn primary" id="tSend">Ask</button></div></aside>`;
    $$('#v-learn [data-t]').forEach(b => b.onclick = () => Learn.pick(b.dataset.t));
    $('#lBrowse').onclick = Learn.browse;
    $('#lAdd').onkeydown = async e => { if (e.key !== 'Enter' || !e.target.value.trim()) return; await post('/api/learn/track', { subject: e.target.value.trim() }); toast('Claude is building your track (beginner → research level) — a few minutes'); e.target.value = ''; setTimeout(Learn.load, 1500); };
    $$('.teacher [data-q]').forEach(b => b.onclick = () => Learn.quick(b.dataset.q));
    $('#tClear').onclick = () => { Learn.chats[Learn.sel] = []; Learn.sessions[Learn.sel] = null; Learn.mock[Learn.sel] = null; Learn.save(); Learn.renderChat(); };
    $('#tSend').onclick = () => Learn.ask($('#tIn').value.trim());
    $('#tIn').onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) $('#tSend').click(); };
    Learn.main(); Learn.renderChat();
  },
  main() {
    const D = Learn.D, m = $('#lMain');
    if (Learn.sel === '__library') {
      m.innerHTML = `<h1>My library</h1><p class="muted">PDFs in your books folder (${esc(SET.books_dir || 'not set — choose it in Settings')}). They open locally and are never uploaded. The teacher can read them when you ask.</p>
        <div class="card list">${D.library.map(b => `<div class="item row gap"><a class="grow" href="/books/${encodeURI(b.rel)}" target="_blank">${esc(b.name)}</a><span class="small muted mono">${b.size_mb} MB</span></div>`).join('') || '<div class="empty" style="margin:12px">No books found.</div>'}</div>`; return;
    }
    if (Learn.sel === '__history') {
      m.innerHTML = `<h1>Test history</h1><div class="card list">${D.test_history.map(h => `<div class="item row gap"><b class="grow">${esc(h.module_id)}</b><span class="score ${scoreCls(h.score)}">${Math.round(h.score)}</span><span class="small muted">${esc(d10(h.created_at))}</span></div>`).join('') || '<div class="empty" style="margin:12px">No tests yet — press “Test me” on any module.</div>'}</div>`; return;
    }
    const t = D.tracks.find(x => x.id === Learn.sel); if (!t) { m.innerHTML = '<div class="empty">Pick a track.</div>'; return; }
    const lv = t.levels[Learn.level - 1], mods = t.modules.filter(x => x.level === Learn.level);
    const inMine = D.selected.includes(t.id);
    const cat = t.for_degree ? '<span style="color:var(--warn-ink)">Core for your degree</span>' : t.category === 'custom' ? 'Added by you' : '<span style="color:var(--accent-ink)">Role track</span>';
    const deepJob = Object.entries(D.jobs || {}).find(([k, j]) => k === `deepen:${t.id}:${Learn.level}` && j.status === 'running');
    const refJob = (D.jobs || {})['refresh:' + t.id];
    m.innerHTML = `<div class="row gap" style="align-items:flex-end"><div class="grow"><div class="label">${cat}</div><h1 style="margin-top:4px">${esc(t.title)}</h1><div class="muted" style="margin-top:6px">${esc(t.why || '')}</div></div>
        <button class="btn" id="lRef" ${refJob && refJob.status === 'running' ? 'disabled' : ''}>${refJob && refJob.status === 'running' ? '<span class="spin"></span> Refreshing…' : 'Refresh sources'}</button>
        <button class="btn" id="lMine">${inMine ? 'Remove from my tracks' : 'Add to my tracks'}</button></div>
      ${refJob && refJob.status !== 'running' ? `<div class="small muted">Last refresh: ${esc(refJob.detail)}</div>` : ''}
      <div class="levels" role="tablist" aria-label="Level">${t.levels.map(l => `<button role="tab" aria-selected="${l.n === Learn.level}" class="${l.n === Learn.level ? 'on' : ''}" data-l="${l.n}"><span class="k">Level ${l.n}</span><span class="n">${l.name}</span><span class="s">${l.total ? `${l.done}/${l.total} done` : 'Generate with AI'}</span><div class="bar"><i style="width:${l.total ? Math.round(100 * l.done / l.total) : 0}%"></i></div></button>`).join('')}</div>
      ${mods.length ? mods.map(Learn.moduleHtml).join('') : `<div class="empty">No ${esc(lv.name)} modules yet for ${esc(t.title)}.<br><br>${deepJob ? '<span class="spin"></span> Claude is researching free sources…' : `<button class="btn primary" id="lDeep">Generate ${esc(lv.name)} modules with Claude</button><div class="small muted" style="margin-top:8px">Uses only free, open sources — textbooks, courses, arXiv papers — checked link by link.</div>`}</div>`}
      ${mods.length ? `<div class="row gap"><button class="btn ghost" id="lDeep2" ${deepJob ? 'disabled' : ''}>${deepJob ? '<span class="spin"></span> Adding modules…' : '+ Add more ' + esc(lv.name) + ' modules with Claude'}</button></div>` : ''}`;
    $$('#lMain [data-l]').forEach(b => b.onclick = () => { Learn.level = +b.dataset.l; Learn.main(); });
    $('#lRef').onclick = async () => { await post('/api/learn/refresh', { track_id: t.id }); toast('Looking for newer free sources…'); setTimeout(Learn.load, 1200); };
    $('#lMine').onclick = async () => { const s = inMine ? D.selected.filter(x => x !== t.id) : [...D.selected, t.id]; await post('/api/learn/select', { selected: s }); Learn.load(); };
    const deep = async () => { await post('/api/learn/deepen', { track_id: t.id, level: Learn.level }); toast('Claude is adding modules…'); setTimeout(Learn.load, 1200); };
    ['#lDeep', '#lDeep2'].forEach(s => { const b = $(s); if (b) b.onclick = deep; });
    $$('#lMain .module').forEach(el => {
      const mid = el.dataset.mid;
      $('select', el).onchange = e => post('/api/learn/progress', { module_id: mid, status: e.target.value }).then(Learn.load);
      const ta = $('textarea', el); ta.oninput = debounce(() => post('/api/learn/progress', { module_id: mid, notes: ta.value }), 700);
      $('[data-test]', el).onclick = () => Learn.test(mid);
      $('[data-teach]', el).onclick = () => { Learn.focus[t.id] = mid; Learn.ask(`Teach me "${t.modules.find(x => x.id === mid).title}" from the start, at ${lv.name} level.`); };
    });
  },
  moduleHtml(md) {
    return `<div class="card module ${md.status === 'done' ? 'done' : ''}" data-mid="${esc(md.id)}">
      <div class="row gap"><div class="grow" style="font-weight:600;font-size:15px">${esc(md.title)}</div><span class="small muted">~${esc(md.hours || '?')} h</span>
        <select class="input" style="height:30px" aria-label="Status">${['todo', 'learning', 'done'].map(s => `<option ${s === md.status ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="small" style="color:var(--ink-2)">${md.topics.map(esc).join(' · ')}</div>
      <div class="stack gap" style="gap:6px">${md.resources.map(r => `<div class="res"><span class="tag blue">${esc(r.kind || 'Web')}</span><a href="${esc(r.u)}" target="_blank" rel="noopener">${esc(r.t)}</a></div>`).join('')}
        ${md.local_books.map(b => `<div class="res"><span class="tag amber">Your PDF</span><a href="/books/${encodeURI(b.rel)}" target="_blank">${esc(b.name)}</a></div>`).join('')}</div>
      ${md.checkpoint ? `<div class="small"><b>Done when:</b> <span class="muted">${esc(md.checkpoint)}</span></div>` : ''}
      <details><summary class="small muted" style="cursor:pointer">Your notes${md.notes ? ' ✓' : ''}</summary><textarea class="input" rows="3" style="width:100%;margin-top:6px" placeholder="The examiner reads these…">${esc(md.notes)}</textarea></details>
      <div class="row gap"><button class="btn sm primary" data-teach>Teach me this</button><button class="btn sm" data-test>Test me</button></div></div>`;
  },
  async browse() {
    const D = Learn.D, sel = new Set(D.selected);
    modal(`<h2 style="font-size:18px;margin-bottom:4px">All tracks</h2><p class="muted small" style="margin:0 0 12px">Tick the ones you want in your sidebar. Want something not here? Type any subject in “Add any subject”.</p>
      <div class="card list">${D.tracks.map(t => `<label class="item row gap" style="cursor:pointer"><input type="checkbox" data-id="${esc(t.id)}" ${sel.has(t.id) ? 'checked' : ''}><b class="grow">${esc(t.title)}</b><span class="small muted">${t.for_degree ? 'core for your degree' : t.category}</span><span class="mono small muted">${t.total} modules</span></label>`).join('')}</div>
      <div class="row gap" style="margin-top:14px"><button class="btn primary" id="bSave">Save</button></div>`);
    $('#bSave').onclick = async () => { await post('/api/learn/select', { selected: $$('#modalBody input:checked').map(i => i.dataset.id) }); closeModal(); Learn.load(); };
  },
  renderChat() {
    const k = Learn.sel, msgs = Learn.chats[k] || [], t = Learn.D.tracks.find(x => x.id === k);
    $('#tFocus').textContent = Learn.mock[k] ? 'Mock interview in progress' : t ? `${t.title} · ${Learn.D.levels[Learn.level - 1]}` : 'Open sources + your books';
    $('#tBody').innerHTML = msgs.length ? msgs.map(m => m.pending ? `<div class="msg ai"><span class="spin"></span> <span class="tthink">${esc(m.text)}</span></div>` : `<div class="msg ${m.who}${m.err ? ' err' : ''}">${m.who === 'ai' ? Learn.linkify(m.text) : esc(m.text)}</div>`).join('')
      : `<div class="muted small">Ask anything — the teacher explains step by step, goes from beginner to research level, searches the web for up-to-date free sources and cites them, and can read the PDFs in your library.</div>`;
    $('#tBody').scrollTop = 1e9;
  },
  linkify(s) { return esc(s).replace(/(https?:\/\/[^\s)<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); },
  async ask(text, opts = {}) {
    const k = Learn.sel; if (!text || !Learn.D.tracks.find(x => x.id === k)) return;
    $('#tIn').value = '';
    const web = /paper|source|link|latest|newest|recent|resource|read next|course|video|arxiv/i.test(text);
    const pend = { who: 'ai', text: web ? 'Searching the web for up-to-date sources…' : 'Thinking…', pending: true };
    (Learn.chats[k] = Learn.chats[k] || []).push({ who: 'me', text: opts.label || text }, pend);
    Learn.renderChat();
    const t0 = Date.now(), tick = setInterval(() => { const s = Math.round((Date.now() - t0) / 1000); pend.text = (web ? 'Searching the web… ' : 'Thinking… ') + s + ' s'; const el = $('.tthink'); if (el && Learn.sel === k) el.textContent = pend.text; }, 1000);
    try {
      const r = Learn.mock[k]
        ? await post('/api/learn/mock', { track_id: k, message: text, session: Learn.mock[k] === true ? null : Learn.mock[k] })
        : await post('/api/learn/teach', { track_id: k, module_id: Learn.focus[k] || '', message: text, session: Learn.sessions[k] || null, level: Learn.level });
      if (Learn.mock[k]) Learn.mock[k] = r.session; else Learn.sessions[k] = r.session;
      Object.assign(pend, { text: r.reply || '(no reply)', pending: false });
    } catch (e) {
      Object.assign(pend, { text: /sign|log ?in|auth/i.test(e.message) ? 'Your AI is signed out — click your initials (bottom left) → Sign in, then ask again.' : 'That didn’t work: ' + e.message, pending: false, err: true });
    }
    clearInterval(tick);
    Learn.save();
    if (Learn.sel === k && VIEW === 'learn') Learn.renderChat();
  },
  save() { try { const out = {}; for (const [k, v] of Object.entries(Learn.chats)) out[k] = v.filter(m => !m.pending).slice(-30); store.set('learnChats', out); store.set('learnSessions', Learn.sessions); } catch (e) {} },
  quick(q) {
    const t = Learn.D.tracks.find(x => x.id === Learn.sel); if (!t) return;
    if (q === 'quiz') { const md = t.modules.find(m => m.level === Learn.level) || t.modules[0]; return Learn.test(md.id); }
    if (q === 'mock') { Learn.mock[t.id] = true; Learn.sessions[t.id] = null; return Learn.ask(`Start a mock interview for ${t.title}.`, { label: 'Start a mock interview' }); }
    if (Learn.mock[t.id] && q !== 'mock') { Learn.mock[t.id] = null; }
    const m = { simpler: 'Explain that again more simply, with a concrete example.', deeper: 'Go one level deeper — towards expert / research level — and tell me what to read next.',
      papers: `What are the most important recent, freely available papers or resources on ${t.title} at ${Learn.D.levels[Learn.level - 1]} level? Give links and one line each.` }[q];
    Learn.ask(m);
  },
  async test(mid) {
    const t0 = Date.now();
    modal('<h2 style="font-size:18px">Preparing your test…</h2><p class="muted"><span class="spin"></span> The examiner is writing 5 interview-level questions — usually 20–60 s. <span class="mono" id="tTimer">0 s</span></p><p class="small muted">You can close this and keep studying — it opens by itself when it’s ready.</p>');
    const tick = setInterval(() => { const el = $('#tTimer'); if (el) el.textContent = Math.round((Date.now() - t0) / 1000) + ' s'; }, 1000);
    let t; try { t = await post('/api/learn/test', { module_id: mid, n: 5 }); } catch (e) { clearInterval(tick); return modal(`<h2 style="font-size:18px">Couldn't create a test</h2><p>${esc(/sign|log ?in|auth/i.test(e.message) ? 'Your AI is signed out — click your initials (bottom left) → Sign in, then try again.' : e.message)}</p>`); }
    clearInterval(tick);
    if (!$('#modal').classList.contains('on')) toast('Your test is ready');
    modal(`<h2 style="font-size:18px;margin-bottom:12px">Test · ${esc(t.module)}</h2>${t.questions.map((q, i) => `<div class="card q" data-q="${esc(q.id)}"><div class="p">${i + 1}. ${esc(q.prompt)}</div>
      ${q.type === 'mcq' ? q.options.map((o, j) => `<label class="row gap" style="margin:4px 0"><input type="radio" name="${esc(q.id)}" value="${j}"> ${esc(o)}</label>`).join('')
        : q.type === 'code' ? `<textarea spellcheck="false">${esc(q.starter_code || 'def solve():\n    pass')}</textarea><div class="row gap" style="margin-top:6px"><button class="btn sm" data-run>Run ${q.n_tests} tests</button><span class="small muted">Python, runs on your computer</span></div>`
        : '<textarea placeholder="Your answer — show your reasoning"></textarea>'}<div class="fb hidden"></div></div>`).join('')}<button class="btn primary" id="tSub">Submit for grading</button>`);
    $$('#modalBody [data-run]').forEach(b => b.onclick = async () => { const q = b.closest('.q'); const r = await post('/api/learn/run', { test_id: t.test_id, qid: q.dataset.q, code: $('textarea', q).value }); const fb = $('.fb', q); fb.classList.remove('hidden'); fb.textContent = r.results.map((x, i) => `${x.ok ? '✓' : '✗'} test ${i + 1}${x.error ? ': ' + x.error : x.ok ? '' : `: got ${x.got}, expected ${JSON.stringify(x.expected)}`}`).join('\n'); });
    $('#tSub').onclick = async () => {
      const answers = {}; $$('#modalBody .q').forEach(q => { const r = $('input[type=radio]:checked', q); answers[q.dataset.q] = r ? r.value : ($('textarea', q)?.value || ''); });
      $('#tSub').disabled = true; $('#tSub').innerHTML = '<span class="spin"></span> Grading…';
      try { const g = await post('/api/learn/grade', { test_id: t.test_id, answers });
        g.results.forEach(r => { const fb = $(`#modalBody [data-q="${CSS.escape(r.id)}"] .fb`); if (fb) { fb.classList.remove('hidden'); fb.textContent = `${r.score}/10 — ${r.feedback}${r.reference ? '\n\nModel answer: ' + r.reference : ''}`; } });
        $('#tSub').insertAdjacentHTML('afterend', `<div class="fb"><b>Score ${g.score}%</b>${g.score >= 80 ? ' — module marked done ✓' : ''}\n${esc(g.overall || '')}</div>`); $('#tSub').remove(); Learn.load();
      } catch (e) { toast(e.message); $('#tSub').disabled = false; $('#tSub').textContent = 'Submit for grading'; }
    };
  },
};

// ================= AGENTS =================
const Agents = {
  async load() {
    await status();
    const d = await api('/api/agents'), b = ST.brain || {};
    $('#v-agents').innerHTML = `<div class="main"><header class="header"><h1>Agents</h1><span class="pill ${b.available ? 'ok' : 'bad'}" style="margin-left:8px"><span class="d"></span>${b.available ? `Claude Code · ${b.active || 0}/${b.max_parallel} busy` : 'Claude Code not found'}</span>
      <div class="grow"></div><button class="btn" id="gSync">Rebuild from my goals</button><button class="btn primary" id="gRun">Run all scouts now</button></header>
      <div class="content">
        <p class="muted small" style="margin:0">Scouts read public job boards (free, no Claude). Research agents use Claude Code with web search on your plan, once a day, ${b.max_parallel || 2} at a time. If your plan's limit is hit they pause and retry.</p>
        <details class="card" style="padding:14px 16px"><summary style="cursor:pointer"><b>+ New research agent</b> <span class="muted">— one field × one place; add as many as you like</span></summary>
          <div class="row gap wrap" style="margin-top:12px"><input class="input" id="nF" placeholder="Field, e.g. 'NHS digital graduate schemes'" style="flex:2;min-width:220px"><input class="input" id="nC" placeholder="Where, e.g. 'Germany' or 'Mumbai'" style="flex:1;min-width:160px"><input class="input" id="nK" placeholder="Kinds (jobs, internships…)" style="flex:1;min-width:160px"><button class="btn primary" id="nAdd">Create agent</button></div></details>
        <div class="agents">${d.agents.map(a => `<div class="card agent ${a.enabled ? '' : 'off'}" data-aid="${a.id}">
          <div class="row gap"><span class="st ${a.running ? 'run' : esc(a.last_status || '')}"></span><b class="grow">${esc(a.name)}</b><span class="tag">${esc(a.kind)}</span><button class="btn sm ghost" data-del aria-label="Delete agent" style="padding:0 6px">✕</button></div>
          ${a.config.field ? `<div class="small muted">${esc(a.config.field)} — ${esc(a.config.country || '')}</div>` : ''}
          <div class="small muted">${a.last_run ? `Last run ${esc(a.last_run.slice(0, 16).replace('T', ' '))} UTC · ${a.last_status === 'needs_claude' ? 'waiting for Claude Code' : esc(a.last_status)} · ${a.last_found} found` : 'Never run'}</div>
          <div class="row gap wrap"><button class="btn sm" data-run ${a.running ? 'disabled' : ''}>${a.running ? '<span class="spin"></span> Running' : 'Run now'}</button>
            <button class="switch inline" data-en aria-pressed="${!!a.enabled}"><span class="lbl">On</span><span class="tr"></span></button>
            <button class="switch inline" data-sch aria-pressed="${!!a.on_schedule}"><span class="lbl">Auto</span><span class="tr"></span></button>
</div>
          ${a.running && a.live_log ? `<pre class="log">${esc(a.live_log)}</pre>` : ''}</div>`).join('')}</div>
        <div class="two"><div><div class="section-title" style="margin-bottom:8px"><h2>Recent runs</h2></div><div class="card list">${d.runs.map(r => `<div class="item row gap"><span class="st ${r.status === 'running' ? 'run' : esc(r.status)}"></span><div class="grow">${esc(r.agent_name)}<div class="small muted">${esc((r.started_at || '').slice(0, 16).replace('T', ' '))} · ${esc(r.status)} · ${r.found} found</div></div><button class="btn sm ghost" data-log="${r.id}">Log</button></div>`).join('') || '<div class="item muted">No runs yet.</div>'}</div></div>
          <div><div class="section-title" style="margin-bottom:8px"><h2>Company job boards</h2><span class="small muted">${d.health.filter(h => h.ok).length} working · ${d.health.filter(h => !h.ok).length} not found</span></div><div class="card list" style="max-height:420px;overflow:auto">${d.health.slice(0, 200).map(h => `<div class="item row gap"><span class="st ${h.ok ? 'ok' : 'error'}"></span><span class="grow">${esc(h.key)}</span><span class="small muted">${esc(h.detail || '')}</span></div>`).join('') || '<div class="item muted">Runs after the first scan.</div>'}</div></div></div>
      </div></div>`;
    $('#gRun').onclick = async () => { await post('/api/agents/run-scouts'); toast('All scouts started'); setTimeout(Agents.load, 800); };
    $('#gSync').onclick = async () => { const r = await post('/api/agents/sync'); toast(`${r.added} added, ${r.removed} removed`); Agents.load(); };
    $('#nAdd').onclick = async () => { if (!$('#nF').value || !$('#nC').value) return toast('Give it a field and a place'); await post('/api/agents', { kind: 'research', field: $('#nF').value, country: $('#nC').value, kinds: $('#nK').value || 'jobs, internships, graduate roles, fellowships' }); toast('Agent created'); Agents.load(); };
    $$('.agent').forEach(el => { const id = el.dataset.aid;
      $('[data-run]', el).onclick = () => post(`/api/agents/${id}/run`).then(() => { toast('Started'); setTimeout(Agents.load, 700); });
      $('[data-en]', el).onclick = e => patch(`/api/agents/${id}`, { enabled: e.currentTarget.getAttribute('aria-pressed') !== 'true' }).then(Agents.load);
      $('[data-sch]', el).onclick = e => patch(`/api/agents/${id}`, { on_schedule: e.currentTarget.getAttribute('aria-pressed') !== 'true' }).then(Agents.load);
      $('[data-del]', el).onclick = () => { if (confirm('Delete this agent?')) api(`/api/agents/${id}`, { method: 'DELETE' }).then(Agents.load); }; });
    $$('[data-log]').forEach(b => b.onclick = async () => { const r = await api(`/api/runs/${b.dataset.log}`); modal(`<h2 style="font-size:18px;margin-bottom:10px">${esc(r.agent_name)}</h2><pre class="log" style="max-height:60vh">${esc(r.log || '')}</pre>`); });
    clearTimeout(Agents._t); if (d.agents.some(a => a.running) && VIEW === 'agents' && !$('#modal').classList.contains('on')) Agents._t = setTimeout(Agents.load, 3000);
  },
};

// ================= SETTINGS =================
const Settings = {
  async load() {
    const d = await settingsLoad(); await status();
    const s = SET, e = s.email || {}, b = ST.brain || {};
    const chk = (ok, html) => `<div class="row gap" style="align-items:flex-start;padding:6px 0"><span class="st ${ok ? 'ok' : 'limited'}" style="margin-top:6px"></span><div>${html}</div></div>`;
    $('#v-settings').innerHTML = `<div class="main"><header class="header"><h1>Settings</h1><div class="grow"></div><button class="btn" id="sWizard">Edit my profile & goals</button><button class="btn primary" id="sSave">Save changes</button></header>
      <div class="content" style="max-width:1100px">
        <div class="card" style="padding:16px 18px"><div class="label" style="margin-bottom:8px">Your AI — which subscription does the thinking</div><div id="sAI"></div><div class="small muted" style="margin-top:8px">Switching only changes which app Career OS talks to; your data, answers and About me stay the same.</div></div>
        <div class="card" style="padding:16px 18px"><div class="label" style="margin-bottom:6px">Setup checklist</div>
          ${chk(b.available, (b.available ? `Claude Code installed (${esc(b.version)}) — runs on your Claude plan, no API key.` : 'Claude Code not installed yet.') + ` <span class="row gap" style="display:inline-flex;margin-left:8px"><button class="btn sm" id="sInst" ${b.available ? 'disabled' : ''}>Install</button><button class="btn sm" id="sLogin">Sign in</button><button class="btn sm" id="sTest">Test</button></span> <span id="sOut" class="small"></span>`)}
          ${chk(ST.cv_ok, ST.cv_ok ? 'CV file found — autofill uploads it.' : 'Add your CV file below so autofill can upload it.')}
          ${chk(ST.email_enabled, ST.email_enabled ? 'Gmail connected — Track updates itself.' : 'Connect Gmail below for automatic tracking and follow-ups (optional).')}
          ${chk(ST.books > 0, ST.books ? `${ST.books} books in your library.` : 'Optional: point to a folder of your PDFs for the Learn teacher.')}</div>
        <div class="two">
          <div class="card" style="padding:18px"><h2 style="font-size:15px;margin-bottom:12px">Files & schedule</h2><div class="form" style="grid-template-columns:1fr">
            <label class="field">CV file (PDF)<input class="input" id="sCv" value="${esc(s.cv_path)}"><small>Uploaded to applications in most countries.</small></label>
            <label class="field">Short resume (PDF, optional)<input class="input" id="sRes" value="${esc(s.resume_path)}"></label>
            <label class="field">Upload the short resume instead of the CV for<input class="input" id="sResC" value="${esc((s.use_resume_for_countries || []).join(', '))}" placeholder="country codes, e.g. US, IN — blank = always the CV"></label>
            <label class="field">Books folder (optional)<input class="input" id="sBooks" value="${esc(s.books_dir)}"></label>
            <label class="field">Scan times<input class="input mono" id="sTimes" value="${esc((s.scout_times || []).join(', '))}"></label>
            <label class="field">Daily digest + autofill time<input class="input mono" id="sDigest" value="${esc((s.notify || {}).daily_digest || '20:00')}"></label>
            <label class="field">Claude agents at once<input class="input" id="sPar" type="number" min="1" max="6" value="${s.max_parallel_agents}"><small>Higher = faster, but uses your plan's limit sooner.</small></label>
            <label class="field">Cover letters drafted per scan<input class="input" id="sTop" type="number" value="${s.auto_prepare_top}"></label>
            <label class="field">Browser for autofill<select class="input" id="sBr">${[['chrome', 'Chrome'], ['msedge', 'Edge'], ['', 'Built-in Chromium']].map(([v, l]) => `<option value="${v}" ${s.browser_channel === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
            <label class="field">Appearance<select class="input" id="sTheme">${[['system', 'Match my computer'], ['light', 'Light'], ['dark', 'Dark']].map(([v, l]) => `<option value="${v}" ${store.get('theme', 'system') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div></div>
          <div class="stack" style="gap:16px"><div class="card" style="padding:18px"><h2 style="font-size:15px;margin-bottom:6px">Gmail tracking</h2>
            <p class="small muted" style="margin:0 0 12px">Free and local. Needs a Google <b>app password</b>: Google Account → Security → turn on 2-Step Verification → App passwords → create “Career OS”. Read-only, except it saves follow-up <i>drafts</i>; it never sends email.</p>
            <div class="form" style="grid-template-columns:1fr"><button class="switch" id="eOn" aria-pressed="${!!e.enabled}"><span class="lbl">Track my applications from Gmail</span><span class="tr"></span></button>
              <label class="field">Gmail address<input class="input" id="eAddr" value="${esc(e.address || d.profile_yaml.match(/email:\s*"?([^"\n]+)/)?.[1] || '')}"></label>
              <label class="field">App password<input class="input" id="ePass" type="password" value="${esc(e.app_password || '')}" placeholder="16 letters"></label>
              <label class="field">Draft a follow-up after (days without reply)<input class="input" id="eDays" type="number" value="${e.followup_after_days}"></label>
              <div class="row gap"><button class="btn" id="eTest">Test connection</button><span id="eOut" class="small muted"></span></div></div></div>
            <div class="card" style="padding:18px"><h2 style="font-size:15px;margin-bottom:6px">Optional free job APIs</h2><p class="small muted" style="margin:0 0 12px">More countries and boards. Free keys.</p><div class="form" style="grid-template-columns:1fr">
              <label class="field">Adzuna app_id <small>developer.adzuna.com</small><input class="input" id="azI" value="${esc(s.adzuna?.app_id || '')}"></label>
              <label class="field">Adzuna app_key<input class="input" id="azK" value="${esc(s.adzuna?.app_key || '')}"></label>
              <label class="field">Reed API key <small>reed.co.uk/developers</small><input class="input" id="rdK" value="${esc(s.reed?.api_key || '')}"></label></div></div></div></div>
        <details class="card" style="padding:16px 18px"><summary style="cursor:pointer"><b>Advanced</b> — edit your profile file and the company list directly</summary>
          <div class="two" style="margin-top:12px"><label class="field">profile.yaml<textarea class="code" id="pY" rows="22">${esc(d.profile_yaml)}</textarea></label><label class="field">companies.yaml<textarea class="code" id="cY" rows="22">${esc(d.companies_yaml)}</textarea></label></div></details>
      </div></div>`;
    $('#eOn').onclick = e => e.currentTarget.setAttribute('aria-pressed', e.currentTarget.getAttribute('aria-pressed') !== 'true');
    $('#sTheme').onchange = e => { store.set('theme', e.target.value); if (e.target.value === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = e.target.value; };
    $('#sWizard').onclick = () => Onboarding.open(true);
    api('/api/ai').then(A => { $('#sAI').innerHTML = AIPick.html(A); AIPick.bind(); });
    $('#sInst').onclick = async () => { const r = await post('/api/claude/install'); $('#sOut').textContent = r.manual || 'Installer opened in a new window.'; };
    $('#sLogin').onclick = async () => { const r = await post('/api/claude/login'); $('#sOut').textContent = r.manual || 'Sign in in the window that opened, then press Test.'; };
    $('#sTest').onclick = async () => { $('#sOut').innerHTML = '<span class="spin"></span>'; try { const r = await post('/api/claude/test'); $('#sOut').innerHTML = r.ok ? '<span style="color:var(--good)">✓ Connected</span>' : esc(r.reply); } catch (e) { $('#sOut').innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; } };
    $('#sSave').onclick = Settings.save;
    $('#eTest').onclick = async () => { $('#eOut').textContent = 'Saving and testing…'; await Settings.save(); try { await post('/api/settings/test-email'); $('#eOut').textContent = 'Connected ✓'; } catch (err) { $('#eOut').textContent = 'Failed: ' + err.message; } };
  },
  async save() {
    const times = $('#sTimes').value.split(',').map(x => x.trim()).filter(Boolean);
    const body = { settings: { cv_path: $('#sCv').value, resume_path: $('#sRes').value, use_resume_for_countries: $('#sResC').value.split(/[,\s]+/).map(x => x.trim().toUpperCase()).filter(Boolean), books_dir: $('#sBooks').value, scout_times: times,
      max_parallel_agents: +$('#sPar').value, auto_prepare_top: +$('#sTop').value, browser_channel: $('#sBr').value,
      notify: { daily_digest: $('#sDigest').value }, email: { enabled: $('#eOn').getAttribute('aria-pressed') === 'true', address: $('#eAddr').value, app_password: $('#ePass').value, followup_after_days: +$('#eDays').value },
      adzuna: { app_id: $('#azI').value, app_key: $('#azK').value }, reed: { api_key: $('#rdK').value } },
      profile_yaml: $('#pY').value, companies_yaml: $('#cY').value };
    try { await put('/api/settings', body); toast('Settings saved'); await settingsLoad(); } catch (e) { toast(e.message, 5000); }
  },
};


// ================= designed dropdowns (enhances every <select class="input">) =================
const CHEV = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
function enhanceSelect(sel) {
  if (sel.dataset.dd || sel.closest('.dd')) return;
  sel.dataset.dd = '1';
  const wrap = document.createElement('div');
  const block = sel.closest('.field') || sel.style.width === '100%' || sel.classList.contains('grow');
  wrap.className = 'dd' + (block ? ' block' : '') + (sel.style.height && parseInt(sel.style.height) <= 30 ? ' sm' : '');
  if (sel.style.width && !block) wrap.style.width = sel.style.width;
  if (sel.style.maxWidth) wrap.style.maxWidth = sel.style.maxWidth;
  sel.parentNode.insertBefore(wrap, sel); wrap.appendChild(sel);
  const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'dd-btn';
  btn.setAttribute('aria-haspopup', 'listbox'); if (sel.getAttribute('aria-label')) btn.setAttribute('aria-label', sel.getAttribute('aria-label'));
  const menu = document.createElement('div'); menu.className = 'dd-menu'; menu.setAttribute('role', 'listbox');
  wrap.append(btn, menu);
  const paint = () => { const o = sel.options[sel.selectedIndex]; btn.innerHTML = `<span class="v">${esc(o ? o.text : '')}</span>${CHEV}`; };
  const build = () => { menu.innerHTML = Array.from(sel.options).map((o, i) => `<button type="button" class="dd-opt" role="option" data-i="${i}" aria-selected="${i === sel.selectedIndex}">${esc(o.text)}</button>`).join(''); };
  const close = () => { wrap.classList.remove('open'); document.removeEventListener('mousedown', outside, true); };
  const outside = e => { if (!wrap.contains(e.target)) close(); };
  const pick = i => { if (i !== sel.selectedIndex) { sel.selectedIndex = i; sel.dispatchEvent(new Event('change', { bubbles: true })); } paint(); close(); btn.focus(); };
  const open = () => {
    build(); wrap.classList.add('open');
    const r = btn.getBoundingClientRect(); wrap.classList.toggle('up', window.innerHeight - r.bottom < 260 && r.top > 260); wrap.classList.toggle('right', r.left + 240 > window.innerWidth);
    const cur = menu.querySelector('[aria-selected="true"]'); if (cur) { cur.classList.add('act'); cur.scrollIntoView({ block: 'nearest' }); }
    document.addEventListener('mousedown', outside, true);
  };
  btn.onclick = () => wrap.classList.contains('open') ? close() : open();
  menu.onclick = e => { const o = e.target.closest('.dd-opt'); if (o) pick(+o.dataset.i); };
  btn.onkeydown = e => {
    const opts = $$('.dd-opt', menu), act = opts.findIndex(o => o.classList.contains('act'));
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); if (!wrap.classList.contains('open')) return open(); const n = Math.max(0, Math.min(opts.length - 1, act + (e.key === 'ArrowDown' ? 1 : -1))); opts.forEach((o, i) => o.classList.toggle('act', i === n)); opts[n]?.scrollIntoView({ block: 'nearest' }); }
    else if (e.key === 'Enter' && wrap.classList.contains('open')) { e.preventDefault(); if (act >= 0) pick(act); }
    else if (e.key === 'Escape') close();
  };
  sel.addEventListener('change', paint);
  paint();
}
new MutationObserver(() => $$('select.input:not([data-dd])').forEach(enhanceSelect)).observe(document.body, { childList: true, subtree: true });

// small hover tooltip used by charts
const tipbox = $('#tipbox');
function tipOn(el, html) { el.addEventListener('mousemove', e => { tipbox.innerHTML = html; tipbox.style.display = 'block'; tipbox.style.left = (e.clientX + 12) + 'px'; tipbox.style.top = (e.clientY + 12) + 'px'; }); el.addEventListener('mouseleave', () => tipbox.style.display = 'none'); }

// ================= USAGE (Claude plan meter) =================
const PCOL = { 'Research agents': '#2448C8', 'Company finders': '#7C3AED', 'Programme finders': '#0E7490', 'Cover letters': '#15803D', 'Form answers': '#A15C00',
  'AI teacher': '#DB2777', 'Tests & grading': '#EA580C', 'Mock interviews': '#9333EA', 'Learn builder': '#0891B2', 'CV import': '#65A30D', 'Board fixer': '#64748B', 'Connection test': '#94A3B8', 'Browser chat': '#CA8A04', 'About me': '#0D9488', 'Other agents': '#475569', other: '#94A3B8' };
const pcol = p => PCOL[p] || '#94A3B8';
const fmtT = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : String(n || 0);
async function meter() {
  let u; try { u = await api('/api/usage?days=1'); } catch (e) { return; }
  const est = u.limit.estimate_tokens, used = u.window.tokens, pct = u.limit.paused ? 100 : est ? Math.min(99, Math.round(100 * used / est)) : null;
  const color = u.limit.paused ? '#F2B24C' : '#6C8CFF', r = 16, C = 2 * Math.PI * r, frac = pct == null ? Math.min(1, used / 400000) : pct / 100;
  $('#meter').innerHTML = `<svg width="38" height="38" viewBox="0 0 40 40"><circle cx="20" cy="20" r="${r}" fill="none" stroke="#2B3440" stroke-width="4"/><circle cx="20" cy="20" r="${r}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-dasharray="${C * frac} ${C}"/></svg><span class="pct">${u.limit.paused ? '||' : pct != null ? pct + '%' : fmtT(used)}</span>`;
  $('#meter').dataset.tip = u.limit.paused ? 'Claude paused — plan limit reached' : `Claude usage · last 5 h: ${fmtT(used)} tokens · no extra cost`;
}
const Usage = {
  range: 'today',
  async load() {
    const u = await api('/api/usage?days=14'); Usage.u = u; meter();
    const R = u[Usage.range === 'window' ? 'window' : Usage.range], b = u.brain;
    const tot = R.tokens || 0, est = u.limit.estimate_tokens;
    const days = [...new Set(u.days.map(d => d.d))], maxDay = Math.max(1, ...days.map(d => u.days.filter(x => x.d === d).reduce((a, x) => a + (x.tokens || 0), 0)));
    const purposes = [...new Set(u.days.map(d => d.purpose))];
    $('#v-usage').innerHTML = `<div class="main"><header class="header"><h1>Claude usage</h1>
      <span class="pill ${b.available ? 'ok' : 'bad'}" style="margin-left:8px"><span class="d"></span>${b.available ? 'Connected · ' + esc(b.version) : 'Claude Code not connected'}</span>
      ${u.limit.paused ? `<span class="pill warn">Paused — ${esc(u.limit.msg || 'plan limit reached')}</span>` : ''}<div class="grow"></div>
      <div class="seg" style="width:340px">${[['window', 'Last 5 h'], ['today', 'Today'], ['week', '7 days'], ['month', '30 days']].map(([k, l]) => `<button data-r="${k}" class="${Usage.range === k ? 'on' : ''}">${l}</button>`).join('')}</div></header>
      <div class="content">
        <div class="kpis">
          <div class="card kpi"><div class="l">Extra cost to you</div><div class="n" style="color:var(--good)">0</div><div class="s">Runs on your Claude plan · API keys are blocked</div></div>
          <div class="card kpi"><div class="l">Tokens used</div><div class="n">${fmtT(tot)}</div><div class="s">${R.calls} Claude runs · ${R.web} web searches</div></div>
          <div class="card kpi"><div class="l">If this were the paid API</div><div class="n">$${R.usd.toFixed(2)}</div><div class="s">What you’re <b>not</b> paying (Claude’s own estimate)</div></div>
          <div class="card kpi"><div class="l">Plan limit (5-hour window)</div><div class="n">${u.limit.paused ? 'Paused' : est ? Math.min(99, Math.round(100 * u.window.tokens / est)) + '%' : '—'}</div><div class="s">${est ? `vs ~${fmtT(est)} tokens when you last hit it` : 'Learns your limit the first time it’s reached'}</div></div></div>
        <div class="card" style="padding:18px 20px"><div class="row"><h2 style="font-size:15px" class="grow">Where it goes</h2><span class="small muted">Hover a segment</span></div>
          ${tot ? `<div class="ubar" style="margin:12px 0" id="uBar">${R.by_purpose.map(p => `<i data-p="${esc(p.purpose)}" style="width:${100 * (p.tokens || 0) / tot}%;background:${pcol(p.purpose)}"></i>`).join('')}</div>
          <div class="legend">${R.by_purpose.map(p => `<span><b style="background:${pcol(p.purpose)}"></b>${esc(p.purpose)} <span class="mono muted">${fmtT(p.tokens)}</span></span>`).join('')}</div>`
          : '<div class="empty" style="margin-top:12px">No Claude use in this period yet.</div>'}</div>
        <div class="card" style="padding:18px 20px 30px"><h2 style="font-size:15px">Last 14 days</h2>
          <div class="cols">${days.map(d => { const rows = u.days.filter(x => x.d === d); return `<div class="c">${rows.map(x => `<i data-t="${esc(x.purpose)}: ${fmtT(x.tokens)} tokens · ${esc(d)}" style="height:${100 * (x.tokens || 0) / maxDay}%;background:${pcol(x.purpose)}"></i>`).join('')}<span class="lb">${esc(d.slice(5))}</span></div>`; }).join('') || '<div class="empty" style="flex:1">Nothing yet.</div>'}</div></div>
        <div class="freegrid"><div class="card" style="padding:16px 18px"><h2 style="font-size:15px;color:var(--good)">Free — no Claude at all</h2><ul style="padding-left:18px;margin:8px 0 0">${u.free.map(f => `<li>${esc(f)}</li>`).join('')}</ul></div>
          <div class="card" style="padding:16px 18px"><h2 style="font-size:15px;color:var(--accent-ink)">Uses your Claude plan (no extra cost)</h2><ul style="padding-left:18px;margin:8px 0 0">${u.plan.map(f => `<li>${esc(f)}</li>`).join('')}</ul>
            <div class="small muted" style="margin-top:8px">Up to ${u.max_parallel} Claude agents run at once (Settings). When the plan’s limit is reached they pause and carry on after it resets.</div></div></div>
      </div></div>`;
    $$('#v-usage [data-r]').forEach(b => b.onclick = () => { Usage.range = b.dataset.r; Usage.load(); });
    $$('#uBar i').forEach(i => { const p = R.by_purpose.find(x => x.purpose === i.dataset.p); tipOn(i, `<b>${esc(p.purpose)}</b> · ${fmtT(p.tokens)} tokens · ${p.calls} runs · ${p.web || 0} searches`); });
    $$('#v-usage .cols i').forEach(i => tipOn(i, esc(i.dataset.t)));
  },
};

// ================= WHERE WE SEARCH =================
const SYS = { greenhouse: ['Greenhouse', '#15803D'], lever: ['Lever', '#2448C8'], ashby: ['Ashby', '#7C3AED'], workday: ['Workday', '#EA580C'], smartrecruiters: ['SmartRecruiters', '#0891B2'], workable: ['Workable', '#DB2777'], page: ['Careers page', '#64748B'] };
const Sources = {
  q: '',
  async load() {
    const d = await api('/api/sources'); Sources.d = d;
    const all = d.groups.flatMap(g => g.companies), feedsN = all.filter(c => c.ats !== 'page').length, pagesN = all.filter(c => c.ats === 'page').length;
    const finders = d.finders.filter(f => f.kind !== 'research'), research = d.finders.filter(f => f.kind === 'research');
    const st = f => f.running ? '<span class="spin"></span> running' : f.last_run ? `${esc(f.last_status === 'needs_claude' ? 'waiting for Claude' : f.last_status)} · ${f.found} found · ${esc(f.last_run.slice(0, 10))}` : 'not run yet';
    $('#v-sources').innerHTML = `<div class="main"><header class="header"><h1>Where we search</h1><span class="small muted" style="margin-left:8px">${all.length} companies · ${d.total_jobs.toLocaleString()} jobs seen so far</span><div class="grow"></div><button class="btn primary" id="sRun">Scan everything now</button></header>
      <div class="content">
        <div class="how">
          <div class="card step"><span class="k">1 · FIND</span><b>Top employers & programmes</b><span class="small muted">Company finders ask Claude for the top 100 employers in each of your sectors. Programme finders list up to 100 graduate schemes, internships, fellowships, apprenticeships and scholarships.</span></div>
          <div class="card step"><span class="k">2 · CONNECT</span><b>Their real job lists</b><span class="small muted">For each careers page we detect the job system behind it (Greenhouse, Lever, Ashby, Workday…) and read its public job feed. Custom sites are opened in a hidden browser.</span></div>
          <div class="card step"><span class="k">3 · SCAN</span><b>Twice a day</b><span class="small muted">At ${esc((d.scout_times || []).join(' and '))} every source is re-read, new roles are added and closed ones drop off. Research agents also search the web once a day.</span></div>
          <div class="card step"><span class="k">4 · MATCH</span><b>Score for you</b><span class="small muted">Each role is scored on your target roles, level, country and visa sponsorship. Only roles above your minimum score show in Matches.</span></div></div>
        <div class="two">
          <div class="card" style="padding:16px 18px"><h2 style="font-size:15px">Find the top companies in a sector</h2><p class="small muted" style="margin:4px 0 10px">Claude lists them with their careers pages; we then scan each one twice a day.</p>
            <div class="chips" style="margin-bottom:10px">${d.sectors_catalog.map(sct => `<button class="chip" data-sect="${esc(sct)}">${esc(sct)}</button>`).join('')}</div>
            <div class="row gap"><input class="input grow" id="secIn" placeholder="…or any sector, e.g. 'Robotics', 'Consulting in India', 'NHS trusts'"><select class="input" id="secN" style="width:110px"><option value="100">Top 100</option><option value="50">Top 50</option><option value="25">Top 25</option></select><button class="btn primary" id="secGo">Find</button></div></div>
          <div class="card" style="padding:16px 18px"><h2 style="font-size:15px">Add a company yourself</h2><p class="small muted" style="margin:4px 0 10px">Paste its careers link (best) or just its name.</p>
            <div class="row gap"><input class="input grow" id="coIn" placeholder="https://company.com/careers  or  Company name"><button class="btn primary" id="coGo">Add</button></div><div id="coOut" class="small" style="margin-top:8px"></div>
            <div class="small muted" style="margin-top:10px">${feedsN} companies read through their job system · ${pagesN} custom careers pages crawled · 4 open job feeds</div></div></div>
        <div><div class="section-title" style="margin-bottom:8px"><h2>Finders</h2><span class="small muted">First run as soon as Claude is connected, then weekly</span></div>
          <div class="agents">${finders.map(f => `<div class="card agent"><div class="row gap"><span class="st ${f.running ? 'run' : esc(f.last_status || '')}"></span><b class="grow">${esc(f.name.replace(/^(Company|Programme) finder · /, ''))}</b><span class="tag ${f.kind === 'discover' ? 'blue' : 'green'}">${f.kind === 'discover' ? 'Top companies' : 'Programmes'}</span></div><div class="small muted">${st(f)}</div><div><button class="btn sm" data-run="${f.id}" ${f.running ? 'disabled' : ''}>Run now</button></div></div>`).join('')}</div></div>
        <div><div class="row gap" style="margin-bottom:8px"><div class="section-title grow"><h2>Companies we scan</h2></div><label class="search" style="width:280px">${ICON.search}<input id="coQ" placeholder="Search companies" value="${esc(Sources.q)}"></label></div>
          <div class="stack" style="gap:10px" id="grpList"></div></div>
        <div class="two"><div class="card list"><div class="item"><b>Open job feeds</b></div>${d.feeds.map(f => `<div class="item row gap"><span class="st ok"></span><span class="grow">${esc(f.name)}</span><span class="small muted">${esc(f.what)}</span></div>`).join('')}</div>
          <div class="card list"><div class="item"><b>Research agents (web search, daily)</b></div>${research.map(f => `<div class="item row gap"><span class="st ${f.running ? 'run' : esc(f.last_status || '')}"></span><span class="grow">${esc(f.name.replace('Research · ', ''))}</span><span class="small muted">${f.found || 0} found</span></div>`).join('')}</div></div>
      </div></div>`;
    Sources.groups();
    $('#coQ').oninput = debounce(e => { Sources.q = e.target.value; Sources.groups(); }, 200);
    $('#sRun').onclick = async () => { await post('/api/agents/run-scouts'); toast('Scanning every source now'); };
    $$('#v-sources [data-sect]').forEach(b => b.onclick = () => { $('#secIn').value = b.dataset.sect; $$('#v-sources [data-sect]').forEach(x => x.classList.toggle('on', x === b)); });
    $('#secGo').onclick = async () => { const s = $('#secIn').value.trim(); if (!s) return toast('Pick or type a sector'); const r = await post('/api/sectors', { sector: s, n: +$('#secN').value }); toast(r.started ? `Finding the top companies in ${s}…` : 'That finder is already running'); setTimeout(Sources.load, 1200); };
    $('#coGo').onclick = async () => { const v = $('#coIn').value.trim(); if (!v) return; $('#coOut').innerHTML = '<span class="spin"></span> Looking for its job system…'; const body = /^https?:|\.[a-z]{2,}\//i.test(v) ? { url: v } : { name: v };
      try { const r = await post('/api/companies', body); $('#coOut').innerHTML = r.ok ? `<span style="color:var(--good)">✓ ${r.already ? 'Already scanning' : 'Added'} ${esc(r.company.name)} — read through ${esc((SYS[r.company.ats] || [r.company.ats])[0])}</span>` : `<span style="color:var(--bad)">${esc(r.error)}</span>`; if (r.ok) { $('#coIn').value = ''; setTimeout(Sources.load, 800); } } catch (e) { $('#coOut').textContent = e.message; } };
    $$('#v-sources [data-run]').forEach(b => b.onclick = () => post(`/api/agents/${b.dataset.run}/run`).then(() => { toast('Started'); setTimeout(Sources.load, 800); }));
  },
  groups() {
    const q = Sources.q.toLowerCase();
    $('#grpList').innerHTML = Sources.d.groups.map(g => {
      const cs = g.companies.filter(c => !q || c.name.toLowerCase().includes(q)); if (!cs.length) return '';
      const counts = {}; cs.forEach(c => counts[c.ats] = (counts[c.ats] || 0) + 1);
      const jobs = cs.reduce((a, c) => a + c.jobs, 0), mt = cs.reduce((a, c) => a + c.matches, 0);
      return `<details class="card grp" ${q ? 'open' : ''}><summary><b class="grow">${esc(g.title)}</b><span class="sysbar">${Object.entries(counts).map(([k, n]) => `<i style="width:${100 * n / cs.length}%;background:${(SYS[k] || ['', '#94A3B8'])[1]}" title="${esc((SYS[k] || [k])[0])}: ${n}"></i>`).join('')}</span><span class="small muted mono" style="width:190px;text-align:right">${cs.length} cos · ${jobs.toLocaleString()} jobs · ${mt} match</span></summary>
        <div class="srcrow hd"><span>Company</span><span>Read through</span><span>Jobs</span><span>Match you</span><span>Last check</span></div>
        ${cs.sort((a, b) => b.matches - a.matches || b.jobs - a.jobs).map(c => `<div class="srcrow"><span class="row gap"><span class="st ${c.ok === 0 ? 'error' : c.ok ? 'ok' : ''}"></span>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.name)}</a>` : esc(c.name)}</span><span><span class="tag" style="color:${(SYS[c.ats] || ['', 'var(--muted)'])[1]}">${esc((SYS[c.ats] || [c.ats])[0])}</span></span><span class="mono">${c.jobs}</span><span class="mono">${c.matches}</span><span class="small muted">${c.checked ? esc(c.checked.slice(0, 16).replace('T', ' ')) + ' · ' + esc(c.detail || '') : 'next scan'}</span></div>`).join('')}</details>`;
    }).join('') || '<div class="empty">No companies match.</div>';
  },
};


// ================= ABOUT ME (career folder + Claude's understanding of you) =================
const md2html = md => {
  const inl = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  let out = '', inList = false;
  for (const line of String(md || '').split('\n')) {
    const h = line.match(/^(#{1,4})\s+(.*)/), li = line.match(/^\s*[-*]\s+(.*)/);
    if (!li && inList) { out += '</ul>'; inList = false; }
    if (h) out += `<h${Math.min(4, h[1].length + 1)}>${inl(h[2])}</h${Math.min(4, h[1].length + 1)}>`;
    else if (li) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${inl(li[1])}</li>`; }
    else if (line.trim().startsWith('>')) out += `<blockquote>${inl(line.replace(/^\s*>\s?/, ''))}</blockquote>`;
    else if (line.trim()) out += `<p>${inl(line)}</p>`;
  }
  return out + (inList ? '</ul>' : '');
};

// Choose / create the career folder. Used by the setup wizard and the About me page.
const Folder = {
  async render(el, after = () => {}) {
    const d = await api('/api/aboutme');
    const has = d.profile_dir && d.exists;
    el.innerHTML = `<div class="card" style="padding:16px 18px">
      <div class="row gap"><span class="folder-ic">${ICON.folder}</span><div class="grow"><b>${has ? 'Your career folder' : 'Choose a folder for your career'}</b>
        <div class="small muted">${has ? `<span class="mono">${esc(d.profile_dir)}</span> · ${d.files.length} document${d.files.length === 1 ? '' : 's'} Claude can read` : 'One folder, just for this. Your CV goes in it, plus anything about you: old CVs, cover letters, personal statements, transcripts, project write-ups, notes. Claude reads it and saves what it understood in a <span class="mono">career-os</span> subfolder.'}</div></div>
        ${has ? '<button class="btn sm" id="fOpen">Open</button><button class="btn sm ghost" id="fChange">Change</button>' : ''}</div>
      <div id="fPick" class="${has ? 'hidden' : ''}" style="margin-top:12px"><div class="row gap"><input class="input grow" id="fPath" value="${esc(d.profile_dir || d.suggest)}" placeholder="e.g. D:\\My career"><button class="btn" id="fBrowse">Browse…</button><button class="btn primary" id="fUse">Use this folder</button></div>
        <div class="small muted" style="margin-top:6px">It's created if it doesn't exist. Nothing leaves your computer except what Claude reads to understand you.</div><div id="fMsg" class="small" style="margin-top:4px"></div></div>
      ${has && d.files.length ? `<details style="margin-top:10px"><summary class="small muted" style="cursor:pointer">What's in it</summary><div class="small mono" style="margin-top:6px;max-height:180px;overflow:auto;display:flex;flex-direction:column;gap:2px">${d.files.map(f => `<span>${esc(f.name)} <span class="muted">${f.kb} KB</span></span>`).join('')}</div></details>` : ''}</div>`;
    const use = async () => { try { await post('/api/aboutme/folder', { path: $('#fPath', el).value }); toast('Career folder set'); await Folder.render(el, after); after(); } catch (e) { $('#fMsg', el).innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; } };
    const b = $('#fBrowse', el); if (b) b.onclick = async () => { $('#fMsg', el).textContent = 'A folder window opened on your computer (check the taskbar)…'; const r = await post('/api/aboutme/pick'); if (r.path) { $('#fPath', el).value = r.path.replace(/\//g, '\\'); $('#fMsg', el).textContent = ''; use(); } else $('#fMsg', el).textContent = r.error || 'No folder chosen.'; };
    const u = $('#fUse', el); if (u) u.onclick = use;
    const o = $('#fOpen', el); if (o) o.onclick = () => post('/api/aboutme/open').catch(e => toast(e.message));
    const c = $('#fChange', el); if (c) c.onclick = () => $('#fPick', el).classList.toggle('hidden');
    return d;
  },
};

// Claude reads the folder -> about-me.md + questions it wants to ask you (an interview).
const Understand = {
  timer: null,
  async render(el, opts = {}) {
    clearTimeout(Understand.timer);
    const d = await api('/api/aboutme');
    const job = d.job || {}, running = job.status === 'running', claude = d.claude?.available;
    const qs = d.questions || [];
    el.innerHTML = `
      <div class="card" style="padding:16px 18px"><div class="row gap"><div class="grow"><b>Claude's understanding of you</b>
        <div class="small muted">${d.md ? `Saved in your folder as <span class="mono">career-os\\about-me.md</span>. Every form answer and cover letter starts from this — you can edit it.` : 'Claude reads your folder like a friend would read your notes, then writes down who you are, your story, projects, goals and how you write. Nothing is invented: gaps become questions for you.'}</div></div>
        <button class="btn ${d.md ? '' : 'primary'}" id="uBuild" ${!d.profile_dir || !claude || running ? 'disabled' : ''}>${running ? '<span class="spin"></span> Reading…' : d.md ? 'Read my folder again' : 'Build my understanding'}</button></div>
        <div class="small" style="margin-top:8px">${!d.profile_dir ? '<span style="color:var(--warn-ink)">Choose your career folder first.</span>' : !claude ? '<span style="color:var(--warn-ink)">Connect Claude Code first — it does the reading.</span>' : job.status ? `<span style="color:${job.status === 'error' ? 'var(--bad)' : job.status === 'done' ? 'var(--good)' : 'var(--ink-2)'}">${job.status === 'running' ? 'Reading your documents — usually 2–6 minutes. You can carry on meanwhile.' : esc(job.detail || '')}</span> <span class="muted">${esc((job.at || '').slice(0, 16).replace('T', ' '))}</span>${job.status === 'error' && /sign|log ?in|auth/i.test(job.detail || '') ? ' <button class="btn sm primary" id="uFix" style="margin-left:6px">Sign in</button>' : ''}` : ''}</div></div>
      ${qs.length ? `<div class="card" style="padding:16px 18px"><b>Claude would like to ask you</b><div class="small muted">Answer in your own words — rough is fine. Your answers go into about-me.md and help Claude write like you.</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:12px">${qs.map((q, i) => `<label class="field full">${esc(q)}<textarea class="input" rows="3" data-q="${i}" placeholder="Your answer…"></textarea></label>`).join('')}</div>
        <div class="row gap" style="margin-top:12px"><div class="grow small muted" id="uQmsg"></div><button class="btn primary" id="uAns">Save my answers</button></div></div>` : ''}
      ${d.md && !opts.compact ? `<div class="card" style="padding:16px 18px"><div class="row gap"><b class="grow">about-me.md</b><button class="btn sm" id="uEdit">Edit</button></div><div class="mdview" id="uView">${md2html(d.md)}</div>
        <div class="hidden" id="uEditor"><textarea class="input mono" id="uMd" rows="24" style="width:100%;font-size:12.5px">${esc(d.md)}</textarea><div class="row gap" style="margin-top:8px"><div class="grow"></div><button class="btn" id="uCancel">Cancel</button><button class="btn primary" id="uSave">Save</button></div></div></div>`
        : d.md ? `<details class="card" style="padding:12px 18px"><summary style="cursor:pointer"><b>Read what Claude understood</b></summary><div class="mdview">${md2html(d.md)}</div></details>` : ''}`;
    const FX = $('#uFix', el); if (FX) FX.onclick = () => AIFix.open();
    const B = $('#uBuild', el); if (B) B.onclick = async () => { try { await post('/api/aboutme/build'); toast('Claude is reading your folder'); Understand.render(el, opts); } catch (e) { toast(e.message, 5000); } };
    const A = $('#uAns', el); if (A) A.onclick = async () => {
      const ans = {}; $$('[data-q]', el).forEach(t => { if (t.value.trim()) ans[qs[+t.dataset.q]] = t.value.trim(); });
      if (!Object.keys(ans).length) return toast('Write at least one answer');
      A.disabled = true; A.innerHTML = '<span class="spin"></span> ' + (claude ? 'Claude is adding them…' : 'Saving…');
      try { const r = await post('/api/aboutme/answers', { answers: ans }); toast(r.merged ? 'Added to your understanding' : 'Saved in your own words'); Understand.render(el, opts); }
      catch (e) { A.disabled = false; A.textContent = 'Save my answers'; toast(e.message, 5000); }
    };
    const E = $('#uEdit', el); if (E) { E.onclick = () => { $('#uView', el).classList.add('hidden'); $('#uEditor', el).classList.remove('hidden'); E.classList.add('hidden'); };
      $('#uCancel', el).onclick = () => Understand.render(el, opts);
      $('#uSave', el).onclick = async () => { await put('/api/aboutme', { md: $('#uMd', el).value }); toast('Saved'); Understand.render(el, opts); }; }
    if (running) Understand.timer = setTimeout(() => { if (el.isConnected) Understand.render(el, opts); }, 5000);
    return d;
  },
};

const Me = {
  async load() {
    const ob = await api('/api/onboarding'), p = ob.profile || {};
    $('#v-me').innerHTML = `<div class="main"><header class="header"><h1>About me</h1><span class="small muted" style="margin-left:8px">What Claude knows about you — and where it comes from</span><div class="grow"></div><button class="btn" id="mProfile">Edit profile & goals</button></header>
      <div class="content" style="max-width:980px">
        <div class="how" style="grid-template-columns:repeat(3,minmax(0,1fr))">
          <div class="card step"><span class="k">01</span><b>Your folder</b><span class="small muted">Your CV and documents about you live in one folder on this computer.</span></div>
          <div class="card step"><span class="k">02</span><b>Claude understands you</b><span class="small muted">It reads them, asks what it can't tell, and writes <span class="mono">about-me.md</span> there.</span></div>
          <div class="card step"><span class="k">03</span><b>Forms answered like you</b><span class="small muted">The autofill reads each page — instructions, links, consents — and answers from that understanding, never by matching labels blindly.</span></div></div>
        <div id="mFolder"></div><div id="mUnd" style="display:flex;flex-direction:column;gap:14px"></div>
        <div class="card" style="padding:14px 18px"><div class="small muted">${esc(p.full_name || '')}${p.email ? ' · ' + esc(p.email) : ''}${p.location ? ' · ' + esc(p.location) : ''} · the answers you give on real forms are kept in <span class="mono">career-os\\answers-history.md</span> so future forms stay consistent.</div></div>
      </div></div>`;
    $('#mProfile').onclick = () => Onboarding.open(true);
    await Folder.render($('#mFolder'), () => Understand.render($('#mUnd')));
    Understand.render($('#mUnd'));
  },
};


// ================= AI picker (Claude / ChatGPT / Gemini) =================
const AIPick = {
  hint(p) { return { claude: 'A terminal opens. Type <code>/login</code>, choose <b>Claude account with subscription</b> (Pro/Max) — not an API key — finish in the browser, then close the window.', codex: 'A window opens and your browser asks you to <b>Sign in with ChatGPT</b> (Plus/Pro/Team) — not an API key. Then close the window.', gemini: 'A terminal opens with Gemini. Choose <b>Login with Google</b>, finish in the browser, then type <code>/quit</code>.' }[p] || ''; },
  html(A) {
    const logo = { claude: '✳', codex: '◎', gemini: '✦' };
    return `<div class="aipick">${A.choices.map(c => `<button class="card aichoice ${c.id === A.provider ? 'on' : ''}" data-ai="${c.id}"><span class="ailogo">${logo[c.id] || '•'}</span><b>${esc(c.name)}</b><span class="small muted">${esc(c.app)} · uses ${esc(c.plan)}</span>${c.installed ? '<span class="tag green">installed</span>' : ''}</button>`).join('')}</div>`;
  },
  bind(after) { $$('[data-ai]').forEach(b => b.onclick = async () => { if (b.classList.contains('on')) return; await put('/api/ai', { provider: b.dataset.ai }); toast('AI switched — the page reloads to use its name'); setTimeout(() => location.reload(), 900); }); },
};

// ================= SETUP WIZARD (any user) =================
const STEPS = [['Your career folder & CV', 'sFolder'], ['Connect your AI', 'sClaude'], ['Claude gets to know you', 'sKnow'], ['About you', 's1'], ['Education', 's2'], ['Goals — roles & places', 's3'], ['Right to work', 's4'], ['Files & Gmail', 's5'], ['Your learning plan', 's6']];
const Onboarding = {
  step: 0, P: {}, C: {}, suggested: [], editing: false, learn: null,
  async open(editing = false) {
    Onboarding.editing = editing;
    const d = await api('/api/onboarding');
    Onboarding.P = JSON.parse(JSON.stringify(d.profile || {})); Onboarding.C = d; Onboarding.step = editing ? 3 : 0;
    Onboarding.P.goals = Onboarding.P.goals || { roles: [], countries: [], kinds: ['job', 'internship', 'graduate', 'fellowship', 'scholarship'], level: 'early' };
    Onboarding.P.work_rights = Onboarding.P.work_rights || { no_sponsorship_needed_in: [], notes: '' };
    Onboarding.P.education = Onboarding.P.education || [];
    Onboarding.secTouched = !!(Onboarding.P.goals.sectors && Onboarding.P.goals.sectors.length);
    $('#app').classList.add('hidden'); $('#onboarding').classList.remove('hidden');
    Onboarding.render();
  },
  close() { $('#onboarding').classList.add('hidden'); $('#app').classList.remove('hidden'); },
  async save() { await post('/api/onboarding/save', { profile: Onboarding.P }); },
  render() {
    const s = Onboarding.step, P = Onboarding.P;
    $('#onboarding').innerHTML = `<div class="ob"><aside>
      <div class="row gap"><div class="logo" style="width:36px;height:36px;border-radius:10px;background:var(--accent);display:grid;place-items:center"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l5-9 4 6 2-3 5 6"/></svg></div><b style="font-size:17px">Career OS</b></div>
      <div><div style="font-size:26px;font-weight:600;line-height:1.2">${Onboarding.editing ? 'Your profile & goals' : 'Set up your search'}</div><div style="color:#A7B0BC;margin-top:8px">About 10 minutes. Everything stays on this computer, and you can change any answer later.</div></div>
      <ol>${STEPS.map(([n], i) => `<li><button data-step="${i}" class="${i === s ? 'on' : i < s ? 'done' : ''}"><span class="num">${i < s ? '✓' : i + 1}</span>${esc(n)}</button></li>`).join('')}</ol>
      <div class="grow" style="flex:1"></div>
      ${Onboarding.editing ? '<button class="btn" id="obClose" style="background:transparent;color:#E8EBEF;border-color:#3A4450">Close without finishing</button>' : ''}
      <div style="font-size:12px;color:#A7B0BC;border-top:1px solid #2B3440;padding-top:16px">No API keys, no bills: the AI runs through Claude Code, signed in with your own Claude plan.</div></aside>
      <main><section class="step" id="obStep"></section><section class="card preview" id="obPrev" aria-label="What will be set up"></section></main></div>`;
    $$('#onboarding [data-step]').forEach(b => b.onclick = async () => { await Onboarding.save(); Onboarding.step = +b.dataset.step; Onboarding.render(); });
    const c = $('#obClose'); if (c) c.onclick = async () => { await Onboarding.save(); Onboarding.close(); show(VIEW); };
    Onboarding[STEPS[s][1]]();
    Onboarding.preview();
  },
  nav(nextLabel = 'Continue', canSkip = false) {
    return `<div class="row gap" style="margin-top:8px">${Onboarding.step ? '<button class="btn" id="obBack" style="height:44px">Back</button>' : ''}<div class="grow"></div>${canSkip ? '<button class="btn ghost" id="obSkip" style="height:44px">Skip</button>' : ''}<button class="btn primary" id="obNext" style="height:44px;padding:0 22px">${nextLabel}</button></div>`;
  },
  bindNav(collect = () => {}) {
    const go = async d => { await collect(); await Onboarding.save(); Onboarding.step += d; Onboarding.render(); };
    const b = $('#obBack'); if (b) b.onclick = () => go(-1);
    const k = $('#obSkip'); if (k) k.onclick = () => go(1);
    $('#obNext').onclick = () => go(1);
  },
  head(title, sub) { return `<div><div class="label" style="color:var(--accent)">Step ${Onboarding.step + 1} of ${STEPS.length}</div><h1 style="margin-top:6px">${title}</h1><p class="muted" style="margin:6px 0 0">${sub}</p></div>`; },
  field(key, label, opts = {}) { const v = key.split('.').reduce((o, k) => (o || {})[k], Onboarding.P) ?? ''; return `<label class="field ${opts.full ? 'full' : ''}">${label}<input class="input" data-k="${key}" value="${esc(v)}" ${opts.ph ? `placeholder="${esc(opts.ph)}"` : ''}>${opts.help ? `<small>${opts.help}</small>` : ''}</label>`; },
  collectFields() { $$('#obStep [data-k]').forEach(i => { const ks = i.dataset.k.split('.'); let o = Onboarding.P; ks.slice(0, -1).forEach(k => o = o[k] = o[k] || {}); o[ks.at(-1)] = i.value.trim(); }); },
  async sFolder() {
    $('#obStep').innerHTML = Onboarding.head('Your career folder', 'First, one folder that holds everything about you. Your CV is saved in it, and Claude reads it to understand you properly — so forms get answered the way <i>you</i> would, not by matching labels.') + `
      <div id="obFolder"></div>
      <div id="obCv"></div>
      <div id="cvOut"></div>` + Onboarding.nav('Continue', true);
    const cvUI = async () => {
      const d = await api('/api/aboutme');
      $('#obCv').innerHTML = `<div class="card" style="padding:16px 18px;display:flex;flex-direction:column;gap:12px"><div><b>Your CV</b><div class="small muted">Claude reads it first; forms upload it. A copy is kept in your career folder.</div></div><label class="drop" id="drop"><input type="file" id="cvFile" accept=".pdf,.docx,.txt,.md" class="hidden"><div style="font-weight:600;font-size:15px">Drop your CV here or click to choose</div><div class="muted small">${d.profile_dir ? `Saved into <span class="mono">${esc(d.profile_dir)}</span>` : 'PDF or Word · it stays on this computer'}${d.cv_path ? ` · current: <span class="mono">${esc(d.cv_path.split(/[\\/]/).pop())}</span>` : ''}</div></label>
        <div class="row gap"><input class="input grow" id="cvPath" placeholder="…or type where it is, e.g. C:\\Users\\me\\Documents\\CV.pdf" value="${esc(d.cv_path || '')}"><button class="btn" id="cvPathGo">Import</button></div>
        <details><summary class="small muted" style="cursor:pointer">…or paste the text</summary><textarea class="input" id="cvText" rows="8" style="width:100%;margin-top:8px"></textarea><button class="btn" id="cvTextGo" style="margin-top:8px">Import text</button></details></div>`;
      const f = $('#cvFile'), dr = $('#drop');
      const readFile = file => { if (!file) return; const rd = new FileReader(); rd.onload = () => run({ filename: file.name, data: rd.result }); rd.readAsDataURL(file); };
      f.onchange = () => readFile(f.files[0]);
      dr.ondragover = e => { e.preventDefault(); dr.classList.add('over'); }; dr.ondragleave = () => dr.classList.remove('over');
      dr.ondrop = e => { e.preventDefault(); dr.classList.remove('over'); readFile(e.dataTransfer.files[0]); };
      $('#cvPathGo').onclick = () => $('#cvPath').value && run({ path: $('#cvPath').value });
      $('#cvTextGo').onclick = () => $('#cvText').value && run({ text: $('#cvText').value });
    };
    const run = async body => {
      $('#cvOut').innerHTML = `<div class="card" style="padding:14px"><span class="spin"></span> ${Onboarding.C.claude?.available ? 'Claude is reading your CV (about a minute)…' : 'Reading your CV…'}</div>`;
      try { const r = await post('/api/onboarding/cv', body); Onboarding.P = { ...Onboarding.P, ...r.profile }; Onboarding.suggested = r.suggested_roles || []; Onboarding.cvClaude = r.used_claude;
        $('#cvOut').innerHTML = `<div class="card" style="padding:14px"><b style="color:var(--good)">✓ Imported${r.used_claude ? ' with Claude' : ''}.</b> ${r.facts_written ? 'Your fact sheet is written. ' : ''}The next steps are pre-filled.${Onboarding.suggested.length ? `<div class="small muted" style="margin-top:6px">Roles your CV fits: ${Onboarding.suggested.map(esc).join(', ')}</div>` : ''}${r.used_claude ? '' : '<div class="small muted" style="margin-top:6px">Only the basics were read — once Claude is connected (next step) it reads it properly.</div>'}</div>`;
        cvUI(); Onboarding.preview();
      } catch (e) { $('#cvOut').innerHTML = `<div class="card" style="padding:14px;color:var(--bad)">${esc(e.message)}</div>`; }
    };
    await Folder.render($('#obFolder'), cvUI);
    cvUI();
    Onboarding.bindNav();
  },
  async sKnow() {
    const claude = Onboarding.C.claude?.available;
    $('#obStep').innerHTML = Onboarding.head('Claude gets to know you', 'Claude reads your career folder, writes down what it understood (in the folder, so you can check it) and asks you what it couldn\u2019t tell. This is what lets it write your long answers and polish your own words later.') + `
      ${claude && !Onboarding.cvClaude && (Onboarding.C.settings || {}).cv_path ? `<div class="card" style="padding:14px 18px"><div class="row gap"><div class="grow small">Your CV was read without Claude. Let Claude read it properly to fill your profile and fact sheet.</div><button class="btn sm" id="kCv">Read my CV with Claude</button></div><div id="kCvOut" class="small" style="margin-top:6px"></div></div>` : ''}
      <div id="obUnd" style="display:flex;flex-direction:column;gap:14px"></div>` + Onboarding.nav('Continue', true);
    const k = $('#kCv'); if (k) k.onclick = async () => { k.disabled = true; $('#kCvOut').innerHTML = '<span class="spin"></span> Reading…'; try { const r = await post('/api/onboarding/cv', { path: Onboarding.C.settings.cv_path }); Onboarding.P = { ...Onboarding.P, ...r.profile }; Onboarding.suggested = r.suggested_roles || []; Onboarding.cvClaude = true; $('#kCvOut').innerHTML = '<span style="color:var(--good)">✓ Done — profile and fact sheet updated.</span>'; } catch (e) { $('#kCvOut').innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; k.disabled = false; } };
    Understand.render($('#obUnd'), { compact: true });
    Onboarding.bindNav();
  },
  s1() {
    $('#obStep').innerHTML = Onboarding.head('About you', 'Used to fill application forms. Blank fields are left for you to fill on the form — and learned once you do.') + `<div class="form">
      ${Onboarding.field('full_name', 'Full name')}${Onboarding.field('preferred_name', 'Preferred first name')}
      ${Onboarding.field('first_name', 'First (given) name(s)', { help: 'As forms should show it' })}${Onboarding.field('last_name', 'Last name / surname')}
      ${Onboarding.field('email', 'Email')}${Onboarding.field('phone', 'Phone', { ph: '+44 …' })}
      ${Onboarding.field('location', 'Location', { ph: 'City, Country' })}${Onboarding.field('country', 'Country you live in')}
      ${Onboarding.field('linkedin', 'LinkedIn URL')}${Onboarding.field('github', 'GitHub URL')}
      ${Onboarding.field('website', 'Portfolio / website')}${Onboarding.field('years_experience', 'Years of experience')}
      ${Onboarding.field('current_title', 'Current / most recent job title')}${Onboarding.field('current_company', 'Current / most recent employer')}</div>` + Onboarding.nav();
    Onboarding.bindNav(Onboarding.collectFields);
  },
  s2() {
    const E = Onboarding.P.education;
    if (!E.length) E.push({ level: '', field: '', school: '', start: '', end: '', grade: '' });
    $('#obStep').innerHTML = Onboarding.head('Education', 'Your degree decides which Learn tracks you start with (e.g. Computer Science → Maths, CS, DSA, Systems). Newest first.') +
      E.map((e, i) => `<div class="card" style="padding:16px" data-e="${i}"><div class="form">
        <label class="field">Level<input class="input" data-f="level" value="${esc(e.level)}" placeholder="e.g. Master's Degree"></label><label class="field">Subject<input class="input" data-f="field" value="${esc(e.field)}" placeholder="e.g. Computer Science"></label>
        <label class="field full">University / school<input class="input" data-f="school" value="${esc(e.school)}"></label>
        <label class="field">Start<input class="input" data-f="start" value="${esc(e.start)}" placeholder="YYYY-MM"></label><label class="field">End (or expected)<input class="input" data-f="end" value="${esc(e.end)}" placeholder="YYYY-MM"></label>
        <label class="field">Grade (optional)<input class="input" data-f="grade" value="${esc(e.grade)}"></label><div class="field" style="justify-content:flex-end">${E.length > 1 ? '<button class="btn ghost" data-rm>Remove</button>' : ''}</div></div></div>`).join('') +
      '<button class="btn" id="eAdd" style="align-self:flex-start">+ Add another qualification</button>' + Onboarding.nav();
    const collect = () => $$('#obStep [data-e]').forEach(c => { const e = E[+c.dataset.e]; $$('[data-f]', c).forEach(i => e[i.dataset.f] = i.value.trim()); });
    $('#eAdd').onclick = () => { collect(); E.push({ level: '', field: '', school: '', start: '', end: '', grade: '' }); Onboarding.s2(); };
    $$('#obStep [data-rm]').forEach(b => b.onclick = () => { collect(); E.splice(+b.closest('[data-e]').dataset.e, 1); Onboarding.s2(); });
    Onboarding.bindNav(() => { collect(); Onboarding.P.education = E.filter(e => e.school || e.field); });
  },
  chipSet(list, chosen, attr) { return `<div class="chips">${list.map(x => `<button class="chip ${chosen.includes(x) ? 'on' : ''}" ${attr}="${esc(x)}" style="height:36px;padding:0 14px;font-size:13px">${esc(x)}</button>`).join('')}</div>`; },
  async s3() {
    const G = Onboarding.P.goals, C = Onboarding.C.catalog;
    const autoSec = () => { if (Onboarding.secTouched) return; const out = []; G.roles.forEach(r => ((C.role_sectors || {})[r] || [`Top employers of ${r}`]).forEach(x => { if (!out.includes(x)) out.push(x); })); G.sectors = out.slice(0, 8); };
    if (!G.sectors || !G.sectors.length) { G.sectors = []; autoSec(); }
    const roles = [...new Set([...C.roles, ...Onboarding.suggested, ...G.roles])];
    const sectors = [...new Set([...(C.sectors || []), ...G.sectors])];
    $('#obStep').innerHTML = Onboarding.head('What are you aiming for?', 'Pick as many as you like. This decides which companies and programmes we look up, how matches are scored and which Learn tracks you get.') + `
      <div class="fgroup"><b>Target roles</b>${Onboarding.chipSet(roles, G.roles, 'data-role')}<input class="input" id="roleAdd" placeholder="Type any other role and press Enter (e.g. Robotics Engineer, Nurse, Lawyer)"></div>
      <div class="fgroup"><b>Sectors — we find the top 100 employers in each</b>${Onboarding.chipSet(sectors, G.sectors, 'data-sec')}<input class="input" id="secAdd" placeholder="Type any sector and press Enter (e.g. Robotics, NHS trusts, Consulting in India)"></div>
      <div class="fgroup"><b>Where you'd work</b>${Onboarding.chipSet(C.countries, G.countries, 'data-c')}</div>
      <div class="fgroup"><b>Kinds of opportunity</b> <span class="small muted">— graduate schemes, internships, fellowships, apprenticeships and scholarships each get a Programme finder (top 100)</span><div class="chips">${C.kinds.map(k => `<button class="chip ${G.kinds.includes(k) ? 'on' : ''}" data-kind="${k}" style="height:36px;padding:0 14px;font-size:13px">${esc(KINDS[k] || k)}</button>`).join('')}</div></div>
      <div class="form"><label class="field">Level<select class="input" id="gLevel">${[['student', 'Student / internship'], ['early', 'Early career (0–3 years)'], ['mid', 'Mid (3–7 years)'], ['senior', 'Senior (7+ years)']].map(([v, l]) => `<option value="${v}" ${G.level === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
        ${Onboarding.field('goals.salary_goal', 'Salary goal (optional)', { ph: 'amount + currency, e.g. 60,000 EUR' })}</div>` + Onboarding.nav();
    const tog = (arr, v) => arr.includes(v) ? arr.splice(arr.indexOf(v), 1) : arr.push(v);
    $$('#obStep [data-role]').forEach(b => b.onclick = () => { tog(G.roles, b.dataset.role); b.classList.toggle('on'); if (!Onboarding.secTouched) { autoSec(); $$('#obStep [data-sec]').forEach(x => x.classList.toggle('on', G.sectors.includes(x.dataset.sec))); const missing = G.sectors.filter(x => !$(`#obStep [data-sec="${CSS.escape(x)}"]`)); if (missing.length) { Onboarding.collectFields(); Onboarding.s3(); } } Onboarding.preview(); });
    $$('#obStep [data-sec]').forEach(b => b.onclick = () => { Onboarding.secTouched = true; tog(G.sectors, b.dataset.sec); b.classList.toggle('on'); Onboarding.preview(); });
    $$('#obStep [data-c]').forEach(b => b.onclick = () => { tog(G.countries, b.dataset.c); b.classList.toggle('on'); Onboarding.preview(); });
    $$('#obStep [data-kind]').forEach(b => b.onclick = () => { tog(G.kinds, b.dataset.kind); b.classList.toggle('on'); Onboarding.preview(); });
    $('#roleAdd').onkeydown = e => { if (e.key === 'Enter' && e.target.value.trim()) { G.roles.push(e.target.value.trim()); Onboarding.collectFields(); Onboarding.s3(); Onboarding.preview(); } };
    $('#secAdd').onkeydown = e => { if (e.key === 'Enter' && e.target.value.trim()) { Onboarding.secTouched = true; G.sectors.push(e.target.value.trim()); Onboarding.collectFields(); Onboarding.s3(); Onboarding.preview(); } };
    Onboarding.bindNav(() => { Onboarding.collectFields(); G.level = $('#gLevel').value; });
  },
  s4() {
    const W = Onboarding.P.work_rights, C = Onboarding.C.catalog.countries.filter(c => !['Remote', 'Europe', 'Anywhere'].includes(c));
    const needs = String(Onboarding.P.requires_sponsorship || 'Yes').toLowerCase().startsWith('y');
    $('#obStep').innerHTML = Onboarding.head('Right to work', 'So forms are answered truthfully and matches that can’t sponsor you are flagged. We go by the law — never guess on these.') + `
      <div class="fgroup"><b>Where can you work without a visa or sponsorship?</b>${Onboarding.chipSet(C, W.no_sponsorship_needed_in || [], 'data-free')}</div>
      <div class="fgroup"><b>Will you need visa sponsorship everywhere else?</b><div class="seg" style="max-width:280px">${['Yes', 'No'].map(v => `<button data-sp="${v}" class="${(needs ? 'Yes' : 'No') === v ? 'on' : ''}">${v}</button>`).join('')}</div></div>
      <div class="form">${Onboarding.field('work_rights.notes', 'Anything agents should know (optional)', { full: true, ph: 'e.g. Student visa: max 20 hours/week in term time', help: 'Research agents use this when they look for part-time work.' })}</div>` + Onboarding.nav();
    W.no_sponsorship_needed_in = W.no_sponsorship_needed_in || [];
    $$('#obStep [data-free]').forEach(b => b.onclick = () => { const a = W.no_sponsorship_needed_in, v = b.dataset.free; a.includes(v) ? a.splice(a.indexOf(v), 1) : a.push(v); b.classList.toggle('on'); });
    $$('#obStep [data-sp]').forEach(b => b.onclick = () => { Onboarding.P.requires_sponsorship = b.dataset.sp; $$('#obStep [data-sp]').forEach(x => x.classList.toggle('on', x === b)); });
    Onboarding.bindNav(Onboarding.collectFields);
  },
  async sClaude() {
    Onboarding.C = await api('/api/onboarding');
    const A = await api('/api/ai'), c = A.status;
    const step = (n, done, title, body, btn) => `<div class="row gap" style="align-items:flex-start;padding:12px 0;border-top:1px solid var(--line-2)"><span class="num" style="width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:600;flex-shrink:0;background:${done ? 'var(--good)' : 'var(--sunk)'};color:${done ? '#fff' : 'var(--ink-2)'}">${done ? '✓' : n}</span><div class="grow"><b>${title}</b><div class="small muted">${body}</div><div id="cOut${n}" class="small" style="margin-top:4px"></div></div>${btn || ''}</div>`;
    $('#obStep').innerHTML = Onboarding.head('Connect your AI', 'The AI is the brain: it reads your folder to understand you, reads each application page, writes your long answers and cover letters, runs the finders and teaches you. It runs on <b>your own subscription</b> through its official command-line app — no API key, no bills.') + `
      ${AIPick.html(A)}
      <div class="card" style="padding:16px 18px"><div class="row gap"><span class="st ${c.available ? 'ok' : 'error'}"></span><b class="grow">${c.available ? esc(c.app) + ' is installed — ' + esc(c.version) : esc(c.app) + ' is not installed yet'}</b></div>
        ${step(1, c.available, 'Install ' + esc(c.app), c.provider === 'claude' ? 'The official installer opens in a PowerShell window. Takes about a minute.' : 'Installs with npm (Node.js). If Node.js is missing, its download page opens first.', `<button class="btn sm" id="cInst" ${c.available ? 'disabled' : ''}>Install</button>`)}
        ${step(2, Onboarding.claudeOk, 'Sign in with your ' + esc(c.plan) + ' subscription', AIPick.hint(c.provider), `<button class="btn sm" id="cLogin" ${c.available ? '' : 'disabled'}>Sign in</button>`)}
        ${step(3, Onboarding.claudeOk, 'Test the connection', 'One tiny request to check everything works (uses almost nothing).', `<button class="btn sm primary" id="cTest" ${c.available ? '' : 'disabled'}>Test</button>`)}
        <div class="small muted" style="border-top:1px solid var(--line-2);padding-top:10px">Free without any AI: job-board scans, careers-page crawling, scoring, filling obvious fields, Gmail tracking. The usage meter (left rail) shows exactly what uses your plan.</div></div>` + Onboarding.nav('Continue', true);
    AIPick.bind(() => Onboarding.sClaude());
    const recheck = async () => { Onboarding.C = await api('/api/onboarding'); };
    $('#cInst').onclick = async () => { const r = await post('/api/claude/install'); $('#cOut1').innerHTML = r.manual ? esc(r.manual) : 'Installer opened in a new window. When it says Done, press <b>Sign in</b>.'; const t = setInterval(async () => { await recheck(); if (Onboarding.C.claude?.available) { clearInterval(t); if (STEPS[Onboarding.step][1] === 'sClaude') Onboarding.sClaude(); } }, 5000); };
    $('#cLogin').onclick = async () => { const r = await post('/api/claude/login'); $('#cOut2').innerHTML = r.manual ? esc(r.manual) : 'A window opened — sign in there, then press <b>Test</b>.'; };
    $('#cTest').onclick = async () => { $('#cOut3').innerHTML = '<span class="spin"></span> Testing…';
      try { const r = await post('/api/claude/test'); Onboarding.claudeOk = r.ok; $('#cOut3').innerHTML = r.ok ? '<span style="color:var(--good)">✓ Connected — it replied. Next it gets to know you.</span>' : 'Unexpected reply: ' + esc(r.reply); }
      catch (e) { Onboarding.claudeOk = false; $('#cOut3').innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; } };
    Onboarding.bindNav();
  },
  async s5() {
    Onboarding.C = await api('/api/onboarding');
    const S = Onboarding.C.settings || {};
    $('#obStep').innerHTML = Onboarding.head('Files & Gmail', 'Which files forms upload, where your books are, and (optionally) Gmail so Track updates itself.') + `
      <div class="card" style="padding:16px"><b>Files</b><div class="form" style="margin-top:10px">
        <label class="field full">CV file used for uploads<input class="input" id="oCv" value="${esc(S.cv_path || '')}" placeholder="C:\\…\\CV.pdf"></label>
        <label class="field full">Short resume (optional)<input class="input" id="oRes" value="${esc(S.resume_path || '')}"></label>
        <label class="field full">Books folder for Learn (optional)<input class="input" id="oBooks" value="${esc(S.books_dir || '')}" placeholder="e.g. D:\\books"></label></div></div>
      <div class="card" style="padding:16px"><b>Gmail (optional)</b><p class="small muted" style="margin:4px 0 10px">Google Account → Security → 2-Step Verification on → App passwords → create “Career OS”. Paste the 16 letters here. You can also do this later in Settings.</p><div class="form">
        <label class="field">Gmail address<input class="input" id="oMail" value="${esc(Onboarding.P.email || '')}"></label><label class="field">App password<input class="input" type="password" id="oPass"></label></div></div>` + Onboarding.nav();
    Onboarding.bindNav(async () => {
      const st = { cv_path: $('#oCv').value.trim(), resume_path: $('#oRes').value.trim(), books_dir: $('#oBooks').value.trim() };
      if ($('#oPass').value.trim()) st.email = { enabled: true, address: $('#oMail').value.trim(), app_password: $('#oPass').value.trim() };
      await post('/api/onboarding/save', { settings: st });
    });
  },
  async s6() {
    await Onboarding.save();
    const D = await api('/api/learn'); Onboarding.learn = D;
    const sel = new Set(D.selected);
    $('#obStep').innerHTML = Onboarding.head('Your learning plan', 'Picked from your degree and target roles. Each track runs from Foundations to research-level Frontier, with free sources and an AI teacher. Add any subject later.') + `
      <div class="card list">${D.tracks.map(t => `<label class="item row gap" style="cursor:pointer"><input type="checkbox" data-t="${esc(t.id)}" ${sel.has(t.id) ? 'checked' : ''}><b class="grow">${esc(t.title)}</b>${t.for_degree ? '<span class="tag amber">core for your degree</span>' : t.category === 'custom' ? '<span class="tag">yours</span>' : ''}<span class="small muted mono">${t.total} modules</span></label>`).join('')}</div>
      ${(Onboarding.P.goals.roles || []).filter(r => !Onboarding.C.catalog.roles.includes(r) || ['Product Manager', 'Cybersecurity'].includes(r)).length ? '<div class="small muted">Tracks for roles not in the catalog are built by Claude after you finish.</div>' : ''}` +
      Onboarding.nav(Onboarding.editing ? 'Save & rebuild my agents' : 'Finish & start my first scan');
    const b = $('#obBack'); if (b) b.onclick = () => { Onboarding.step--; Onboarding.render(); };
    $('#obNext').onclick = async () => {
      await post('/api/learn/select', { selected: $$('#obStep input:checked').map(i => i.dataset.t) });
      $('#obNext').disabled = true; $('#obNext').innerHTML = '<span class="spin"></span> Setting up…';
      const r = await post('/api/onboarding/finish');
      Onboarding.close(); toast(`All set — ${r.agents_total} agents ready. Your first scan is running now.`, 5000); boot(true);
    };
  },
  preview: debounce(async () => {
    const P = Onboarding.P, G = P.goals || {};
    let pv = { agents: [], tracks: [] }; try { await Onboarding.save(); pv = await api('/api/onboarding/preview'); } catch (e) {}
    const el = $('#obPrev'); if (!el) return;
    let am = {}; try { am = await api('/api/aboutme'); } catch (e) {}
    el.innerHTML = `<div><div class="label">What Career OS will set up</div><div class="small muted" style="margin-top:4px">Updates as you answer</div></div>
      <div><b>Career folder</b><div class="small" style="color:var(--ink-2);margin-top:6px">${am.profile_dir ? `<span class="mono">${esc(am.profile_dir)}</span><br>${am.files.length} documents · ${am.md ? '<span style="color:var(--good)">Claude understands you ✓</span>' : 'not read by Claude yet'}${am.questions?.length ? ` · ${am.questions.length} questions for you` : ''}` : '<span class="muted">Not chosen yet</span>'}</div></div>
      <div style="height:1px;background:var(--line)"></div>
      <div><b>${pv.agents.length} agents</b> <span class="small muted">· top 100 companies in ${pv.sectors?.length || 0} sectors</span><div class="small" style="color:var(--ink-2);margin-top:6px;display:flex;flex-direction:column;gap:4px">${pv.agents.slice(0, 7).map(a => `<div>${esc(a)}</div>`).join('')}${pv.agents.length > 7 ? `<div class="muted">+ ${pv.agents.length - 7} more</div>` : ''}</div></div>
      <div style="height:1px;background:var(--line)"></div>
      <div><b>Learn tracks</b><div class="chips" style="margin-top:8px">${pv.tracks.map(t => `<span class="tag ${t.core ? 'amber' : 'blue'}">${esc(t.title)}</span>`).join('') || '<span class="muted small">Add your degree and roles</span>'}</div><div class="small muted" style="margin-top:6px">Amber = core for your degree · blue = from your roles</div></div>
      <div style="height:1px;background:var(--line)"></div>
      <div class="small" style="color:var(--ink-2)">${G.countries?.length ? `Matches scored for ${esc(G.countries.join(', '))} first.` : 'Pick the places you’d work.'}</div>`;
  }, 400),
};

// ================= boot =================
async function boot(fresh = false) {
  const ob = await api('/api/onboarding');
  if (!ob.onboarded) return Onboarding.open(false);
  const p = ob.profile || {}; const ini = (p.full_name || '?').split(/\s+/).map(x => x[0]).filter(Boolean);
  $('#me').textContent = (ini[0] || '') + (ini.length > 1 ? ini.at(-1) : ''); $('#me').title = p.full_name || '';
  show(fresh ? 'apply' : ((location.hash || '#apply').slice(1) || 'apply'));
  meter(); status();
}
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (v && v !== VIEW && $('#v-' + v) && $('#onboarding').classList.contains('hidden')) show(v); });
setInterval(() => { if ($("#onboarding").classList.contains("hidden")) { status(); meter(); } }, 10000);
boot();
