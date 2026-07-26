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

# --- Notion sync config ---------------------------------------------------
#
# Create apps/09-notes/notion.txt (gitignored) with:
#     token=ntn_...
#     database=<your database id>
# Optional: title=<title property name> (auto-detected otherwise),
#           version=<Notion API version>.
# Absent -> Notion sync is unavailable and the app runs unchanged.

NOTION_ENDPOINT = "https://api.notion.com/v1"
NOTION_TIMEOUT = 10           # seconds per request
MAX_SYNC_PER_CYCLE = 5        # notes pushed per sync pass (bounds any UI stall)
SYNC_INTERVALS = [5, 10, 30, 60]  # minutes offered in the settings menu


def _load_notion_config() -> dict:
    cfg: dict = {}
    try:
        text = (Path(__file__).resolve().parent.parent / "notion.txt").read_text()
        for line in text.splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    for env_key, cfg_key in (("NOTION_TOKEN", "token"), ("NOTION_DATABASE", "database")):
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key].strip()
    return cfg


NOTION = _load_notion_config()
NOTION_VERSION = NOTION.get("version", "2022-06-28")
notion_configured = bool(NOTION.get("token") and NOTION.get("database"))
_notion_title_prop = NOTION.get("title")  # cached; auto-detected on first use


def _notion_request(method: str, path: str, body: dict | None = None):
    """Return (status, json). status 0 means the request never reached Notion."""
    import json as _json
    import urllib.error
    import urllib.request

    data = _json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{NOTION_ENDPOINT}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {NOTION.get('token', '')}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=NOTION_TIMEOUT) as resp:
            return resp.status, _json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, _json.loads(exc.read().decode())
        except Exception:
            return exc.code, {"message": str(exc)}
    except Exception as exc:
        return 0, {"message": str(exc)}


def notion_title_property() -> str:
    """The DB's title property name — differs per user's schema, so detect it."""
    global _notion_title_prop
    if _notion_title_prop:
        return _notion_title_prop
    status, data = _notion_request("GET", f"/databases/{NOTION.get('database')}")
    if status == 200:
        for name, prop in (data.get("properties") or {}).items():
            if prop.get("type") == "title":
                _notion_title_prop = name
                return name
    return "Name"  # Notion's default title property name


def notion_create_page(title: str, body: str, prefix: str = "") -> tuple[bool, dict]:
    prop = notion_title_property()
    full_title = f"{prefix} {title}".strip() if prefix else title
    payload = {
        "parent": {"database_id": NOTION.get("database"), "type": "database_id"},
        # Only the title property is set, so this works with ANY database schema.
        "properties": {prop: {"title": [{"text": {"content": full_title[:1900]}}]}},
        "children": [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": body[:1900]}}]},
        }],
    }
    status, data = _notion_request("POST", "/pages", payload)
    return status in (200, 201), data


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

# Key/value settings that must survive restarts (sync on/off, interval, type).
try:
    db.create_table("settings", {"key": "TEXT PRIMARY KEY", "value": "TEXT"})
except Exception as exc:
    logger.info("settings table already exists (%s)", exc)

# Migration: track which notes have been pushed to Notion. The ALTER fails once
# the column exists, which is expected on every run after the first.
try:
    db.execute_sql("ALTER TABLE notes ADD COLUMN synced INTEGER DEFAULT 0")
    logger.info("added notes.synced column")
except Exception:
    pass

COLUMNS = ["id", "created", "raw", "ai", "synced"]


def get_setting(key: str, default=None):
    try:
        rows = db.execute_sql("SELECT value FROM settings WHERE key = ?", (key,))
        if rows:
            return rows[0].get("value")
    except Exception as exc:
        logger.warning("get_setting(%s) failed: %s", key, exc)
    return default


def set_setting(key: str, value) -> None:
    try:
        db.execute_sql(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(value))
        )
    except Exception as exc:
        logger.warning("set_setting(%s) failed: %s", key, exc)


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


# --------------------------------------------------------------- Notion sync ---
#
# Cached in memory so the loop() scheduler doesn't hit the DB every tick;
# set_settings() keeps these and the persisted values in step.
_sync_enabled = get_setting("sync_enabled", "0") == "1"
_sync_interval = int(get_setting("sync_interval", "10") or 10)
_item_type = get_setting("item_type", "note")  # "note" or "reminder"


def pending_note_count() -> int:
    try:
        rows = db.execute_sql("SELECT COUNT(*) AS c FROM notes WHERE COALESCE(synced,0)=0")
        return int(rows[0]["c"]) if rows else 0
    except Exception:
        return 0


def sync_settings() -> dict:
    return {
        "notion_configured": notion_configured,
        "enabled": _sync_enabled,
        "interval": _sync_interval,
        "intervals": SYNC_INTERVALS,
        "item_type": _item_type,
        "pending": pending_note_count(),
        "last_sync": get_setting("last_sync", ""),
        "last_result": get_setting("last_result", ""),
    }


def sync_to_notion(reason: str = "scheduled") -> dict:
    """Push up to MAX_SYNC_PER_CYCLE unsynced notes to Notion. Runs in loop()."""
    if not notion_configured:
        return {"ok": False, "msg": "Notion not configured"}
    try:
        rows = db.execute_sql(
            "SELECT id, raw, ai FROM notes WHERE COALESCE(synced,0)=0 "
            "ORDER BY id ASC LIMIT ?",
            (MAX_SYNC_PER_CYCLE,),
        ) or []
    except Exception as exc:
        return {"ok": False, "msg": f"read failed: {exc}"}

    prefix = "⏰" if _item_type == "reminder" else "📝"
    synced, err = 0, ""
    for r in rows:
        raw = (r.get("raw") or "").strip()
        ai = (r.get("ai") or "").strip()
        title = raw.splitlines()[0][:120] if raw else "Note"
        body = raw + (f"\n\n— AI —\n{ai}" if ai and not ai.startswith("(no AI") else "")
        ok, data = notion_create_page(title, body, prefix)
        if ok:
            db.execute_sql("UPDATE notes SET synced=1 WHERE id=?", (r["id"],))
            synced += 1
        else:
            # Stop on the first failure (usually auth/sharing) and surface it,
            # rather than hammering Notion with the whole backlog.
            err = str(data.get("message", data.get("code", "unknown error")))[:160]
            break

    set_setting("last_sync", datetime.now().isoformat(timespec="seconds"))
    result = f"{synced} synced" + (f" — stopped: {err}" if err else "")
    set_setting("last_result", result)
    logger.info("notion sync (%s): %s", reason, result)
    return {"ok": not err, "synced": synced, "msg": result}


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
        # Open mode: no password needed. If a stale login page (left over from
        # when a password WAS set) submits anyway, let it through so it recovers
        # instead of hanging with no response.
        ui.send_message("auth_ok", {}, room=sid)
        pushes.put(sid)
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


def on_get_settings(sid: str, data) -> None:
    if not _guard(sid):
        return
    ui.send_message("settings", sync_settings(), room=sid)


def on_set_settings(sid: str, data) -> None:
    global _sync_enabled, _sync_interval, _item_type
    if not _guard(sid):
        return
    data = data or {}
    if "enabled" in data:
        _sync_enabled = bool(data["enabled"])
        set_setting("sync_enabled", "1" if _sync_enabled else "0")
    if "interval" in data:
        try:
            iv = int(data["interval"])
            if iv in SYNC_INTERVALS:
                _sync_interval = iv
                set_setting("sync_interval", iv)
        except (ValueError, TypeError):
            pass
    if data.get("item_type") in ("note", "reminder"):
        _item_type = data["item_type"]
        set_setting("item_type", _item_type)
    broadcast_settings()


def on_sync_now(sid: str, data) -> None:
    if not _guard(sid):
        return
    pending.put({"op": "sync_now"})  # run in loop() to keep the DB single-owner


ui.on_connect(on_connect)
ui.on_disconnect(on_disconnect)
ui.on_message("auth", on_auth)
ui.on_message("new_note", on_new_note)
ui.on_message("edit_note", on_edit_note)
ui.on_message("delete_note", on_delete_note)
ui.on_message("get_settings", on_get_settings)
ui.on_message("set_settings", on_set_settings)
ui.on_message("sync_now", on_sync_now)


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


def broadcast_settings() -> None:
    s = sync_settings()
    if PASSWORD is None:
        ui.send_message("settings", s)
    else:
        for sid in list(authed):
            ui.send_message("settings", s, room=sid)


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
        # synced=0 so the edited note re-syncs to Notion.
        {"raw": text, "ai": ai_text if ok else NO_MODEL_PLACEHOLDER, "synced": 0},
        f"id = {int(note_id)}",
    )
    logger.info("edited note id=%d (ai=%s)", int(note_id), ok)


def do_delete(note_id) -> None:
    db.delete("notes", f"id = {int(note_id)}")
    logger.info("deleted note id=%d", int(note_id))


def do_sync_now() -> None:
    sync_to_notion("manual")


OPS = {
    "add": lambda o: do_add(o["text"]),
    "edit": lambda o: do_edit(o["id"], o["text"]),
    "delete": lambda o: do_delete(o["id"]),
    "sync_now": lambda o: do_sync_now(),
}


# --------------------------------------------------------------- main loop ---

_last_sync_run = 0.0  # monotonic time of the last scheduled sync attempt


def maybe_sync() -> None:
    """Scheduled Notion push. Cheap to call every tick — it rate-limits itself
    and only touches the DB/network when a sync is actually due."""
    global _last_sync_run
    if not (notion_configured and _sync_enabled):
        return
    now = time.monotonic()
    if now - _last_sync_run < _sync_interval * 60:
        return
    _last_sync_run = now
    if pending_note_count() == 0:
        return
    sync_to_notion("scheduled")
    broadcast_notes()      # synced badges changed
    broadcast_settings()   # last_sync / pending changed


def loop() -> None:
    # 0. Periodic Notion sync (rate-limited internally).
    maybe_sync()

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
    broadcast_settings()


scheme = "https" if USE_TLS else "http"
logger.info(
    "Notes app starting — open %s://<board-ip>:7000  (auth: %s)",
    scheme,
    "password required" if PASSWORD else "OPEN — no password set",
)
App.run(user_loop=loop)
