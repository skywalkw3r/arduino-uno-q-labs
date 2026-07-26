// Browser side of the notes app.
//
// WebUI comes from libs/arduino.js (a thin wrapper over socket.io). Run
// scripts/fetch-webui-libs.sh apps/09-notes once to download both libs.

const ui = new WebUI();

const statusEl = document.querySelector('#status');
const bannerEl = document.querySelector('#banner');
const inputEl = document.querySelector('#note-input');
const saveBtn = document.querySelector('#save-btn');
const listEl = document.querySelector('#notes');
const emptyEl = document.querySelector('#empty');

ui.on_connect(() => setStatus('connected', true));
ui.on_disconnect(() => setStatus('disconnected', false));

// The server pushes the full list on connect and after every save, so the UI
// is always a straight reflection of what's stored on the board.
ui.on_message('notes', (data) => {
  renderBanner(data.ai_available);
  renderNotes(data.notes || []);
});

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

  const meta = document.createElement('div');
  meta.className = 'note__meta';
  meta.textContent = formatDate(note.created);
  li.appendChild(meta);

  const raw = document.createElement('div');
  raw.className = 'note__raw';
  raw.textContent = note.raw || '';
  li.appendChild(raw);

  const aiText = (note.ai || '').trim();
  if (note.pending) {
    li.appendChild(aiBlock('summarising on the board…', true));
  } else if (aiText) {
    li.appendChild(aiBlock(aiText, false));
  }
  return li;
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
