"""Local AI note-taking app for the UNO Q.

Type a note in the browser; a local LLM summarises it and pulls out action
items; everything is stored in SQLite on the board. No cloud, no API key — the
model runs on the Qualcomm QRB2210 via the `llm` brick.

Pipeline — all Python bricks, no Go, no server to manage:

    browser (web_ui) → queue → LLM (llm) → SQLite (dbstorage_sqlstore) → browser

Open it at http://<board-ip>:7000

Graceful degradation: the app works as a plain note-taker even before you
download an LLM model. It stores your notes and shows a banner. Once you
download a model in the `llm` brick's "AI model" tab (App Lab GUI), summaries
turn on automatically — no code change, no restart of your workflow.

Threading model: the Web UI callbacks fire on a background socket thread, so
they only *enqueue* work. All database writes, LLM calls, and data sends happen
in loop() on the main thread. One owner for the DB and the model means no locks
and no races — the same flag/queue pattern the bring-up apps use for the Bridge.
"""

import hmac
import logging
import os
import queue
import time
from datetime import datetime
from pathlib import Path

from arduino.app_utils import App, Logger
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.dbstorage_sqlstore import SQLStore

# Import the LLM brick defensively: the app should still run as a plain
# note-taker if the brick package or its model isn't available.
try:
    from arduino.app_bricks.llm import LargeLanguageModel
    _HAVE_LLM_BRICK = True
except Exception:  # pragma: no cover - only if the brick isn't installed
    LargeLanguageModel = None
    _HAVE_LLM_BRICK = False

logger = Logger("Notes", level=logging.INFO)

SYSTEM_PROMPT = (
    "You are a concise note-taking assistant. Given a raw note, reply with a "
    "one or two sentence summary. Then, if the note implies any tasks, list "
    "them as short lines starting with '- '. If there are no tasks, omit them. "
    "Do not add anything else, no preamble."
)

NO_MODEL_PLACEHOLDER = (
    "(no AI summary yet — download a model in the llm brick's 'AI model' tab, "
    "then new notes will be summarised automatically)"
)

# --- security config ------------------------------------------------------
#
# HTTPS: on by default. The web_ui brick generates a self-signed certificate on
# first run, so your browser shows a one-time "not private" warning you accept.
# Drop your own cert.pem/key.pem in a `cert/` folder to replace it. Set False
# for plain http.
USE_TLS = True

# Password: create a file `secret.txt` next to this app (one line, your
# password) or set the NOTES_PASSWORD env var to require a login. If neither
# exists the app is OPEN — anyone on the network can read and edit notes.
# The file is gitignored, so your password is never committed.
#
# Security level: this keeps unauthorized people on your LAN out of your notes.
# It's a single shared password, stored in plaintext on the board, compared in
# constant time and — with TLS on — encrypted in transit. It is not per-user
# accounts or hardened multi-tenant auth.


def _load_password() -> str | None:
    env = os.environ.get("NOTES_PASSWORD")
    if env and env.strip():
        return env.strip()
    try:
        pw = (Path(__file__).resolve().parent.parent / "secret.txt").read_text().strip()
        return pw or None
    except OSError:
        return None


PASSWORD = _load_password()

# --------------------------------------------------------------- storage ---

db = SQLStore("notes.db")

# CREATE TABLE is idempotent in spirit here: on a restart the table already
# exists, so tolerate that instead of crashing on the second run.
try:
    db.create_table(
        "notes",
        {
            "id": "INTEGER PRIMARY KEY",
            "created": "TEXT",
            "raw": "TEXT",
            "ai": "TEXT",
        },
    )
except Exception as exc:
    logger.info("notes table already exists (%s)", exc)

COLUMNS = ["id", "created", "raw", "ai"]


def row_to_dict(row) -> dict:
    """Normalise a stored row to a dict.

    SQLStore.read() may return dicts or plain tuples depending on the brick
    version, so handle both rather than assuming one.
    """
    if isinstance(row, dict):
        return {k: row.get(k) for k in COLUMNS}
    return {k: v for k, v in zip(COLUMNS, row)}


def all_notes(limit: int = 100) -> list[dict]:
    try:
        rows = db.read("notes", order_by="id DESC", limit=limit) or []
    except Exception as exc:
        logger.warning("read failed: %s", exc)
        return []
    return [row_to_dict(r) for r in rows]


# ----------------------------------------------------------------- LLM ---

def make_llm():
    """Bring up the LLM, or return None so the app degrades to plain notes.

    Construction succeeds even when the model isn't downloaded yet — the failure
    only surfaces on an actual call. So we probe with one tiny chat, and treat a
    failed probe as "no model": that keeps `ai_available` (and the UI banner)
    honest instead of claiming AI works when every summary would fall back.
    """
    if not _HAVE_LLM_BRICK:
        logger.warning("llm brick not present — running without summaries")
        return None
    try:
        model = LargeLanguageModel(system_prompt=SYSTEM_PROMPT)
        model.chat("ping")  # probe: does the model actually respond?
        logger.info("llm ready — summaries enabled")
        return model
    except Exception as exc:
        logger.warning("llm not ready (%s) — running without summaries", exc)
        return None


llm = make_llm()


def summarise(raw: str) -> tuple[str, bool]:
    """Return (ai_text, ok). ok is False when no model is available."""
    if llm is None:
        return "", False
    try:
        return llm.chat(raw).strip(), True
    except Exception as exc:
        # Most common cause: the model is registered but not downloaded yet.
        logger.warning("summary failed (%s)", exc)
        return "", False


# --------------------------------------------------------------- web UI ---

ui = WebUI(use_tls=USE_TLS)

# Operations from the browser, processed one at a time in loop(). Each is a dict:
#   {"op": "add",    "text": "..."}
#   {"op": "edit",   "id": N, "text": "..."}
#   {"op": "delete", "id": N}
# Handlers run on a socket thread and only enqueue; loop() is the sole owner of
# the DB and the model, and the only place that reads the DB.
pending: "queue.Queue[dict]" = queue.Queue()
pushes: "queue.Queue[str]" = queue.Queue()   # sids to send the current list to

# Per-session auth, keyed by socket session id (sid). A client is authed once it
# sends the right password; with no password configured the app is open and
# every session is treated as authed.
authed: "set[str]" = set()


def is_authed(sid: str) -> bool:
    return PASSWORD is None or sid in authed


def _guard(sid: str) -> bool:
    """True if the client may act; otherwise nudge it back to the login."""
    if is_authed(sid):
        return True
    ui.send_message("need_auth", {}, room=sid)
    return False


def on_connect(sid: str) -> None:
    # These callbacks fire on a socket thread — no DB access here. Sending small
    # control messages is fine; the notes list is fetched in loop() via `pushes`.
    if PASSWORD is None:
        pushes.put(sid)                              # open: send the list
    else:
        ui.send_message("need_auth", {}, room=sid)   # locked: ask for a password


def on_disconnect(sid: str) -> None:
    authed.discard(sid)


def on_auth(sid: str, data) -> None:
    if PASSWORD is None:
        return
    given = str((data or {}).get("password", ""))
    # Constant-time compare so a wrong password can't be narrowed down by timing.
    if hmac.compare_digest(given, PASSWORD):
        authed.add(sid)
        ui.send_message("auth_ok", {}, room=sid)
        pushes.put(sid)
    else:
        ui.send_message("auth_fail", {}, room=sid)


def on_new_note(sid: str, data) -> None:
    if not _guard(sid):
        return
    text = (data or {}).get("text", "").strip()
    if text:
        pending.put({"op": "add", "text": text})


def on_edit_note(sid: str, data) -> None:
    if not _guard(sid):
        return
    data = data or {}
    note_id, text = data.get("id"), (data.get("text") or "").strip()
    if note_id is not None and text:
        pending.put({"op": "edit", "id": note_id, "text": text})


def on_delete_note(sid: str, data) -> None:
    if not _guard(sid):
        return
    note_id = (data or {}).get("id")
    if note_id is not None:
        pending.put({"op": "delete", "id": note_id})


ui.on_connect(on_connect)
ui.on_disconnect(on_disconnect)
ui.on_message("auth", on_auth)
ui.on_message("new_note", on_new_note)
ui.on_message("edit_note", on_edit_note)
ui.on_message("delete_note", on_delete_note)


def _payload() -> dict:
    return {"notes": all_notes(), "ai_available": llm is not None}


def push_to(sid: str) -> None:
    ui.send_message("notes", _payload(), room=sid)


def broadcast_notes() -> None:
    # Note data goes only to authenticated sessions (or everyone when open) — an
    # unauthenticated socket never receives notes, even though it can load the
    # static page.
    if PASSWORD is None:
        ui.send_message("notes", _payload())
    else:
        for sid in list(authed):
            ui.send_message("notes", _payload(), room=sid)


# ---------------------------------------------------------------- operations ---

def do_add(text: str) -> None:
    ai_text, ok = summarise(text)
    db.store(
        "notes",
        {
            "created": datetime.now().isoformat(timespec="seconds"),
            "raw": text,
            "ai": ai_text if ok else NO_MODEL_PLACEHOLDER,
        },
    )
    logger.info("added note (%d chars, ai=%s)", len(text), ok)


def do_edit(note_id, text: str) -> None:
    # Editing the text invalidates the old summary, so re-summarise.
    ai_text, ok = summarise(text)
    # int() makes the WHERE clause injection-proof: a non-integer id raises here
    # rather than reaching the database.
    db.update(
        "notes",
        {"raw": text, "ai": ai_text if ok else NO_MODEL_PLACEHOLDER},
        f"id = {int(note_id)}",
    )
    logger.info("edited note id=%d (ai=%s)", int(note_id), ok)


def do_delete(note_id) -> None:
    db.delete("notes", f"id = {int(note_id)}")
    logger.info("deleted note id=%d", int(note_id))


OPS = {
    "add": lambda o: do_add(o["text"]),
    "edit": lambda o: do_edit(o["id"], o["text"]),
    "delete": lambda o: do_delete(o["id"]),
}


# --------------------------------------------------------------- main loop ---

def loop() -> None:
    # 1. Send the current list to any sessions that just connected or authed.
    sent_any = False
    while True:
        try:
            sid = pushes.get_nowait()
        except queue.Empty:
            break
        push_to(sid)
        sent_any = True

    # 2. Process one queued operation, then sync every authed session. One op at
    #    a time keeps the DB single-owner and lets the UI update per-op.
    try:
        op = pending.get_nowait()
    except queue.Empty:
        if not sent_any:
            time.sleep(0.1)  # idle — don't spin a core
        return

    handler = OPS.get(op.get("op"))
    if handler is None:
        logger.warning("unknown op: %s", op)
        return

    try:
        handler(op)
    except Exception as exc:
        logger.error("op %r failed: %s", op.get("op"), exc)

    broadcast_notes()


scheme = "https" if USE_TLS else "http"
logger.info(
    "Notes app starting — open %s://<board-ip>:7000  (auth: %s)",
    scheme,
    "password required" if PASSWORD else "OPEN — no password set",
)
App.run(user_loop=loop)
