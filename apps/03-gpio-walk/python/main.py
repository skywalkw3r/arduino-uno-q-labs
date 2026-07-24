"""Bring-up step 3 — verify every digital output pin on the header.

Walks a single HIGH across D2..D13, one pin at a time, and logs the sketch's
confirmation of what it actually drove. Move one LED (with a series resistor)
down the header and you can check every pin in about 15 seconds.

⚠️ The header pins are 3.3 V. Never connect a 5 V source to them.

Wiring (optional but this is the point of the app):
    D<n> ──[220 Ω]──▶|── GND        (LED anode to the pin, cathode to GND)
"""

import logging
import time

from arduino.app_utils import App, Bridge, Logger

logger = Logger("GpioWalk", level=logging.INFO)

DWELL_S = 1.0        # how long each pin stays HIGH
PAUSE_AT_END_S = 2.0  # blank gap so you can see the sequence restart

# Overwritten by the sketch's gpio_ready notification.
first_pin = 2
last_pin = 13

index = 0
sweeps = 0
confirmations = 0


def gpio_ready(first: int, last: int) -> None:
    """The sketch reports its own pin range so nothing is hardcoded twice."""
    global first_pin, last_pin, index

    first_pin, last_pin = first, last
    index = 0
    logger.info("Sketch reports pin range D%d..D%d", first, last)


def gpio_active(pin: int) -> None:
    """The sketch confirms which pin it actually drove."""
    global confirmations

    if pin < 0:
        logger.info("  ... all pins low")
    else:
        confirmations += 1
        logger.info("  D%-2d HIGH", pin)


Bridge.provide("gpio_ready", gpio_ready)
Bridge.provide("gpio_active", gpio_active)


def loop() -> None:
    global index, sweeps

    pins = list(range(first_pin, last_pin + 1))

    if index >= len(pins):
        # End of a sweep: blank everything, pause, start over.
        Bridge.call("set_active_pin", -1)
        sweeps += 1
        logger.info(
            "Sweep %d complete — %d/%d pins confirmed by the sketch",
            sweeps,
            confirmations,
            len(pins) * sweeps,
        )
        index = 0
        time.sleep(PAUSE_AT_END_S)
        return

    Bridge.call("set_active_pin", pins[index])
    index += 1
    time.sleep(DWELL_S)


logger.info("Walking D%d..D%d, %.1fs per pin. Follow along with an LED.", first_pin, last_pin, DWELL_S)
App.run(user_loop=loop)
