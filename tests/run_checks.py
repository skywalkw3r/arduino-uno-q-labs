#!/usr/bin/env python3
"""Bring-up checks, no dependencies. Run this ON the board.

    python3 tests/run_checks.py

The stock UNO Q image has no pip and no pytest, and installing them needs a
sudo password — so this runner uses nothing but the standard library.

Exit code is 0 when everything that ran passed, 1 if anything failed. Skips
don't fail the run: they mean optional hardware isn't attached.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import CHECKS, on_board, thermal_zones  # noqa: E402

# Colour only when attached to a terminal, so piping to a file stays clean.
if sys.stdout.isatty():
    GREEN, RED, YELLOW, DIM, BOLD, RESET = (
        "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m",
    )
else:
    GREEN = RED = YELLOW = DIM = BOLD = RESET = ""

MARK = {
    True: f"{GREEN}PASS{RESET}",
    False: f"{RED}FAIL{RESET}",
    None: f"{YELLOW}SKIP{RESET}",
}


def main() -> int:
    if not on_board():
        print(
            f"{YELLOW}warning:{RESET} this doesn't look like the UNO Q "
            "(expected Linux/aarch64).\n"
            "         Run it on the board:  ssh <board> 'python3 arduino-uno-q-labs/tests/run_checks.py'\n"
        )

    print(f"\n{BOLD}UNO Q bring-up checks{RESET}")

    passed = failed = skipped = 0
    current_group = None
    failures: list[tuple[str, str]] = []

    for group, name, check in CHECKS:
        if group != current_group:
            current_group = group
            print(f"\n{DIM}{group}{RESET}")

        try:
            status, detail = check()
        except Exception as exc:  # a broken check shouldn't abort the run
            status, detail = False, f"check raised {exc.__class__.__name__}: {exc}"

        print(f"  {MARK[status]}  {name:<32} {DIM}{detail}{RESET}")

        if status is True:
            passed += 1
        elif status is False:
            failed += 1
            failures.append((name, detail))
        else:
            skipped += 1

    # The thermal baseline is the whole point of running this on a healthy
    # board — print it so it lands in the saved output.
    zones = thermal_zones()
    if zones:
        print(f"\n{DIM}thermal baseline{RESET}")
        for name, temp in sorted(zones.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<28} {temp:5.1f} C")

    print(
        f"\n{BOLD}{passed} passed, {failed} failed, {skipped} skipped{RESET}"
    )

    if failures:
        print(f"\n{BOLD}What to fix{RESET}")
        for name, detail in failures:
            print(f"  {RED}•{RESET} {name}: {detail}")
        print("\nSee docs/hardware.md and the app READMEs")
        return 1

    print(f"{DIM}Board is healthy. Save this output as your baseline.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
