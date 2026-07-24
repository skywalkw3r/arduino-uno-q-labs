# 00 — Hello MPU

**Proves:** the Linux side boots, App Lab can run a Python app, and the
MPU-controlled LEDs work.
**Wiring:** none.

## Run it

Paste `python/main.py` into a new App Lab app and press Run. There is no sketch.

## What you should see

A block of board inventory in the console, then `LED 1 -> red / green / blue`
once a second, matching LED 1 on the board.

```
==============================================================
UNO Q — Linux side inventory
==============================================================
OS         : PRETTY_NAME="Debian GNU/Linux ..."
Kernel     : Linux 6.x...
CPU        : 4 cores — ...
Memory     : 4014xxx kB total, ...
Thermals   : ...
--------------------------------------------------------------
Router     : active
ttyHS1     : present
Network    : 192.168.x.x
==============================================================
```

## Read the output for

- **`Router: active`** — if this says `inactive` or `failed`, the Bridge is dead
  and apps 02+ will not work. `sudo systemctl restart arduino-router`.
- **`ttyHS1: present`** — the physical MPU↔MCU serial transport. Missing means a
  deeper problem than your code.
- **Thermals** — write these down. This is your idle baseline; you need it later
  to tell thermal throttling from a software bug.
- **Memory** — confirm you're seeing ~4 GB, i.e. you actually have the 4 GB
  variant.

## If it fails

`Leds` import errors mean the app isn't running under App Lab's Python
environment — it provides `arduino.app_utils`. Run it through App Lab, not a
bare `python3 main.py`.
