// Career OS form helper - injected into every frame of the autofill browser.
// It reads fields, fills what Python decided, highlights them, and NEVER clicks submit.
(() => {
  if (window.__careeros) return;
  const C = {};
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const send = obj => { try { window.__careeros_send && window.__careeros_send(JSON.stringify(obj)); } catch (e) {} };

  function cleanText(node) {
    if (!node) return '';
    const cl = node.cloneNode(true);
    cl.querySelectorAll('select, option, textarea, input, button, script, style, svg, [aria-hidden="true"]').forEach(n => n.remove());
    return norm(cl.innerText || cl.textContent || '');
  }

  function visible(el) {
    if (el.type === 'file') return true;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') return false;
    return r.width > 0 && r.height > 0 || el.getClientRects().length > 0;
  }

  function labelFor(el) {
    let t = '';
    const lb = el.getAttribute('aria-labelledby');
    if (lb) t = lb.split(/\s+/).map(id => cleanText(document.getElementById(id))).join(' ');
    if (!t && el.id) {
      try { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t = cleanText(l); } catch (e) {}
    }
    if (!t) { const l = el.closest('label'); if (l) t = cleanText(l); }
    if (!t) t = el.getAttribute('aria-label') || '';
    if (!t) {
      let p = el.parentElement, depth = 0;
      while (p && depth < 4 && !t) {
        const lab = p.querySelector('label, legend, .application-label, [class*="label" i], [class*="question" i]');
        if (lab && !lab.contains(el)) t = cleanText(lab);
        p = p.parentElement; depth++;
      }
    }
    if (!t) t = el.getAttribute('placeholder') || el.getAttribute('name') || el.id || '';
    return norm(t).slice(0, 300);
  }

  function groupLabel(inputs) {
    const first = inputs[0];
    const fs = first.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg) return cleanText(lg).slice(0, 300); }
    const lb = first.closest('[role="radiogroup"], [role="group"]');
    if (lb) {
      const al = lb.getAttribute('aria-labelledby');
      if (al) return norm(al.split(/\s+/).map(id => cleanText(document.getElementById(id))).join(' ')).slice(0, 300);
      if (lb.getAttribute('aria-label')) return lb.getAttribute('aria-label');
    }
    const optTexts = inputs.map(i => optionLabel(i)).filter(Boolean);
    let p = first.parentElement;
    for (let d = 0; p && d < 7; d++, p = p.parentElement) {
      const contained = inputs.every(i => p.contains(i));
      if (!contained) continue;
      let t = cleanText(p);
      optTexts.forEach(o => { t = t.replace(o, ' '); });
      t = norm(t);
      if (t.length > 2) return t.slice(0, 300);
    }
    return first.name || '';
  }

  function optionLabel(inp) {
    let t = '';
    if (inp.id) { try { const l = document.querySelector(`label[for="${CSS.escape(inp.id)}"]`); if (l) t = cleanText(l); } catch (e) {} }
    if (!t) { const l = inp.closest('label'); if (l) t = cleanText(l); }
    if (!t) t = inp.getAttribute('aria-label') || inp.value || '';
    return norm(t);
  }

  function helpFor(el, label) {
    let t = '';
    const db = el.getAttribute('aria-describedby');
    if (db) t = db.split(/\s+/).map(id => cleanText(document.getElementById(id))).join(' ');
    if (!t) {
      let box = el.closest('fieldset, [class*="question" i], [class*="field" i], [class*="form-group" i], [role="group"], li');
      if (!box || cleanText(box).length > 900) box = el.parentElement && el.parentElement.parentElement;
      if (box) { t = cleanText(box); if (label) t = t.replace(label.replace(/\s*\*\s*$/, ''), ' '); }
    }
    t = norm(t);
    return t.length > 400 ? t.slice(0, 400) : t;
  }

  C.pageInfo = () => {
    const links = []; const seen = new Set();
    for (const a of document.querySelectorAll('a[href]')) {
      const tx = norm(a.innerText || a.textContent || ''); const h = a.href;
      if (!tx || tx.length > 90 || !/^https?:/.test(h) || seen.has(h)) continue;
      seen.add(h); links.push({ text: tx, href: h }); if (links.length >= 80) break;
    }
    return { title: document.title, url: location.href, text: norm(document.body ? document.body.innerText : '').slice(0, 14000), links };
  };

  function kindOf(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return 'textarea';
    if (tag === 'select') return 'select';
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete') === 'list' || /select__input/.test(el.className || '')) return 'combobox';
    if (['radio', 'checkbox', 'file', 'password', 'date', 'number', 'email', 'tel', 'url'].includes(type)) return type === 'email' || type === 'tel' || type === 'url' ? 'text' : type;
    if (el.isContentEditable) return 'textarea';
    return 'text';
  }

  C.collect = () => {
    const els = Array.from(document.querySelectorAll('input, textarea, select, [contenteditable="true"]'));
    const out = []; const seenRadio = new Set(); let idx = 0;
    for (const el of els) {
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (['hidden', 'submit', 'button', 'image', 'reset', 'search'].includes(type)) continue;
      if (el.disabled || el.readOnly && type !== 'file') continue;
      if (el.closest('#careeros-panel-host')) continue;
      if (!visible(el)) continue;
      const kind = kindOf(el);
      if (kind === 'radio') {
        const name = el.name || '';
        if (!name || seenRadio.has(name)) continue;
        seenRadio.add(name);
        const group = Array.from(document.querySelectorAll(`input[type="radio"][name="${CSS.escape(name)}"]`));
        const id = 'r' + (idx++);
        group.forEach((g, i) => { g.dataset.careerosIdx = id; g.dataset.careerosOpt = i; });
        const checked = group.find(g => g.checked);
        const gl = groupLabel(group);
        out.push({ idx: id, kind, label: gl, help: helpFor(group[0], gl), options: group.map(optionLabel), value: checked ? optionLabel(checked) : '',
                   required: group.some(g => g.required), filled: el.dataset.careerosFilled || '', source: el.dataset.careerosSource || '' });
        continue;
      }
      const id = el.dataset.careerosIdx || ('f' + (idx++));
      el.dataset.careerosIdx = id;
      const label = labelFor(el);
      const rec = { idx: id, kind, label, help: helpFor(el, label), name: el.name || '', elid: el.id || '', required: !!el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label),
                    filled: el.dataset.careerosFilled || '', source: el.dataset.careerosSource || '' };
      if (kind === 'select') {
        rec.options = Array.from(el.options).map(o => norm(o.text));
        rec.value = el.selectedIndex >= 0 && el.value ? norm(el.options[el.selectedIndex].text) : '';
        rec.multiple = el.multiple;
      } else if (kind === 'checkbox') {
        rec.value = el.checked ? 'checked' : '';
      } else if (kind === 'file') {
        rec.value = el.files && el.files.length ? el.files[0].name : '';
        rec.accept = el.getAttribute('accept') || '';
      } else if (el.isContentEditable) {
        rec.value = norm(el.innerText);
      } else {
        rec.value = el.value || '';
      }
      out.push(rec);
    }
    return out;
  };

  function setNative(el, v) {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const d = Object.getOwnPropertyDescriptor(proto, 'value');
    el.focus();
    if (d && d.set) d.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  }

  const COLORS = { learned: '#1a7f37', profile: '#1a7f37', decline: '#1a7f37', ai: '#bf8700', none: '#cf222e', needs: '#cf222e' };
  function note(el, text, source) {
    const host = (el.closest('label') && el.type === 'radio') ? el.closest('fieldset, [role="radiogroup"]') || el.closest('label') : el;
    const nx = host.nextElementSibling;
    if (nx && nx.classList && nx.classList.contains('careeros-note')) nx.remove();
    if (!text) return;
    const d = document.createElement('div');
    d.className = 'careeros-note';
    d.style.cssText = `font:12px/1.4 system-ui,Segoe UI,sans-serif;margin:4px 0 8px;padding:5px 8px;border-radius:6px;background:${source === 'ai' ? '#fff4d6' : '#fdecea'};color:${source === 'ai' ? '#7a4500' : '#a1170e'};`;
    d.textContent = (source === 'ai' ? 'Claude: ' : 'You: ') + text;
    host.insertAdjacentElement('afterend', d);
  }
  function mark(el, source) {
    el.style.outline = `2px solid ${COLORS[source] || '#888'}`;
    el.style.outlineOffset = '1px';
    el.title = source === 'ai' ? 'Career OS: drafted by Claude - please read it' :
               source === 'none' ? 'Career OS: I did not know this one - fill it and I will learn it' : 'Career OS: filled from your answers';
  }

  // plan: [{idx, kind, value, option, source}]  (option = index for select/radio)
  C.apply = plan => {
    let n = 0;
    for (const p of plan) {
      const els = document.querySelectorAll(`[data-careeros-idx="${p.idx}"]`);
      if (!els.length) continue;
      const el = els[0];
      try {
        if (p.source === 'none' || p.source === 'needs') { if (p.clear && el.dataset.careerosFilled) { setNative(el, ''); delete el.dataset.careerosFilled; el.dataset.careerosSource = 'none'; } if (p.kind !== 'radio') mark(el, 'none'); else els.forEach(e => mark(e.closest('label') || e, 'none')); if (p.note) note(el, p.note, 'needs'); continue; }
        if (p.force && p.kind !== 'radio' && p.kind !== 'select' && p.kind !== 'checkbox') { setNative(el, p.value); el.dataset.careerosFilled = p.value; el.dataset.careerosSource = p.source; mark(el, p.source); if (p.note) note(el, p.note, 'ai'); n++; continue; }
        if (p.kind === 'radio') {
          const target = Array.from(els).find(e => String(e.dataset.careerosOpt) === String(p.option));
          if (target && (p.force || !Array.from(els).some(e => e.checked))) { target.click(); }
          els.forEach(e => { e.dataset.careerosFilled = p.value; e.dataset.careerosSource = p.source; });
          mark(target && (target.closest('label') || target) || el, p.source); n++; continue;
        }
        if (p.kind === 'select') {
          if (el.value && el.selectedIndex > 0 && !el.dataset.careerosFilled) continue;
          el.selectedIndex = p.option;
          setNative(el, el.options[p.option].value);
        } else if (p.kind === 'checkbox') {
          const want = /^(checked|yes|true|tick|on)$/i.test(p.value);
          if (el.checked !== want) el.click();
        } else if (el.isContentEditable) {
          if (norm(el.innerText) && !el.dataset.careerosFilled) continue;
          el.focus(); el.innerText = p.value; el.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
          if (el.value && !el.dataset.careerosFilled) continue;  // never overwrite what you typed
          setNative(el, p.value);
        }
        el.dataset.careerosFilled = p.value; el.dataset.careerosSource = p.source;
        mark(el, p.source); if (p.note) note(el, p.note, p.source === 'ai' ? 'ai' : 'needs'); n++;
      } catch (e) {}
    }
    return n;
  };

  C.markFilled = (idx, value, source) => {
    document.querySelectorAll(`[data-careeros-idx="${idx}"]`).forEach(el => {
      el.dataset.careerosFilled = value; el.dataset.careerosSource = source; mark(el, source);
    });
  };

  C.snapshot = () => C.collect();
  let lastFocus = null;
  document.addEventListener('focusin', e => {
    const el = e.target && e.target.closest && e.target.closest('[data-careeros-idx]');
    if (el) lastFocus = { idx: el.dataset.careerosIdx, at: Date.now(), value: (el.value || el.innerText || '').slice(0, 1500) };
  }, true);
  C.lastFocus = () => lastFocus;
  C.errorsShown = () => Array.from(document.querySelectorAll('[class*="error" i], [role="alert"], [aria-invalid="true"]'))
    .filter(e => e.getAttribute('aria-invalid') === 'true' || (visible(e) && norm(e.innerText || '').length > 3 && norm(e.innerText || '').length < 300)).length;

  // ---------- floating panel (top frame only) ----------
  const escH = x => String(x || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function panel() {
    if (window.top !== window || document.getElementById('careeros-panel-host')) return;
    const host = document.createElement('div');
    host.id = 'careeros-panel-host';
    host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
    const sh = host.attachShadow({ mode: 'open' });
    sh.innerHTML = `<style>
      .b{font:13px/1.45 system-ui,Segoe UI,sans-serif;background:#0f1720;color:#e6edf3;border-radius:14px;padding:14px 16px;width:360px;max-height:70vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.4)}
      .t{font-weight:700;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:14px}
      .s{color:#c9d3dd;margin-bottom:10px;white-space:pre-wrap}
      .u{background:#17212b;border-radius:10px;padding:10px 12px;margin-bottom:10px;color:#dbe4ec}
      .u b{display:block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#8fa1b3;margin-bottom:4px}
      .w{background:#3a2a0c;color:#ffd58a;border-radius:10px;padding:9px 12px;margin-bottom:8px}
      .w a{color:#ffe7b3}
      .k{display:flex;gap:10px;font-size:11px;margin-bottom:10px;color:#9aa7b4}
      .k i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
      button{font:600 12px system-ui;border:0;border-radius:8px;padding:8px 10px;margin:0 6px 6px 0;cursor:pointer;background:#2b3743;color:#e6edf3}
      button.p{background:#3b6cf6;color:#fff} button.g{background:#1f6f3f;color:#fff} .x{background:none;color:#9aa7b4;padding:0 4px;margin:0}
      .min .s,.min .k,.min .r,.min .u,.min .ws,.min .c{display:none}
      .b.chat{width:420px}
      .c{display:none;border-top:1px solid #243140;margin-top:4px;padding-top:10px}
      .chat .c{display:block}
      .ml{display:flex;flex-direction:column;gap:8px;max-height:38vh;overflow:auto;margin-bottom:8px}
      .m{padding:8px 10px;border-radius:10px;white-space:pre-wrap;word-wrap:break-word}
      .m.me{background:#26344a;align-self:flex-end;max-width:85%}
      .m.ai{background:#17212b;color:#dbe4ec}
      .m.ai b{color:#fff}
      .m .ins{display:block;margin-top:6px;background:#bf8700;color:#111}
      .chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
      .chips button{background:#17212b;color:#c9d3dd;font-weight:500;padding:5px 9px;margin:0;border:1px solid #2b3743}
      .row{display:flex;gap:6px;align-items:flex-end}
      textarea{flex:1;resize:none;font:13px/1.4 system-ui,Segoe UI,sans-serif;background:#0b1118;color:#e6edf3;border:1px solid #2b3743;border-radius:8px;padding:8px;min-height:38px;max-height:120px}
      .row button{margin:0}
      .hint{font-size:11px;color:#8fa1b3;margin-top:6px} .spin{display:inline-block;width:10px;height:10px;border:2px solid #3b4a58;border-top-color:#8fb3ff;border-radius:50%;animation:s .8s linear infinite;margin-right:6px;vertical-align:-1px}@keyframes s{to{transform:rotate(360deg)}}
    </style>
    <div class="b" id="b"><div class="t"><span>Career OS</span><button class="x" id="x" title="Minimise">–</button></div>
    <div class="s" id="s">Reading the page…</div><div id="u"></div><div class="ws" id="ws"></div>
    <div class="k"><span><i style="background:#1a7f37"></i>yours</span><span><i style="background:#bf8700"></i>Claude wrote</span><span><i style="background:#cf222e"></i>needs you</span></div>
    <div class="r"><button class="p" id="fill">Read & fill this page</button><button id="polish">Polish my text</button><button class="g hidden" id="consent" style="display:none">Tick acknowledgements</button><button id="undo" style="display:none">Undo polish</button><button id="learn">Save my answers</button><button id="done">I submitted it</button><button id="ask">💬 Ask Claude</button></div>
    <div class="c" id="c"><div class="chips" id="chips"><button data-q="What does this page want from me? Anything I might miss?">What does this page want?</button><button data-q="Help me answer the question I'm on - write it in my voice.">Help with this question</button><button data-q="Is this role a good fit for me? Be honest.">Is this a good fit?</button><button data-q="Tell me about this company in 5 lines.">About this company</button></div>
    <div class="ml" id="ml"></div>
    <div class="row"><textarea id="q" rows="2" placeholder="Ask anything about this page, the role or your answers…"></textarea><button class="p" id="send">Send</button></div>
    <div class="hint">Claude sees this page and your About me. Click into a question first to get help with it. It never submits or ticks anything.</div></div></div>`;
    document.documentElement.appendChild(host);
    const $ = id => sh.getElementById(id);
    $('fill').onclick = () => send({ type: 'fill' });
    $('polish').onclick = () => send({ type: 'polish' });
    $('consent').onclick = () => send({ type: 'consents' });
    $('undo').onclick = () => send({ type: 'undo_polish' });
    $('learn').onclick = () => send({ type: 'learn', fields: C.snapshot() });
    $('done').onclick = () => send({ type: 'submitted', fields: C.snapshot() });
    $('x').onclick = () => $('b').classList.toggle('min');
    $('ask').onclick = () => { $('b').classList.toggle('chat'); $('b').classList.remove('min'); if ($('b').classList.contains('chat')) $('q').focus(); };
    const ask = text => {
      text = (text || '').trim(); if (!text) return;
      addMsg('me', text); $('q').value = '';
      thinking = document.createElement('div'); thinking.className = 'm ai'; thinking.innerHTML = '<span class="spin"></span>Thinking…'; $('ml').appendChild(thinking); $('ml').scrollTop = 1e9;
      send({ type: 'chat', text });
    };
    let thinking = null;
    const addMsg = (who, text, fills) => {
      const d = document.createElement('div'); d.className = 'm ' + who;
      d.innerHTML = who === 'ai' ? escH(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>') : escH(text);
      (fills || []).forEach(f => { const q = document.createElement('div'); q.style.cssText = 'margin-top:8px;padding:8px 10px;border-left:3px solid #bf8700;background:#0b1118;border-radius:6px;white-space:pre-wrap;max-height:220px;overflow:auto'; q.textContent = f.value; d.appendChild(q); const b = document.createElement('button'); b.className = 'ins'; b.textContent = `Insert into “${(f.label || 'this field').slice(0, 50)}”`; b.onclick = () => { send({ type: 'chat_insert', id: f.id, value: f.value }); b.textContent = 'Inserted ✓ (amber — check it)'; b.disabled = true; }; d.appendChild(b); });
      $('ml').appendChild(d); $('ml').scrollTop = 1e9;
    };
    C._chat = (text, fills) => { if (thinking) { thinking.remove(); thinking = null; } addMsg('ai', text, fills); };
    $('send').onclick = () => ask($('q').value);
    ['keydown', 'keyup', 'keypress'].forEach(ev => $('q').addEventListener(ev, e => e.stopPropagation()));
    $('q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask($('q').value); } });
    sh.querySelectorAll('#chips button').forEach(b => b.onclick = () => ask(b.dataset.q));
    C._status = t => { $('s').innerHTML = t.startsWith('…') ? '<span class="spin"></span>' + escH(t.slice(1)) : escH(t); };
    C._info = d => {
      $('u').innerHTML = d.understanding ? `<div class="u"><b>What this page wants</b>${escH(d.understanding)}</div>` : '';
      $('ws').innerHTML = (d.warnings || []).map(w => `<div class="w">⚠ ${escH(w)}</div>`).join('') +
        (d.opened || []).map(o => `<div class="w">↗ Opened: <a href="${escH(o.url)}" target="_blank">${escH(o.why || o.url)}</a></div>`).join('');
      if ((d.consentList || []).length) $('ws').innerHTML += `<div class="u"><b>Acknowledgements — your call</b>${d.consentList.map(c => `<div>☐ ${escH(c)}</div>`).join('')}<div style="color:#8fa1b3;margin-top:4px">Nothing is ticked until you press the green button.</div></div>`;
      $('consent').style.display = d.consents ? '' : 'none';
      if (d.consents) $('consent').textContent = `Tick ${d.consents} acknowledgement${d.consents > 1 ? 's' : ''}`;
      $('undo').style.display = d.canUndo ? '' : 'none';
    };
  }
  C.status = t => { panel(); if (C._status) C._status(t); };
  C.chat = (text, fills) => { panel(); if (C._chat) C._chat(text, fills); };
  C.info = d => { panel(); if (C._info) C._info(d); };
  C.setValue = (idx, value, source, noteText) => {
    const el = document.querySelector(`[data-careeros-idx="${idx}"]`); if (!el) return false;
    if (el.isContentEditable) { el.innerText = value; el.dispatchEvent(new Event('input', { bubbles: true })); } else setNative(el, value);
    el.dataset.careerosFilled = value; el.dataset.careerosSource = source; mark(el, source); note(el, noteText || '', source === 'ai' ? 'ai' : 'needs'); return true;
  };

  // detect you clicking a real submit button (we never click it ourselves)
  document.addEventListener('click', e => {
    const b = e.target && e.target.closest && e.target.closest('button, input[type="submit"], [role="button"], a');
    if (!b || b.closest('#careeros-panel-host')) return;
    const t = norm(b.innerText || b.value || b.getAttribute('aria-label') || '').toLowerCase();
    // only a real final button counts - never "Apply" / "Apply now", which just opens the form
    if (!/^(submit|send application|submit application|submit my application|finish and submit|complete application)\b/.test(t) || /linkedin|indeed|autofill|with |google|save for later|resume|cv|draft/.test(t)) return;
    const fields = C.snapshot();
    if (fields.filter(f => f.value).length < 3) return;
    send({ type: 'submit_click', text: t, fields });  // Career OS then checks whether the site accepted it
    send({ type: 'submit_click', text: t, fields });
  }, true);

  window.__careeros = C;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel); else panel();
})();
