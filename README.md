# arduino-uno-q-labs

Bring-up tests and worked examples for the **Arduino UNO Q (4 GB)**.

The UNO Q is two computers on one UNO-footprint board:

| | MPU (Linux side) | MCU (real-time side) |
|---|---|---|
| Silicon | Qualcomm Dragonwing QRB2210, 4× Cortex-A53 @ 2.0 GHz | STM32U585, Cortex-M33 @ 160 MHz |
| Memory | 4 GB LPDDR4 / 32 GB eMMC | 2 MB flash / 786 KB SRAM |
| Runs | Debian + Arduino App Lab + Docker | Arduino core on Zephyr |
| You write | `python/main.py` | `sketch/sketch.ino` |

The two halves talk over an RPC link called the **Bridge**. Almost everything
interesting on this board is "Python asks the MCU to do a thing, MCU streams
data back". Every app in `apps/` is a test of one link in that chain, ordered so
that if app *N* fails you already know apps *0..N-1* passed.

## Order of operations

Run these in order the first time you power the board. Each one isolates a
different failure, so the first one that fails tells you where the problem is.

| App | Proves | Extra hardware |
|---|---|---|
| [`00-hello-mpu`](apps/00-hello-mpu) | Linux side boots, App Lab runs Python, MPU LEDs work | none |
| [`01-blink-mcu`](apps/01-blink-mcu) | sketch compiles, flashes, and runs on the STM32 | none |
| [`02-bridge-roundtrip`](apps/02-bridge-roundtrip) | the Python↔MCU RPC link works, and how fast | none |
| [`03-gpio-walk`](apps/03-gpio-walk) | every digital header pin drives a load | LED + 220 Ω (optional) |
| [`04-analog-scan`](apps/04-analog-scan) | 14-bit ADC on A0–A5 | 10 kΩ pot (optional) |
| [`05-i2c-scan`](apps/05-i2c-scan) | both I²C buses, incl. the Qwiic connector | any I²C/Qwiic device |
| [`06-web-dashboard`](apps/06-web-dashboard) | the `web_ui` brick, live telemetry at `http://<board-ip>:7000` | none |
| [`07-camera-objects`](apps/07-camera-objects) | camera + on-device object detection | USB camera |
| [`08-llm-bench`](apps/08-llm-bench) | local LLM speed (load, TTFT, tok/s) on the QRB2210 | model download (GUI) |

Plus [`tests/run_checks.py`](tests/run_checks.py) — 19 stdlib-only checks you
run **on the board** to assert the OS-level things (router service, serial
transport, LED sysfs nodes, storage, thermals) before you blame your own code.

## Running an app

`arduino-app-cli app start` takes a **directory path**, so apps run straight out
of this repo — no zip, no import step, no copy/paste into the App Lab UI.

```bash
./scripts/deploy.sh arduino@<board-ip>          # copy the repo to the board
ssh arduino@<board-ip>
cd arduino-uno-q-labs
python3 tests/run_checks.py                     # confirm the board is healthy
arduino-app-cli app start apps/00-hello-mpu     # run the first app
```

[`scripts/app.sh`](scripts/app.sh) wraps the lifecycle and verifies each step
actually took effect. Point it at the board once and you can drive everything
from your laptop:

```bash
export UNOQ_HOST=arduino@<board-ip>
```

```bash
./scripts/app.sh start apps/00-hello-mpu
./scripts/app.sh logs  apps/00-hello-mpu
./scripts/app.sh stop  apps/00-hello-mpu
./scripts/app.sh status
./scripts/app.sh stop-all
```

With `UNOQ_HOST` set it forwards each command over SSH; run it on the board and
it executes locally. Add the export to your shell profile to make it stick.

> The work always happens **on the board** — `arduino-app-cli` and the Docker
> daemon live there. Your laptop's `arduino-cli` is the classic Arduino CLI, a
> different tool with no `app` subcommand.

`deploy.sh` uses rsync when the board has it and falls back to tar over SSH when
it doesn't — the stock image has no rsync.

You can still use the App Lab UI (*My Apps → Create new app*, paste in
`python/main.py` and `sketch/sketch.ino`, add any `bricks:` from `app.yaml`).
The CLI is just faster once SSH works.

> **Apps run inside Docker containers.** Anything process-scoped — `hostname`,
> the IP address, `systemctl` — reports the *container*, not the board. Device
> nodes and sysfs (`/dev/ttyHS1`, the LEDs, `/proc` CPU and memory) are the real
> host's. Host-level checks belong in `tests/run_checks.py` over SSH.
>
> A running app keeps its compose project in `<app>/.cache/`. **Don't delete it
> while the app is running** or the container is orphaned and `app stop` can no
> longer reach it.

## Repo layout

```
apps/            App Lab apps, one per bring-up step
  <app>/
    app.yaml         name, icon, description, bricks
    python/main.py   runs on the Qualcomm MPU under Linux
    sketch/sketch.ino  runs on the STM32 under Zephyr
    sketch/sketch.yaml platform + library pins
    assets/          static files, if the app has a web UI
docs/            anatomy of an app, hardware reference
scripts/         deploy, app lifecycle, on-board inventory
tests/           stdlib bring-up checks (run on the board)
```

## Read these before you wire anything up

- **[docs/anatomy.md](docs/anatomy.md)** — what each file in an app does, what
  actually happens when you press Run, and the two Bridge rules that cause most
  lockups (`provide` vs `provide_safe`, and never calling out from inside an RPC
  handler). Start here if you're new to the two-processor split.
- **[docs/hardware.md](docs/hardware.md)** — pin maps, cooling, Qwiic/Modulino,
  and the thing that will bite you: **the headers are 3.3 V, not 5 V.** Classic
  UNO shields fit mechanically and can still damage inputs.

Each app's own README covers its wiring, expected output, and failure modes.

## Sources

Specs and APIs here were taken from the
[UNO Q product page](https://store-usa.arduino.cc/products/uno-q-4gb),
the [UNO Q user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/),
and the official
[app-bricks-examples](https://github.com/arduino/app-bricks-examples) repo.

## License

MIT — see [LICENSE](LICENSE).
