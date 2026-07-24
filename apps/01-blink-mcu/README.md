# 01 — Blink MCU

**Proves:** the sketch toolchain compiles, flashes, and runs on the STM32.
**Wiring:** none.

## Run it

Paste `sketch/sketch.ino` into a new App Lab app's sketch and `python/main.py`
into its Python file, then Run. The Python side is deliberately empty —
`App.run()` is what keeps App Lab holding the app open.

## What you should see

- `LED_BUILTIN` toggling twice a second.
- LED 3 cycling red → green → blue.
- In the console: `MCU alive.` then `LED 3 -> red` / `green` / `blue`.

## Why it's written this way

**Active low.** Every LED on this board turns on with a logic `0`. The sketch
defines `ON = LOW` / `OFF = HIGH` so the inversion appears once instead of being
scattered through the code where you'll misread it.

**No `delay()`.** This blink could use `delay(500)` and work fine. It doesn't,
because on this board the Bridge runs a background thread on the same core, and
blocking in `loop()` becomes a real problem in apps 03–06. Building the
`millis()` habit here costs nothing.

**`Serial`, not `Monitor`.** `Serial.print()` reaches the App Lab console on
core 0.55.0 and later. Older examples use a `Monitor` object; it still works, but
`Serial` is the recommended path for new code.

## If it fails

- **Compile error on `LED3_R`** — the platform isn't right. `sketch/sketch.yaml`
  must specify `platform: arduino:zephyr`.
- **Nothing in the console but the LEDs blink** — you're on a core older than
  0.55.0. Swap `Serial` for `Monitor` (`Monitor.begin(115200)` /
  `Monitor.println(...)`).
- **Won't flash** — app 00 first. If the Linux side is unhealthy, flashing has
  nothing to talk to.
