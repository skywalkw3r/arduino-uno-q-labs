# 09 — Notes

A local AI note-taking app. Type a note in the browser; a local LLM on the
QRB2210 summarises it and pulls out action items; everything is stored in SQLite
on the board. **No cloud, no API key** — the model runs on the device.

This is the first *application* in the repo rather than a bring-up test — it
builds on everything the earlier apps verified (the `web_ui` brick from 06, plus
`llm` and `dbstorage_sqlstore`).

```
browser (web_ui) → queue → LLM (llm) → SQLite (dbstorage_sqlstore) → browser
```

## One-time setup

Fetch the two Web UI libraries (gitignored — third-party):

```bash
./scripts/fetch-webui-libs.sh apps/09-notes
```

Then, to get AI summaries, download a model once in the App Lab GUI: open this
app → the `llm` brick → **AI model** tab → download **Gemma 3 1B** (or Qwen
0.8B). See [08-llm-bench](../08-llm-bench) for why that step is GUI-only on CLI
0.12.1.

**You can skip the model for now** — the app runs as a plain note-taker without
it and shows a banner. Summaries switch on automatically once a model is present.

## Run it

```bash
./scripts/app.sh start apps/09-notes
```

Open **https://<board-ip>:7000** (note **https** — see below). Write a note,
press **Save** (or ⌘/Ctrl+Enter). It appears immediately; the AI summary fills
in a few seconds later once the model finishes. Edit/Delete buttons sit on each
saved note (editing re-summarises).

## Security: HTTPS + optional password

Both are controlled at the top of `python/main.py`.

**HTTPS is on by default** (`USE_TLS = True`). The `web_ui` brick generates a
self-signed certificate on first run, so your browser shows a one-time
"connection not private" warning — accept it to proceed. To use your own
certificate, drop `cert.pem` and `key.pem` in a `cert/` folder in the app. Set
`USE_TLS = False` for plain http.

**Password is opt-in.** Create a one-line file `secret.txt` next to the app (or
set the `NOTES_PASSWORD` env var):

```bash
printf 'your-password' > apps/09-notes/secret.txt   # gitignored, never committed
./scripts/app.sh stop apps/09-notes && ./scripts/app.sh start apps/09-notes
```

With no `secret.txt`, the app is **open** — anyone on your network can read and
edit notes. With one, the browser shows a login and the server sends **no note
data** until the session authenticates.

How the gate works: the static page is public (it holds no secrets), but every
note payload and every add/edit/delete is refused unless that socket session has
sent the right password. The check is constant-time, and with HTTPS on the
password is encrypted in transit. Honest scope: this is one shared password in
plaintext on the board — enough to keep unauthorized people on your LAN out of
your notes, **not** per-user accounts or hardened multi-tenant auth.

## Notion sync (optional)

Push notes to a Notion database on a schedule. Off until you configure it.

**The token alone grants no access.** Notion integrations start with access to
nothing — you must *connect* each database to the integration, like sharing with
a person. Two steps:

1. **Create an integration** at [notion.so/my-integrations](https://www.notion.so/my-integrations)
   → copy the Internal Integration Secret (`ntn_…`).
2. **Connect it to your database**: open the database in Notion → **•••**
   (top-right) → **Connections** → search your integration → confirm. *Without
   this every API call returns `object_not_found`, even with a valid token.*

Then create `apps/09-notes/notion.txt` (gitignored, never committed):

```
token=ntn_your_secret
database=your_database_id
```

The **database id** is the 32-hex string in the database URL *before* `?v=`
(the `?v=` part is a view, not the database). A full-page database and its
wrapping page can have different ids — use the one with `?v=`.

Restart the app, then open the **⚙ settings** menu: toggle sync on, pick an
interval (5/10/30/60 min), choose **Note** or **Reminder** (sets the title
prefix), and **Sync now** for an immediate push. Each note becomes a page in
your database — only the **title property** is set, so it works with *any*
database schema (the app auto-detects the title property's name). A ✓ Notion
badge marks synced notes; editing a note re-syncs it.

## Context detection & place lookups

Notes are scanned for entities and shown as chips: phones/emails/URLs (regex) and
**places** (a proper-noun scan of your note, confirmed by the local LLM). The
name always comes from your note's own text — the model only says "yes, that's a
place" — so it's robust to a small model's noisy output.

Tap a 📍 place chip to look up its **address and phone** via OpenStreetMap
(Nominatim). This is **off by default** and per-tap: only that place name leaves
the device (never the note), and only when you tap. Turn it on under **⚙ →
Context lookups**. Address is reliable; phone is present only when OSM has it.

Design note: the local 0.8B model must never *produce* a fact — it would
hallucinate addresses. So facts come from the lookup API; the model is used only
for language (spotting that a place is mentioned). See the multi-agent design
exploration that shaped this.

## How it works

- **`web_ui`** serves the page and carries messages over a WebSocket. The
  browser sends `new_note` / `edit_note` / `delete_note`; the server pushes the
  `notes` list back to authenticated sessions after every change.
- **`llm`** runs `llm.chat(note)` locally to produce the summary + tasks.
- **`dbstorage_sqlstore`** persists notes to `notes.db`; edit/delete use its
  `update()` / `delete()` methods.
- **`webui.js`** is a tiny local wrapper (not the vendored `arduino.js`) that
  connects socket.io to the page's own origin, so it works over both http and
  https.

### The threading rule

Web UI callbacks fire on a background socket thread, so they only **enqueue**
work. All database writes, LLM calls, and data sends happen in `loop()` on the
main thread — one owner for the DB and the model, so no locks and no races. It's
the same flag/queue pattern the bring-up apps use for the Bridge.

### Graceful degradation

Every LLM touch is wrapped so a missing or still-downloading model can't crash
the app — it stores the note and shows a placeholder instead. The app is useful
on day one and gets smarter when you add the model.

## Extending it

**Voice notes (dictation).** Add the `asr` brick and a USB mic, then feed the
transcript into the same pipeline:

```yaml
# app.yaml
bricks:
  - arduino:web_ui
  - arduino:llm
  - arduino:dbstorage_sqlstore
  - arduino:asr          # add this
```

```python
from arduino.app_bricks.asr import AutomaticSpeechRecognition
asr = AutomaticSpeechRecognition()

# in a handler or loop, capture speech and enqueue it just like a typed note:
with asr.transcribe_stream(duration=5) as stream:
    for chunk in stream:
        if chunk.type == "full_text":
            pending.put(chunk.data)
```

**Tags.** Ask the model for topic tags in `SYSTEM_PROMPT` and store them in a new
column, or add a `tags` table and a filter UI.

**Search.** `db.read("notes")` + a text filter is enough to start. Semantic
search (embed each note, vector-compare) is the bigger version — that's where a
model with embeddings support would come in.

## If it fails

- **Page won't load** — check the port (7000) and that the app is running
  (`./scripts/app.sh status`). Run `./scripts/fetch-webui-libs.sh apps/09-notes`
  if `libs/` is missing.
- **Notes save but never get a summary** — no model downloaded. The banner says
  so; do the GUI step above. Confirm with `arduino-app-cli model list`.
- **Page connects but stays empty after saving** — check the app log
  (`./scripts/app.sh logs apps/09-notes`) for a store/read error.
