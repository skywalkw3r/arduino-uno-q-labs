# Anatomy of an app

## The files

```
apps/02-bridge-roundtrip/
├── app.yaml              manifest — name, icon, description, bricks
├── python/
│   ├── main.py           runs on the MPU (Linux), inside a Docker container
│   └── requirements.txt  optional pip dependencies for that container
├── sketch/
│   ├── sketch.ino        C++ — compiled and FLASHED into the STM32
│   └── sketch.yaml       build config — target platform + library versions
├── assets/               optional — static files served by the web_ui brick
└── .cache/               generated at runtime. Never edit, never commit.
```

| File | Language | Where it ends up | When |
|---|---|---|---|
| `app.yaml` | YAML | read by App Lab | at start |
| `python/main.py` | Python | Docker container on the MPU | runs continuously |
| `python/requirements.txt` | pip list | that container's venv | at start |
| `sketch/sketch.ino` | C++/Arduino | **STM32 internal flash** | written once at start |
| `sketch/sketch.yaml` | YAML | the compiler | at start |
| `assets/*` | HTML/CSS/JS | served over HTTP by `web_ui` | on request |
| `.cache/*` | generated | app venv + `app-compose.yaml` | at start |

## The correction: the Bridge does not carry your sketch

A natural assumption is that Python runs in Docker and the Bridge "sends the
.ino to the microcontroller". The first half is right; the second isn't.

`sketch.ino` is **compiled to a binary and written into the STM32's 2 MB flash**
at app start, using the onboard debug interface (OpenOCD). You can watch it
happen in the App Lab console:

```
[stm32u5.cpu] halted due to debug-request, current mode: Thread
Info : device idcode = 0x30076482 (STM32U57/U58xx - Rev U : 0x3007)
Info : flash size = 2048 KiB
Info : Padding image section 0 at 0x08112ee4 with 12 bytes
```

The Bridge is what the two processors use to **exchange data at runtime**, after
the sketch is already running. Code goes over the debug interface once; data
goes over the Bridge continuously.

## What happens when you press Run

```
arduino-app-cli app start apps/02-bridge-roundtrip
   │
   ├─ 1. read app.yaml                  name, description, which bricks to install
   │
   ├─ 2. compile sketch/sketch.ino      arduino-cli, target arduino:zephyr,
   │                                    libraries pinned by sketch/sketch.yaml
   │
   ├─ 3. FLASH the binary  ──────────►  STM32U585
   │        (OpenOCD, debug interface)  sketch now runs independently
   │
   ├─ 4. build the Python environment   venv in .cache/, installs requirements.txt
   │
   ├─ 5. write .cache/app-compose.yaml  the Docker Compose project for this app
   │
   └─ 6. start the container ────────►  python/main.py runs on the MPU
                                        (this is the process you can stop)
```

## The two processors, side by side

```
        ┌───────────────────────────────┐     ┌──────────────────────────┐
        │  MPU — Qualcomm QRB2210       │     │  MCU — STM32U585         │
        │  4× Cortex-A53 @ 2.0 GHz      │     │  Cortex-M33 @ 160 MHz    │
        │  Debian 13 + Docker           │     │  Arduino core on Zephyr  │
        │                               │     │                          │
        │  ┌─────────────────────────┐  │     │  ┌────────────────────┐  │
        │  │ container               │  │     │  │ sketch.ino         │  │
        │  │   python/main.py        │  │     │  │   setup()          │  │
        │  │   + bricks              │  │     │  │   loop()           │  │
        │  └───────────┬─────────────┘  │     │  └─────────┬──────────┘  │
        └──────────────┼────────────────┘     └────────────┼─────────────┘
                       │                                   │
                  arduino-router  ◄── /dev/ttyHS1 ──►  Serial1
                    (MessagePack RPC — "the Bridge")
```

## Which file do I edit?

| I want to… | Edit |
|---|---|
| read a pin, drive a motor, anything time-critical | `sketch/sketch.ino` |
| call an AI model, serve a page, talk to a network | `python/main.py` |
| add a Python package | `python/requirements.txt` |
| add an Arduino library | `sketch/sketch.yaml` |
| add an AI capability | `bricks:` in `app.yaml` |
| change the web UI | `assets/` |

## Passing data across

Sketch exposes a function; Python calls it:

```cpp
void set_led(bool on) { ledDesired = on; ledPending = true; }

void setup() {
    Bridge.begin();
    Bridge.provide_safe("set_led", set_led);
}
```

```python
Bridge.call("set_led", True)
```

Sketch pushes data up to Python:

```cpp
Bridge.notify("adc_sample", analogRead(A0));
```

```python
def adc_sample(raw: int): ...
Bridge.provide("adc_sample", adc_sample)
```

### The two rules

Break either of these and you get a hang that looks like a hardware fault.

**1. Never start a new call inside an RPC handler.** No `Bridge.call()`,
`Serial.print()`, or `Monitor.print()` inside a function you registered with
`provide()`. Initiating communication while answering communication deadlocks
the link.

**2. `provide()` runs on the RPC thread; `provide_safe()` runs in `loop()`.**
Handlers registered with `provide()` execute on a high-priority background
thread and must not touch Arduino APIs. Use `provide_safe()` for anything that
calls `digitalWrite`, `Wire`, `Serial`, or similar.

The shape that always works — the handler sets a flag, `loop()` does the work:

```cpp
volatile bool scanRequested = false;

void request_scan() { scanRequested = true; }   // returns instantly

void setup() {
    Bridge.begin();                              // mandatory
    Bridge.provide_safe("request_scan", request_scan);
}

void loop() {
    if (scanRequested) {
        scanRequested = false;
        do_the_work();                           // Arduino APIs safe here
        Bridge.notify("scan_done", result);      // and so is replying
    }
}
```

Every app in this repo that takes a command from Python uses this shape.

### Inbound parameter types are strict

A `provide()` parameter must be a type the RPC layer binds. Use **`int`,
`bool`, `String`, `std::vector<int>`, `float`**. `unsigned long` is *not*
accepted inbound, and fails at runtime rather than at compile time:

```
ValueError: Request 'ping' failed: Wrong type parameter in position: 0 (253)
```

`unsigned long` is fine for values you send *out* with `notify()` — the
restriction is on parameters coming in.

### Debugging the link

```bash
systemctl status arduino-router        # is it up?
sudo systemctl restart arduino-router  # unstick it without rebooting
journalctl -u arduino-router -f        # live RPC traffic
```

`arduino-router` owns `/dev/ttyHS1` on Linux and `Serial1` on the MCU. Opening
either from your own code breaks the Bridge.

## `.cache/` — leave it alone

Generated per app at start: the Python venv, and `app-compose.yaml`, which is
the Docker Compose project the container is managed through.

**Deleting `.cache` while the app is running orphans the container** — the thing
that knows how to stop it is gone. It's gitignored, and `scripts/deploy.sh`
unpacks over the tree rather than wiping it for exactly this reason.
