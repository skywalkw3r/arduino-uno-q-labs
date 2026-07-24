"""Bring-up step 6 — put live MCU data in a browser.

Ties together everything so far: the sketch streams A0 over the Bridge, this
side forwards it to a web page over WebSocket, and a button on that page calls
back down to the MCU to toggle the LED.

    browser  <--websocket-->  Python (MPU)  <--Bridge-->  sketch (MCU)

Uses the web_ui brick, declared in app.yaml:

    bricks:
      - arduino:web_ui

The page needs two vendored JS files in assets/libs/ — run
scripts/fetch-webui-libs.sh once to download them.
"""

import logging
import time

from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge, Logger

logger = Logger("WebDashboard", level=logging.INFO)

ui = WebUI()

PUSH_INTERVAL_S = 0.1   # 10 Hz to the browser
STATUS_EVERY_S = 10.0   # console heartbeat

adc_max = 16383
vref = 3.3

latest_raw = 0
sample_count = 0
led_on = False
clients = 0
_last_status = 0.0


def adc_config(max_counts: int, reference: float) -> None:
    """Scaling constants come from the sketch so they're defined once."""
    global adc_max, vref

    adc_max, vref = max_counts, reference
    logger.info("ADC full scale %d counts, Vref %.2f V", max_counts, reference)


def adc_sample(raw: int) -> None:
    """Called ~10x/second by the sketch."""
    global latest_raw, sample_count

    latest_raw = raw
    sample_count += 1


Bridge.provide("adc_config", adc_config)
Bridge.provide("adc_sample", adc_sample)


def on_connect(connection) -> None:
    global clients

    clients += 1
    logger.info("Browser connected (%d active)", clients)


def on_disconnect(connection) -> None:
    global clients

    clients = max(0, clients - 1)
    logger.info("Browser disconnected (%d active)", clients)


def on_toggle_led(client, data) -> None:
    """Button press in the browser -> Bridge call down to the MCU."""
    global led_on

    led_on = not led_on
    Bridge.call("set_led", led_on)
    logger.info("LED -> %s (from browser)", "on" if led_on else "off")
    ui.send_message("led_state", {"on": led_on})


ui.on_connect(on_connect)
ui.on_disconnect(on_disconnect)
ui.on_message("toggle_led", on_toggle_led)


def loop() -> None:
    global _last_status

    time.sleep(PUSH_INTERVAL_S)

    now = time.monotonic()
    if now - _last_status > STATUS_EVERY_S:
        _last_status = now
        logger.info(
            "%d samples from MCU, %d browser(s) connected, A0 = %.3f V",
            sample_count,
            clients,
            latest_raw / adc_max * vref,
        )

    if clients == 0:
        return  # nobody watching, don't bother serialising

    ui.send_message(
        "telemetry",
        {
            "raw": latest_raw,
            "volts": round(latest_raw / adc_max * vref, 4),
            "percent": round(latest_raw / adc_max * 100, 1),
            "samples": sample_count,
            "led": led_on,
        },
    )


logger.info("Dashboard starting — open the app's web UI from App Lab.")
App.run(user_loop=loop)
