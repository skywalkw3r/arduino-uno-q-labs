"""Bring-up step 0 — is the Linux side healthy?

Runs on the Qualcomm MPU. No sketch, no wiring, no Bridge. If this doesn't work,
nothing else in this repo will, and the problem is the board or App Lab rather
than your code.

Prints a one-shot inventory, then blinks LED 1 through red/green/blue so you get
a visual heartbeat you can see from across the bench.

IMPORTANT — App Lab runs apps inside Docker containers. That means anything
process-scoped (hostname, IP, systemd services) reports the *container*, not the
board. Facts that come from mapped device nodes and sysfs (/dev/ttyHS1, the LED
interfaces, /proc CPU and memory) are the real host's.

This app labels which is which. For host-level checks — is arduino-router
actually running, is the eMMC filling up — use the SSH-side runner instead:

    python3 tests/run_checks.py
"""

import logging
import subprocess
import time
from pathlib import Path

from arduino.app_utils import App, Leds, Logger

logger = Logger("HelloMPU", level=logging.INFO)

# LED 1 and LED 2 are wired to the MPU, so Linux drives them directly.
# (LED 3 and LED 4 belong to the MCU — see app 01.)
COLORS = [
    ("red", (1, 0, 0)),
    ("green", (0, 1, 0)),
    ("blue", (0, 0, 1)),
]


def _read(path: str, default: str = "unavailable") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def _run(cmd: list[str]) -> str:
    """Run a command, returning its output or a readable failure string."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable ({exc.__class__.__name__})"
    return (out.stdout or out.stderr).strip() or "no output"


def in_container() -> bool:
    """App Lab runs apps under Docker, so several /proc facts are namespaced."""
    return Path("/.dockerenv").exists()


def cpu_summary() -> str:
    cores = _read("/proc/cpuinfo", "").count("processor\t:")
    # /proc/cpuinfo on this SoC carries no model-name field, so read the clock
    # from sysfs instead — it's the host's either way.
    khz = _read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "")
    speed = f" @ {int(khz) / 1_000_000:.2f} GHz" if khz.isdigit() else ""
    return f"{cores} cores{speed} (Cortex-A53)"


def memory_summary() -> str:
    meminfo = {
        line.split(":")[0]: line.split(":")[1].strip()
        for line in _read("/proc/meminfo", "").splitlines()
        if ":" in line
    }
    total = meminfo.get("MemTotal", "?")
    available = meminfo.get("MemAvailable", "?")
    return f"{total} total, {available} available"


def thermal_summary() -> str:
    """Baseline temperatures. Record these — you need them to spot throttling."""
    zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*"))
    readings = []
    for zone in zones:
        raw = _read(str(zone / "temp"), "")
        kind = _read(str(zone / "type"), "?")
        if raw.lstrip("-").isdigit():
            readings.append(f"{kind}={int(raw) / 1000:.1f}C")
    if not readings:
        return "no thermal zones exposed"
    # Only the hottest few matter for a quick eyeball.
    hottest = sorted(readings, key=lambda r: float(r.split("=")[1][:-1]), reverse=True)
    return ", ".join(hottest[:4])


def report() -> None:
    logger.info("=" * 62)
    logger.info("UNO Q — Linux side inventory")
    logger.info("=" * 62)
    logger.info("OS         : %s", _read("/etc/os-release", "").splitlines()[0] if _read("/etc/os-release", "") else "unknown")
    logger.info("Kernel     : %s", _run(["uname", "-sr"]))
    logger.info("CPU        : %s", cpu_summary())
    logger.info("Memory     : %s", memory_summary())
    logger.info("Uptime     : %s", _read("/proc/uptime", "0").split()[0] + "s")
    logger.info("Thermals   : %s", thermal_summary())
    logger.info("Storage    : %s", _run(["df", "-h", "/"]).splitlines()[-1])
    logger.info("-" * 62)
    # /dev/ttyHS1 is a mapped device node, so this one is the real host's. It's
    # the physical MPU<->MCU link the Bridge rides on.
    logger.info("ttyHS1     : %s", "present" if Path("/dev/ttyHS1").exists() else "MISSING")
    logger.info("LED sysfs  : %s", "present" if Path("/sys/class/leds/red:user").exists() else "MISSING")

    if in_container():
        # Deliberately not printing hostname/IP/systemctl here: under Docker
        # they describe the container and read as alarming nonsense.
        logger.info("-" * 62)
        logger.info("Running under Docker (normal for App Lab).")
        logger.info("Host-level checks — router service, disk, network — live in")
        logger.info("tests/run_checks.py, which you run over SSH on the board.")
    else:
        logger.info("Router     : %s", _run(["systemctl", "is-active", "arduino-router"]))
        logger.info("Network    : %s", _run(["hostname", "-I"]) or "no address")
        logger.info("Hostname   : %s", _run(["hostname"]))
    logger.info("=" * 62)
    logger.info("Now cycling LED 1 — you should see red, green, blue on repeat.")


def all_off() -> None:
    Leds.set_led1_color(0, 0, 0)
    Leds.set_led2_color(0, 0, 0)


report()
all_off()

step = 0


def loop() -> None:
    """Visual heartbeat: LED 1 cycles R -> G -> B, one second each."""
    global step
    name, rgb = COLORS[step % len(COLORS)]
    Leds.set_led1_color(*rgb)
    logger.info("LED 1 -> %s", name)
    step += 1
    time.sleep(1)


App.run(user_loop=loop)
