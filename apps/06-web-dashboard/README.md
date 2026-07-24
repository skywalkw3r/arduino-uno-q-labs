# 06 — Web dashboard

**Proves:** the `web_ui` brick works, and data flows the whole way from the MCU
to a browser and back.
**Wiring:** none (a pot on A0 makes it much more fun).

```
browser  ◄──websocket──►  Python (QRB2210)  ◄──Bridge──►  sketch (STM32)
```

## One-time setup

The page needs two JS files the brick doesn't vendor for you:

```bash
./scripts/fetch-webui-libs.sh apps/06-web-dashboard
```

That downloads `socket.io.min.js` and `arduino.js` from Arduino's official
examples repo into `assets/libs/`. They're gitignored — third-party code, and
you want whatever version matches your board's brick.

## Run it

This app has four parts, so App Lab's copy/paste flow needs all of them:

- `python/main.py` → the app's Python file
- `sketch/sketch.ino` → the app's sketch
- `assets/` → the app's assets folder (`index.html`, `app.js`, `style.css`, `libs/`)
- and in app settings, add the brick from `app.yaml`:
  ```yaml
  bricks:
    - arduino:web_ui
  ```

## Opening it

The `web_ui` brick serves on **port 7000**, published on all interfaces:

```
http://<board-ip>:7000
```

So from any machine on the same network, e.g. `http://192.168.1.42:7000`. On the
board itself, `http://localhost:7000`. App Lab also has a button to open it.

Confirm it's up without a browser:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<board-ip>:7000/
```

`200` means the page is being served and the problem is elsewhere.

## What you should see

A dark/light-aware page with a live A0 voltage readout, a rolling 200-sample
chart, and a button that toggles the onboard LED. The console reports a
heartbeat every 10 seconds:

```
Browser connected (1 active)
1204 samples from MCU, 1 browser(s) connected, A0 = 1.652 V
LED -> on (from browser)
```

Turn a pot on A0 and the trace moves. Press the button and `LED_BUILTIN`
changes — that's a browser click travelling through Python, over the Bridge, to
a `digitalWrite` on the STM32.

## Both directions

**Up (MCU → browser).** The sketch pushes A0 with `Bridge.notify()`; Python
buffers the latest value and forwards it at 10 Hz with
`ui.send_message("telemetry", {...})`.

**Down (browser → MCU).** The page calls `ui.send_message('toggle_led')`; Python's
`ui.on_message("toggle_led", ...)` handler fires and does `Bridge.call("set_led", state)`.

The brick also does plain HTTP if you'd rather:

```python
ui.expose_api(method="POST", path="/my_endpoint", function=handler)
```

## Design notes

- **The chart is hand-rolled canvas**, not a charting library. No CDN, nothing
  to vendor, and the whole page stays a few KB.
- **Python skips serialising when `clients == 0`.** No point formatting JSON
  nobody will receive.
- **Scaling constants come from the sketch** via `adc_config`, so ADC resolution
  is defined in exactly one place.

## If it fails

- **Browser can't connect at all** — check the port is 7000, and that the app is
  actually running (`./scripts/app.sh status`). The container publishes
  `0.0.0.0:7000->7000/tcp`; verify with `docker ps` on the board.
- **Page loads but stays "disconnected"** — `libs/` is missing. Run
  `fetch-webui-libs.sh`.
- **`WebUI is not defined` in the browser console** — same cause; `arduino.js`
  didn't load.
- **Page connects but no data** — the Bridge is down, not the UI. Run app 02.
- **Button does nothing** — check the Python console. If you see `LED -> on` but
  the LED doesn't change, the problem is in the sketch; if you see nothing, the
  WebSocket message isn't arriving.
