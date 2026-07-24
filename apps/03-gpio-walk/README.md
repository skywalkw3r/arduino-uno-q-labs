# 03 — GPIO walk

**Proves:** every digital header pin D2–D13 can drive a load, and that Python
can command the MCU pin-by-pin.
**Wiring:** one LED + 220 Ω resistor (optional — a multimeter or logic probe
works too).

## ⚠️ Before you wire anything

**These pins are 3.3 V, not 5 V.** The UNO Q has the UNO footprint but the
STM32U585 runs at 3.3 V logic. Never feed 5 V into a header pin.

## Wiring

```
D<n> ──[220 Ω]──▶|── GND
                LED
```

Long leg (anode) to the pin, short leg through the resistor to GND. Move it down
the header as the walk progresses, or build a 12-LED bar and watch the whole
sweep at once.

## Run it

Paste both files into a new App Lab app and Run.

## What you should see

```
Sketch reports pin range D2..D13
  D2  HIGH
  D3  HIGH
  D4  HIGH
  ...
  D13 HIGH
  ... all pins low
Sweep 1 complete — 12/12 pins confirmed by the sketch
```

One second per pin, a two-second blank gap, then it repeats.

## Why D0 and D1 are skipped

They're the UART TX/RX pair. Driving them fights with serial output. D2–D13 is
the range you can safely toggle.

## Reading the result

The log line comes from the **sketch confirming what it actually drove**, not
from Python assuming. If Python says `D7 HIGH` and no LED lights on D7 while
every other pin works, that pin is the problem — not the code.

## Tuning

Both knobs are in `python/main.py`, no reflash needed:

- `DWELL_S` — time per pin. Drop to `0.15` for a fast chase once you trust it.
- `PAUSE_AT_END_S` — the blank gap between sweeps.

## If it fails

- **No output at all** — run app 02 first; this app depends on a working Bridge.
- **Every pin dead** — check your LED polarity before suspecting the board. The
  long leg goes to the pin.
- **One pin dead** — try that pin as an input, or with a meter instead of the
  LED, to separate a damaged pin from a bad connection.
