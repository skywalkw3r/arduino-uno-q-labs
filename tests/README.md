# Bring-up tests

Run these **on the board**. No dependencies:

```bash
python3 tests/run_checks.py
```

From your laptop after `scripts/deploy.sh`:

```bash
ssh arduino@<board-ip> 'cd arduino-uno-q-labs && python3 tests/run_checks.py'
```

## No dependencies, on purpose

The stock UNO Q image has **no pip, no venv, and no pytest**, and
`sudo apt install python3-pytest` needs a password. A bring-up suite you can't
run without first installing a package manager isn't much use.

So the checks live in [`checks.py`](checks.py) as plain stdlib functions and
[`run_checks.py`](run_checks.py) runs them. Nothing to install.

## What it covers

| Group | Checks |
|---|---|
| identity | ARM64, 4 cores, ~4 GB RAM, memory not exhausted |
| bridge | `arduino-router` active, `/dev/ttyHS1` present, not restart-looping |
| leds | all six MPU LED sysfs segments |
| storage | disk headroom for model downloads, home writable |
| thermal | zones readable, not throttling, prints the baseline |
| network | has an IP, DNS resolves |
| toolchain | `arduino-app-cli`, Python version, docker |
| hardware | camera, I²C — **skips** if absent |

Exit code is 0 when everything that ran passed, 1 on any failure. Skips don't
fail the run.

## Run it over SSH, not as an App Lab app

This matters. App Lab runs apps **inside Docker containers**, where `systemctl`,
`hostname`, and the IP address describe the container rather than the board. The
router check is meaningless in there.

`run_checks.py` is meant to run in a plain SSH session on the host, which is
where those answers are real.

## A known-good baseline

From an actual UNO Q 4 GB, idle:

```
19 passed, 0 failed, 0 skipped

identity   aarch64 · 4 cores · 3.58 GB total · 2.96 GB available
bridge     active · /dev/ttyHS1 present · 0 restarts
storage    2.9 GB free of 9.7 GB   <-- note: root is ~10 GB, not the full 32 GB eMMC
thermal    hottest cpuss0-thermal 38.4 C
toolchain  Arduino App CLI 0.12.1 · Python 3.13.5 · Docker 26.1.5
hardware   video0, video1 · i2c-0, i2c-1, i2c-2
```

Save your own:

```bash
ssh arduino@<board-ip> 'cd arduino-uno-q-labs && python3 tests/run_checks.py' | tee baseline.txt
```
