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

import logging
import queue
import threading
import time
from datetime import datetime

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
        rows = db.read("notes") or []
    except Exception as exc:
        logger.warning("read failed: %s", exc)
        return []
    notes = [row_to_dict(r) for r in rows]
    notes.sort(key=lambda r: r.get("id") or 0, reverse=True)  # newest first
    return notes[:limit]


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

ui = WebUI()

pending: "queue.Queue[str]" = queue.Queue()  # note texts from the browser
refresh = threading.Event()                   # a client wants the current list


def on_connect(connection) -> None:
    # Don't touch the DB from this socket-thread callback; ask loop() to.
    refresh.set()


def on_new_note(client, data) -> None:
    text = (data or {}).get("text", "").strip()
    if text:
        pending.put(text)


ui.on_connect(on_connect)
ui.on_message("new_note", on_new_note)


def push_notes() -> None:
    ui.send_message("notes", {"notes": all_notes(), "ai_available": llm is not None})


# --------------------------------------------------------------- main loop ---

def loop() -> None:
    # 1. A newly connected browser asked for the current list.
    if refresh.is_set():
        refresh.clear()
        push_notes()

    # 2. Process one queued note per iteration (keeps sends interleaved so the
    #    UI updates as each note finishes, rather than all at once).
    try:
        raw = pending.get_nowait()
    except queue.Empty:
        time.sleep(0.1)  # idle — don't spin a core
        return

    ai_text, ok = summarise(raw)
    if not ok:
        ai_text = NO_MODEL_PLACEHOLDER

    try:
        db.store(
            "notes",
            {
                "created": datetime.now().isoformat(timespec="seconds"),
                "raw": raw,
                "ai": ai_text,
            },
        )
        logger.info("saved note (%d chars, ai=%s)", len(raw), ok)
    except Exception as exc:
        logger.error("failed to store note: %s", exc)

    push_notes()  # keep every connected browser in sync


logger.info("Notes app starting — open http://<board-ip>:7000")
App.run(user_loop=loop)
