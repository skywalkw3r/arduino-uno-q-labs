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

Open **http://<board-ip>:7000**. Write a note, press **Save** (or ⌘/Ctrl+Enter).
It appears immediately; the AI summary fills in a few seconds later once the
model finishes.

## How it works

- **`web_ui`** serves the page and carries messages over a WebSocket. The
  browser sends `new_note`; the server pushes the full `notes` list back after
  every save so all connected browsers stay in sync.
- **`llm`** runs `llm.chat(note)` locally to produce the summary + tasks.
- **`dbstorage_sqlstore`** persists every note to `notes.db` on the board.

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
