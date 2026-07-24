"""Bring-up step 2 — is the Bridge alive, and how fast is it?

Python sends ping(seq) to the sketch; the sketch notifies pong(seq) back. We
time the round trip and report percentiles every 20 samples.

Two things this tells you:

  1. Whether the MPU<->MCU RPC link works at all. If you see no pongs, the
     Bridge is broken and every later app will fail.
  2. What round-trip latency actually is on your board. Write it down. Without a
     baseline you can't tell a real regression from normal jitter later.
"""

import logging
import statistics
import time

from arduino.app_utils import App, Bridge, Logger

logger = Logger("BridgeRoundtrip", level=logging.INFO)

PING_INTERVAL_S = 0.05     # 20 Hz — brisk, but not enough to saturate the link
REPORT_EVERY = 20          # samples per summary line
TIMEOUT_S = 2.0            # how long before we declare a ping lost

sent_at: dict[int, float] = {}
latencies_ms: list[float] = []
seq = 0
lost = 0
call_errors = 0


def pong(received_seq: int) -> None:
    """Called by the sketch. Matches the reply to its send time."""
    global lost

    start = sent_at.pop(received_seq, None)
    if start is None:
        # Arrived after we gave up on it, or a sequence number we never sent.
        logger.warning("pong %d was unexpected (late or duplicate)", received_seq)
        return

    latencies_ms.append((time.monotonic() - start) * 1000)

    if len(latencies_ms) % REPORT_EVERY == 0:
        window = latencies_ms[-REPORT_EVERY:]
        ordered = sorted(window)
        p95 = ordered[int(len(ordered) * 0.95) - 1]
        logger.info(
            "n=%4d  min %.2f ms  mean %.2f ms  p95 %.2f ms  max %.2f ms  lost %d  errors %d",
            len(latencies_ms),
            min(window),
            statistics.fmean(window),
            p95,
            max(window),
            lost,
            call_errors,
        )


Bridge.provide("pong", pong)


def expire_stale(now: float) -> None:
    """Count pings the sketch never answered."""
    global lost

    stale = [s for s, t in sent_at.items() if now - t > TIMEOUT_S]
    for s in stale:
        del sent_at[s]
        lost += 1
        logger.error("ping %d timed out after %.1fs", s, TIMEOUT_S)


def loop() -> None:
    global seq, call_errors

    now = time.monotonic()
    expire_stale(now)

    seq += 1
    sent_at[seq] = now

    # Bridge.call raises if the sketch rejects the request. Catch it: this app
    # exists to diagnose a sick link, so dying on the first bad ping would
    # throw away the very information you came for.
    try:
        Bridge.call("ping", seq)
    except Exception as exc:
        sent_at.pop(seq, None)
        call_errors += 1
        if call_errors == 1:
            logger.error("Bridge.call('ping') failed: %s", exc)
            logger.error("  'method not found'  -> the sketch didn't flash, or Bridge.begin() is missing")
            logger.error("  'Wrong type parameter' -> sketch signature must be ping(int), not unsigned long")
            logger.error("  timeout             -> check: systemctl status arduino-router")
        elif call_errors % 100 == 0:
            logger.error("%d consecutive call failures — see the first error above", call_errors)
        time.sleep(1.0)  # back off rather than spinning on a broken link
        return

    time.sleep(PING_INTERVAL_S)


logger.info("Pinging the MCU at %.0f Hz — first summary after %d replies.", 1 / PING_INTERVAL_S, REPORT_EVERY)
App.run(user_loop=loop)
