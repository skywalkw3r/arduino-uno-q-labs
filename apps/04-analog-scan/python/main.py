"""Bring-up step 4 — verify the 14-bit ADC on A0..A5.

The sketch streams all six channels at 10 Hz. This side converts counts to
volts, tracks min/mean/max per channel, and draws a live bar for A0 so you can
watch a potentiometer sweep in the console.

Wiring (optional):
    3.3V ── pot leg 1
    A0   ── pot wiper
    GND  ── pot leg 3

⚠️ Use the 3.3V pin, not 5V. The ADC reference is 3.3 V and the pins are not
5 V tolerant.

Unconnected channels float and will show noise. That's expected — it's what a
floating input looks like, and it's useful to see once so you recognise it.
"""

import logging
import time

from arduino.app_utils import App, Bridge, Logger

logger = Logger("AnalogScan", level=logging.INFO)

REPORT_INTERVAL_S = 1.0
BAR_WIDTH = 40

# Overwritten by the sketch's adc_config notification.
adc_max = 16383
vref = 3.3
num_channels = 6

# Per-channel running stats, reset after each report.
stats: list[dict[str, float]] = []
sample_count = 0


def _reset_stats() -> None:
    global stats
    stats = [
        {"min": float("inf"), "max": float("-inf"), "sum": 0.0, "n": 0}
        for _ in range(num_channels)
    ]


def adc_config(max_counts: int, reference: float, channels: int) -> None:
    """The sketch owns the ADC constants and reports them once at startup."""
    global adc_max, vref, num_channels

    adc_max, vref, num_channels = max_counts, reference, channels
    _reset_stats()
    logger.info(
        "ADC: %d channels, full scale %d counts, Vref %.2f V (%.3f mV/count)",
        channels,
        max_counts,
        reference,
        reference / max_counts * 1000,
    )


def adc_samples(samples: list[int]) -> None:
    """Called ~10x/second with one reading per channel."""
    global sample_count

    if len(stats) != len(samples):
        _reset_stats()

    for i, raw in enumerate(samples):
        s = stats[i]
        s["min"] = min(s["min"], raw)
        s["max"] = max(s["max"], raw)
        s["sum"] += raw
        s["n"] += 1

    sample_count += 1


Bridge.provide("adc_config", adc_config)
Bridge.provide("adc_samples", adc_samples)

_reset_stats()


def to_volts(counts: float) -> float:
    return counts / adc_max * vref


def bar(counts: float) -> str:
    filled = int(counts / adc_max * BAR_WIDTH)
    return "█" * filled + "·" * (BAR_WIDTH - filled)


def loop() -> None:
    time.sleep(REPORT_INTERVAL_S)

    if sample_count == 0:
        logger.warning("No samples from the sketch yet — is the Bridge up?")
        return

    logger.info("─" * 72)
    for i, s in enumerate(stats):
        if s["n"] == 0:
            continue
        mean = s["sum"] / s["n"]
        logger.info(
            "A%d  %5.0f cnt  %5.3f V   min %5.0f  max %5.0f  spread %4.0f",
            i,
            mean,
            to_volts(mean),
            s["min"],
            s["max"],
            s["max"] - s["min"],
        )

    if stats[0]["n"]:
        a0_mean = stats[0]["sum"] / stats[0]["n"]
        logger.info("A0 |%s| %.3f V", bar(a0_mean), to_volts(a0_mean))

    _reset_stats()


logger.info("Sampling A0..A5. Turn a pot on A0 and watch the bar move.")
App.run(user_loop=loop)
