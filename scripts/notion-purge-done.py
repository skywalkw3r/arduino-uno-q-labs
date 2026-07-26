#!/usr/bin/env python3
"""Archive every completed (Done = checked) item in the notes app's Notion DB.

Reads the token + database id from the notes app's gitignored notion.txt, so no
credentials go on the command line. Dry-run by default — pass --yes to archive.

    # see what would be archived (safe, read-only):
    python3 scripts/notion-purge-done.py

    # actually archive them:
    python3 scripts/notion-purge-done.py --yes

"Archive" moves pages to the Notion trash (restorable for ~30 days), which is the
only "delete" the Notion API offers — so this is reversible. Only pages whose
"Done" checkbox is checked are touched; everything else is left alone.

Stdlib only, so it runs on the board's bare Python. Run it where notion.txt
lives (the board), e.g.:

    ssh arduino@<board-ip> 'python3 arduino-uno-q-labs/scripts/notion-purge-done.py --yes'
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

NOTION_VERSION = "2022-06-28"
DONE_PROPERTY = "Done"          # the checkbox that marks an item complete
RATE_LIMIT_SLEEP = 0.35         # seconds between writes (~3 req/s Notion cap)


def load_config() -> dict:
    """Find notion.txt next to the notes app and parse token/database."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "apps" / "09-notes" / "notion.txt",  # repo layout
        here / "notion.txt",
    ]
    for path in candidates:
        if path.exists():
            cfg = {}
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
            if cfg.get("token") and cfg.get("database"):
                return cfg
    sys.exit("error: could not find a notion.txt with token= and database= "
             "(looked next to the notes app). Run this on the board.")


def api(cfg: dict, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {cfg['token']}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {"message": str(exc)}
    except Exception as exc:
        return 0, {"message": str(exc)}


def title_of(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "(untitled)"
    return "(untitled)"


def find_done(cfg: dict) -> list:
    """All pages where the Done checkbox is checked, across all pages of results."""
    pages, cursor = [], None
    while True:
        body = {
            "filter": {"property": DONE_PROPERTY, "checkbox": {"equals": True}},
            "page_size": 100,
        }
        if cursor:
            body["start_cursor"] = cursor
        status, data = api(cfg, "POST", f"/databases/{cfg['database']}/query", body)
        if status != 200:
            sys.exit(f"error querying database: {data.get('message', data)}")
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            return pages
        cursor = data.get("next_cursor")


def main() -> int:
    execute = "--yes" in sys.argv
    cfg = load_config()

    done = find_done(cfg)
    print(f"Found {len(done)} completed item(s) (Done checked).")
    for p in done:
        print(f"  {'archiving' if execute else 'would archive'}: {title_of(p)}")

    if not execute:
        print(f"\nDry run — nothing changed. Re-run with --yes to archive all {len(done)}.")
        return 0

    if not done:
        return 0

    print(f"\nArchiving {len(done)} item(s) to Notion trash (restorable ~30 days)…")
    ok = fail = 0
    for i, p in enumerate(done, 1):
        status, data = api(cfg, "PATCH", f"/pages/{p['id']}", {"archived": True})
        if status == 200:
            ok += 1
        else:
            fail += 1
            print(f"  ! failed on {title_of(p)}: {data.get('message', status)}")
        if i % 25 == 0:
            print(f"  … {i}/{len(done)}")
        time.sleep(RATE_LIMIT_SLEEP)

    print(f"\nDone: {ok} archived, {fail} failed. (Restore from Notion → Trash if needed.)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
