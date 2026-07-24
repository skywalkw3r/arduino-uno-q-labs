# 05 — I²C scan

**Proves:** both I²C buses work, and shows you what's attached to each.
**Wiring:** any I²C or Qwiic device (a Modulino node is the zero-effort option).

## The two buses

This is the thing worth internalising about I²C on this board:

| Object | Bus | Where | Notes |
|---|---|---|---|
| `Wire` | I²C1 | D20 (SDA) / D21 (SCL) header pins | needs pull-ups; most breakouts have them |
| `Wire1` | I²C4 | **Qwiic connector** | **3.3 V only**, Modulino nodes live here |

Scanning the wrong one is the most common reason a working sensor looks dead.
This app scans both, so that ambiguity disappears.

## Run it

Paste both files into a new App Lab app and Run. Plug a Qwiic device in while
it's running — the scan repeats every 3 seconds and logs on change.

## What you should see

```
════════════════════════════════════════════════════════════════
I2C scan #2
Wire  — header (D20 SDA / D21 SCL): nothing found
Wire1 — Qwiic  (3.3 V only): 1 device(s)
    0x29  VL53L0X / VL53L4CD ToF (Modulino Distance)
════════════════════════════════════════════════════════════════
```

Output only appears when the device list **changes**, so hot-plugging is easy to
spot and a steady setup doesn't spam the console.

## About the address hints

`KNOWN_ADDRESSES` in `python/main.py` maps addresses to likely parts. I²C
addresses are **not unique to a device** — 0x68 is a DS3231 RTC *and* an
MPU-6050, and plenty of parts are configurable. Treat a hint as a starting point
for a datasheet search, not an identification. Add your own devices to the dict
as you accumulate them.

The scan covers 0x08–0x77; addresses outside that range are reserved by the I²C
spec.

## The `provide_safe` pattern, again

The scan hammers `Wire` and then calls `Bridge.notify()`. Neither is safe inside
an RPC handler, so the handler only sets a flag:

```cpp
void request_scan() { scanRequested = true; }   // registered with provide_safe
```

and `loop()` does the scanning and reporting. See
[docs/anatomy.md](../../docs/anatomy.md#the-two-rules).

## If it fails

- **Both buses empty with a device attached** — check the device is powered and
  3.3 V. On the header bus, confirm pull-ups exist (bare chips need them; most
  breakout boards include them).
- **Device shows on neither bus but works elsewhere** — try the other connector.
  If it only works on `Wire`, its Qwiic cable or the connector may be at fault.
- **`request_scan` times out** — Bridge problem, not I²C. Run app 02.
- **Scan hangs the board** — a shorted SDA/SCL can stall the bus. Unplug
  everything and rescan.

## Next step

Once a Modulino shows up here, `Arduino_Modulino` gives you a proper driver.
Note it binds to `Wire1`:

```cpp
Modulino.begin(Wire1);
```

and needs the library pinned in `sketch/sketch.yaml` — see
[docs/hardware.md](../../docs/hardware.md#qwiic-and-modulino).
