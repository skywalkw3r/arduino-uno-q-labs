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

// The server pushes the full list on connect and after every add/edit/delete,
// so the UI is always a straight reflection of what's stored on the board.
let lastNotes = [];
ui.on_message('notes', (data) => {
  renderBanner(data.ai_available);
  lastNotes = data.notes || [];
  renderNotes(lastNotes);
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

  li.appendChild(metaDiv(note.created));
  li.appendChild(rawDiv(note.raw || ''));

  const aiText = (note.ai || '').trim();
  if (note.pending) {
    li.appendChild(aiBlock('summarising on the board…', true));
  } else if (aiText) {
    li.appendChild(aiBlock(aiText, false));
  }

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
