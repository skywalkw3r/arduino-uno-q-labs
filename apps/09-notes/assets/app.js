// Browser side of the notes app.
//
// WebUI comes from libs/arduino.js (a thin wrapper over socket.io). Run
// scripts/fetch-webui-libs.sh apps/09-notes once to download both libs.

const ui = new WebUI();

const appEl = document.querySelector('#app');
const loginEl = document.querySelector('#login');
const loginForm = document.querySelector('#login-form');
const loginPassword = document.querySelector('#login-password');
const loginError = document.querySelector('#login-error');

const statusEl = document.querySelector('#status');
const bannerEl = document.querySelector('#banner');
const inputEl = document.querySelector('#note-input');
const saveBtn = document.querySelector('#save-btn');
const listEl = document.querySelector('#notes');
const emptyEl = document.querySelector('#empty');

ui.on_connect(() => setStatus('connected', true));
ui.on_disconnect(() => setStatus('disconnected', false));

// --- auth ----------------------------------------------------------------
// The static page is public, but the server sends no note data until the
// session authenticates. The password is kept in sessionStorage so a refresh
// re-auths silently and is forgotten when the tab closes.

ui.on_message('need_auth', () => {
  const saved = sessionStorage.getItem('notes_pw');
  if (saved) {
    ui.send_message('auth', { password: saved }); // try the remembered password
  } else {
    showLogin();
  }
});

ui.on_message('auth_ok', () => {
  loginError.hidden = true;
  showApp();
});

ui.on_message('auth_fail', () => {
  sessionStorage.removeItem('notes_pw');
  loginError.hidden = false;
  showLogin();
});

loginForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const pw = loginPassword.value;
  if (!pw) return;
  sessionStorage.setItem('notes_pw', pw);
  loginError.hidden = true;
  ui.send_message('auth', { password: pw });
});

function showLogin() {
  appEl.hidden = true;
  loginEl.hidden = false;
  loginPassword.focus();
}

function showApp() {
  loginEl.hidden = true;
  appEl.hidden = false;
}

// --- notes ---------------------------------------------------------------
// The server pushes the full list after auth and after every add/edit/delete,
// so the UI is always a straight reflection of what's stored on the board.
// Receiving a list also means we're authorised (or the app is open).
let lastNotes = [];
ui.on_message('notes', (data) => {
  showApp();
  renderBanner(data.ai_available);
  lastNotes = data.notes || [];
  renderNotes(lastNotes);
});

// --- settings (Notion sync) ----------------------------------------------
const settingsBtn = document.querySelector('#settings-btn');
const settingsPanel = document.querySelector('#settings');
const notionStatus = document.querySelector('#notion-status');
const syncToggle = document.querySelector('#sync-toggle');
const syncInterval = document.querySelector('#sync-interval');
const syncType = document.querySelector('#sync-type');
const syncNowBtn = document.querySelector('#sync-now-btn');
const syncStatus = document.querySelector('#sync-status');
const enrichToggle = document.querySelector('#enrich-toggle');

let enrichEnabled = false;              // are external place lookups allowed?
const enrichTargets = {};               // query -> result container element

settingsBtn.addEventListener('click', () => {
  const opening = settingsPanel.hidden;
  settingsPanel.hidden = !opening;
  if (opening) ui.send_message('get_settings'); // refresh on open
});

ui.on_message('settings', renderSettings);

function renderSettings(s) {
  if (s.notion_configured) {
    notionStatus.textContent = 'Connected to Notion.';
    notionStatus.className = 'settings__status settings__status--ok';
    syncToggle.disabled = false;
  } else {
    notionStatus.textContent =
      'Not configured — add a notion.txt on the board (see the app README).';
    notionStatus.className = 'settings__status';
    syncToggle.disabled = true;
  }
  syncToggle.checked = !!s.enabled;
  syncInterval.value = String(s.interval);
  syncType.value = s.item_type || 'note';
  const bits = [];
  if (s.pending != null) bits.push(`${s.pending} unsynced`);
  if (s.last_sync) bits.push(`last ${new Date(s.last_sync).toLocaleTimeString()}`);
  if (s.last_result) bits.push(s.last_result);
  syncStatus.textContent = bits.join(' · ');

  enrichEnabled = !!s.enrich_enabled;
  enrichToggle.checked = enrichEnabled;
  enrichToggle.disabled = !s.enrich_available; // no model = nothing to detect
}

function pushSettings() {
  ui.send_message('set_settings', {
    enabled: syncToggle.checked,
    interval: parseInt(syncInterval.value, 10),
    item_type: syncType.value,
    enrich_enabled: enrichToggle.checked,
  });
}
syncToggle.addEventListener('change', pushSettings);
syncInterval.addEventListener('change', pushSettings);
syncType.addEventListener('change', pushSettings);
enrichToggle.addEventListener('change', pushSettings);
syncNowBtn.addEventListener('click', () => ui.send_message('sync_now'));

// --- entity chips + place lookup -----------------------------------------
const ENTITY_ICON = { place: '📍', person: '👤', phone: '📞', email: '✉️', url: '🔗' };

function entityChips(note) {
  const ents = note.entities || [];
  if (!ents.length) return null;
  const wrap = document.createElement('div');
  wrap.className = 'note__entities';
  for (const e of ents) {
    const chip = document.createElement('span');
    chip.className = 'chip chip--' + e.type + (e.enrichable ? ' chip--enrichable' : '');
    chip.textContent = `${ENTITY_ICON[e.type] || '•'} ${e.text}`;
    if (e.enrichable) {
      chip.title = 'Look up address & phone (OpenStreetMap)';
      chip.addEventListener('click', () => lookUp(e.text, wrap));
    }
    wrap.appendChild(chip);
  }
  return wrap;
}

function lookUp(query, wrap) {
  let box = wrap.querySelector(`.enrich-result[data-q="${cssEscape(query)}"]`);
  if (!box) {
    box = document.createElement('div');
    box.className = 'enrich-result';
    box.dataset.q = query;
    wrap.appendChild(box);
  }
  if (!enrichEnabled) {
    box.textContent = 'Place lookups are off — turn on “Look up places” in ⚙ settings.';
    return;
  }
  box.textContent = `Looking up “${query}” on OpenStreetMap…`;
  enrichTargets[query] = box;
  ui.send_message('enrich', { query });
}

ui.on_message('enrich_result', (data) => {
  const box = enrichTargets[data.query];
  if (!box) return;
  if (data.disabled) {
    box.textContent = 'Place lookups are off.';
    return;
  }
  const results = data.results || [];
  if (!results.length) {
    box.textContent = `No match found for “${data.query}”.`;
    return;
  }
  const r = results[0]; // best match
  box.innerHTML = '';
  const line = document.createElement('div');
  const parts = [];
  if (r.address) parts.push(r.address);
  if (r.phone) parts.push('📞 ' + r.phone);
  if (r.website) parts.push('🔗 ' + r.website);
  line.textContent = parts.join('  ·  ');
  box.appendChild(line);
  const src = document.createElement('span');
  src.className = 'enrich-src';
  src.textContent = 'via OpenStreetMap' + (r.phone ? '' : ' · no phone listed');
  box.appendChild(src);
});

function cssEscape(s) {
  return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
}

saveBtn.addEventListener('click', save);
inputEl.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') save();
});

function save() {
  const text = inputEl.value.trim();
  if (!text) return;
  ui.send_message('new_note', { text });
  inputEl.value = '';
  inputEl.focus();
  // Optimistic placeholder so the note appears instantly; it's replaced when
  // the server pushes the real list back with the summary filled in.
  prepend({ created: 'saving…', raw: text, ai: '', pending: true });
  emptyEl.hidden = true;
}

function setStatus(text, up) {
  statusEl.textContent = text;
  statusEl.className = 'status ' + (up ? 'status--up' : 'status--down');
}

function renderBanner(aiAvailable) {
  if (aiAvailable) {
    bannerEl.hidden = true;
    return;
  }
  bannerEl.hidden = false;
  bannerEl.textContent =
    'No AI model downloaded yet — notes are saved as plain text. Download a ' +
    'model in the llm brick’s “AI model” tab to turn on summaries.';
}

function renderNotes(notes) {
  listEl.innerHTML = '';
  emptyEl.hidden = notes.length > 0;
  for (const note of notes) {
    listEl.appendChild(noteCard(note));
  }
}

function prepend(note) {
  emptyEl.hidden = true;
  listEl.prepend(noteCard(note));
}

function noteCard(note) {
  const li = document.createElement('li');
  li.className = 'note' + (note.pending ? ' note--pending' : '');

  const meta = metaDiv(note.created);
  if (note.synced) {
    const badge = document.createElement('span');
    badge.className = 'note__synced';
    badge.textContent = '✓ Notion';
    meta.appendChild(badge);
  }
  li.appendChild(meta);
  li.appendChild(rawDiv(note.raw || ''));

  const aiText = (note.ai || '').trim();
  if (note.pending) {
    li.appendChild(aiBlock('summarising on the board…', true));
  } else if (aiText) {
    li.appendChild(aiBlock(aiText, false));
  }

  const chips = entityChips(note);
  if (chips) li.appendChild(chips);

  // Edit/Delete only on real, stored notes — an optimistic card has no id yet.
  if (!note.pending && note.id != null) {
    const actions = document.createElement('div');
    actions.className = 'note__actions';
    const edit = actionButton('Edit', () => enterEditMode(li, note));
    const del = actionButton('Delete', () => deleteNote(note.id, li));
    del.classList.add('btn-danger');
    actions.append(edit, del);
    li.appendChild(actions);
  }
  return li;
}

function metaDiv(created) {
  const el = document.createElement('div');
  el.className = 'note__meta';
  el.textContent = formatDate(created);
  return el;
}

function rawDiv(text) {
  const el = document.createElement('div');
  el.className = 'note__raw';
  el.textContent = text;
  return el;
}

function actionButton(label, onClick) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'btn-small';
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}

function deleteNote(id, li) {
  if (!confirm('Delete this note?')) return;
  ui.send_message('delete_note', { id });
  li.remove(); // optimistic; the server push re-syncs everyone
  if (!listEl.children.length) emptyEl.hidden = false;
}

// Swap a note card into an editable textarea with Save / Cancel.
function enterEditMode(li, note) {
  li.className = 'note note--editing';
  li.innerHTML = '';

  const ta = document.createElement('textarea');
  ta.className = 'note__edit';
  ta.rows = 4;
  ta.value = note.raw || '';
  li.appendChild(ta);

  const actions = document.createElement('div');
  actions.className = 'note__actions';
  const save = actionButton('Save', () => {
    const text = ta.value.trim();
    if (!text) return;
    ui.send_message('edit_note', { id: note.id, text });
    // Optimistic: show the new text + "re-summarising" until the server pushes
    // back the authoritative row.
    li.className = 'note';
    li.innerHTML = '';
    li.appendChild(metaDiv(note.created));
    li.appendChild(rawDiv(text));
    li.appendChild(aiBlock('re-summarising on the board…', true));
  });
  const cancel = actionButton('Cancel', () => renderNotes(lastNotes));
  actions.append(save, cancel);
  li.appendChild(actions);

  ta.focus();
  ta.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') save.click();
    if (e.key === 'Escape') cancel.click();
  });
}

function aiBlock(text, pending) {
  const box = document.createElement('div');
  box.className = 'note__ai' + (pending ? ' note__ai--pending' : '');
  const label = document.createElement('span');
  label.className = 'note__ai-label';
  label.textContent = 'AI';
  box.appendChild(label);
  const body = document.createElement('div');
  body.className = 'note__ai-body';
  // Preserve the model's line breaks (summary line + any "- " task lines).
  body.textContent = text;
  box.appendChild(body);
  return box;
}

function formatDate(value) {
  if (!value || value === 'saving…') return value || '';
  const d = new Date(value);
  if (isNaN(d)) return value;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
