"""The bring-up checks themselves — stdlib only, no third-party imports.

The stock UNO Q Debian image has no pip, no venv, and no pytest, and installing
them needs a sudo password. So the checks live here as plain stdlib functions
and tests/run_checks.py runs them — nothing to install.

Each check returns (status, detail):

    True   passed
    False  failed  — detail explains what to do about it
    None   skipped — optional hardware or an unavailable tool
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path

# --------------------------------------------------------------- helpers


def run(*cmd: str, timeout: int = 15) -> tuple[int, str]:
    """Run a command, returning (returncode, combined output)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]}: timed out"
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def meminfo_kb(key: str) -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(f"{key}:"):
            return int(re.search(r"\d+", line).group())
    raise KeyError(key)


def thermal_zones() -> dict[str, float]:
    temps: dict[str, float] = {}
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            raw = (zone / "temp").read_text().strip()
            kind = (zone / "type").read_text().strip()
        except OSError:
            continue
        if raw.lstrip("-").isdigit():
            temps[kind] = int(raw) / 1000
    return temps


def on_board() -> bool:
    """True when we're running on the UNO Q rather than a dev laptop."""
    return platform.system() == "Linux" and platform.machine() in ("aarch64", "arm64")


# ----------------------------------------------------------- the checks


def check_architecture():
    machine = platform.machine()
    if machine not in ("aarch64", "arm64"):
        return False, f"expected ARM64, got {machine} — run this on the board"
    return True, machine


def check_core_count():
    cores = Path("/proc/cpuinfo").read_text().count("processor\t:")
    if cores != 4:
        return False, f"expected 4 Cortex-A53 cores, found {cores}"
    return True, f"{cores} cores"


def check_memory_size():
    total_gb = meminfo_kb("MemTotal") / (1024 * 1024)
    if total_gb <= 3.0:
        return False, f"only {total_gb:.2f} GB visible — is this the 2 GB variant?"
    return True, f"{total_gb:.2f} GB total"


def check_memory_available():
    available_gb = meminfo_kb("MemAvailable") / (1024 * 1024)
    if available_gb <= 0.3:
        return False, f"only {available_gb:.2f} GB available — AI bricks will fail to load"
    return True, f"{available_gb:.2f} GB available"


def check_router_active():
    code, out = run("systemctl", "is-active", "arduino-router")
    if code != 0 or out != "active":
        return False, (
            f"arduino-router is '{out}' — the Bridge will not work. "
            "Fix: sudo systemctl restart arduino-router"
        )
    return True, "active"


def check_serial_transport():
    if not Path("/dev/ttyHS1").exists():
        return False, "/dev/ttyHS1 missing — the physical MPU<->MCU link is gone"
    return True, "/dev/ttyHS1 present"


def check_router_stable():
    code, out = run("systemctl", "show", "arduino-router", "--property=NRestarts")
    if code != 0:
        return None, "systemctl show unavailable"
    restarts = int(out.split("=", 1)[1] or 0)
    if restarts >= 5:
        return False, (
            f"router restarted {restarts}x — check journalctl -u arduino-router"
        )
    return True, f"{restarts} restarts"


def check_leds():
    expected = ["red:user", "green:user", "blue:user", "red:panic", "green:wlan", "blue:bt"]
    led_dir = Path("/sys/class/leds")
    if not led_dir.is_dir():
        return False, "/sys/class/leds missing"
    missing = [led for led in expected if not (led_dir / led).exists()]
    if missing:
        available = sorted(p.name for p in led_dir.iterdir())
        return False, f"missing {missing}; available: {available}"
    return True, f"all {len(expected)} segments present"


def check_disk_headroom():
    usage = shutil.disk_usage("/")
    free_gb = usage.free / (1024**3)
    total_gb = usage.total / (1024**3)
    if free_gb <= 1.0:
        return False, f"only {free_gb:.2f} GB free — brick model downloads will fail"
    # The eMMC is 32 GB but root is a ~10 GB partition, so this fills faster
    # than the spec sheet suggests.
    note = f"{free_gb:.1f} GB free of {total_gb:.1f} GB"
    if free_gb < 3.0:
        note += "  (tight — AI models are large)"
    return True, note


def check_root_writable():
    probe = Path.home() / ".arduino-uno-q-labs-write-probe"
    try:
        probe.write_text("ok")
        content = probe.read_text()
        probe.unlink()
    except OSError as exc:
        return False, f"cannot write to home: {exc}"
    return (content == "ok"), "writable"


def check_thermals_readable():
    zones = thermal_zones()
    if not zones:
        return False, "no readable thermal zones"
    return True, f"{len(zones)} zones"


def check_not_throttling():
    zones = thermal_zones()
    if not zones:
        return None, "no thermal zones"
    name, hottest = max(zones.items(), key=lambda kv: kv[1])
    if hottest >= 95.0:
        return False, f"{name} at {hottest:.1f} C — throttling, add cooling"
    return True, f"hottest {name} {hottest:.1f} C"


def check_has_address():
    code, out = run("hostname", "-I")
    if code != 0 or not out.strip():
        return False, "no IP address — Network Mode and model downloads need this"
    return True, out.split()[0]


def check_dns():
    code, _ = run("getent", "hosts", "downloads.arduino.cc")
    if code == 127:
        return None, "getent unavailable"
    if code != 0:
        return False, "cannot resolve downloads.arduino.cc — bricks can't fetch models"
    return True, "resolves"


def check_app_cli():
    if not shutil.which("arduino-app-cli"):
        return False, "arduino-app-cli not on PATH — is App Lab installed?"
    code, out = run("arduino-app-cli", "version")
    version = out.splitlines()[0] if out else "unknown"
    return True, version


def check_python_version():
    import sys

    if sys.version_info < (3, 9):
        return False, f"Python {platform.python_version()} is older than expected"
    return True, f"Python {platform.python_version()}"


def check_docker():
    if not shutil.which("docker"):
        return None, "docker not installed"
    code, out = run("docker", "info")
    if code != 0:
        first = out.splitlines()[0] if out else "?"
        return None, f"present but not usable: {first}"
    code, ver = run("docker", "--version")
    return True, ver


def check_camera():
    cameras = sorted(p.name for p in Path("/dev").glob("video*"))
    if not cameras:
        return None, "no /dev/video* — app 07 needs a camera"
    return True, ", ".join(cameras)


def check_i2c_devices():
    buses = sorted(p.name for p in Path("/dev").glob("i2c-*"))
    if not buses:
        return None, "no /dev/i2c-* (the MCU owns the header buses)"
    return True, ", ".join(buses)


# Ordered so the most diagnostic failures surface first.
CHECKS: list[tuple[str, str, callable]] = [
    ("identity", "ARM64 architecture", check_architecture),
    ("identity", "4 CPU cores", check_core_count),
    ("identity", "memory size (4 GB variant)", check_memory_size),
    ("identity", "memory not exhausted", check_memory_available),
    ("bridge", "arduino-router active", check_router_active),
    ("bridge", "MPU<->MCU serial transport", check_serial_transport),
    ("bridge", "router not restart-looping", check_router_stable),
    ("leds", "MPU LED interfaces", check_leds),
    ("storage", "disk headroom for models", check_disk_headroom),
    ("storage", "home directory writable", check_root_writable),
    ("thermal", "thermal zones readable", check_thermals_readable),
    ("thermal", "not throttling", check_not_throttling),
    ("network", "has an IP address", check_has_address),
    ("network", "DNS resolves", check_dns),
    ("toolchain", "arduino-app-cli present", check_app_cli),
    ("toolchain", "Python version", check_python_version),
    ("toolchain", "docker usable", check_docker),
    ("hardware", "camera", check_camera),
    ("hardware", "I2C devices", check_i2c_devices),
]
