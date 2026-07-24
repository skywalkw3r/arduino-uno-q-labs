#!/usr/bin/env bash
# Board inventory — run this ON the UNO Q.
#
#   ssh <user>@unoq.local 'bash -s' < scripts/board-info.sh
#
# Everything here is read-only. Capture the output on a healthy board and keep
# it: a known-good baseline is what makes the next problem diagnosable.

set -uo pipefail   # deliberately no -e; a missing tool shouldn't abort the report

section() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# Print "key: value", or a placeholder if the command fails.
try() {
  local label="$1"; shift
  local out
  if out=$("$@" 2>/dev/null) && [[ -n "${out}" ]]; then
    printf '%-14s %s\n' "${label}:" "${out}"
  else
    printf '%-14s %s\n' "${label}:" "(unavailable)"
  fi
}

section "Identity"
try "Hostname" hostname
try "Kernel" uname -sr
try "Arch" uname -m
if [[ -r /etc/os-release ]]; then
  printf '%-14s %s\n' "OS:" "$(. /etc/os-release && echo "${PRETTY_NAME}")"
fi
try "Uptime" uptime -p

section "CPU and memory"
if have lscpu; then
  lscpu | grep -E '^(Model name|CPU\(s\)|CPU max MHz|Architecture)' || true
fi
if have free; then
  free -h
fi

section "Storage"
df -h / /var 2>/dev/null | grep -vE '^(tmpfs|devtmpfs)' || true

section "Thermals"
# Record your idle numbers. Without a baseline you can't tell throttling from
# a software regression later.
found_zone=0
for zone in /sys/class/thermal/thermal_zone*; do
  [[ -r "${zone}/temp" ]] || continue
  temp=$(cat "${zone}/temp" 2>/dev/null) || continue
  type=$(cat "${zone}/type" 2>/dev/null || echo "?")
  awk -v t="${temp}" -v n="${type}" 'BEGIN { printf "%-24s %.1f C\n", n, t/1000 }'
  found_zone=1
done
[[ "${found_zone}" -eq 1 ]] || echo "(no thermal zones exposed)"

section "Bridge / router"
# This is the service that makes Python <-> MCU work. If it isn't active,
# every app from 02 onwards will fail.
try "Router" systemctl is-active arduino-router
if [[ -e /dev/ttyHS1 ]]; then
  echo "ttyHS1:        present (reserved by arduino-router — do not open it)"
else
  echo "ttyHS1:        MISSING"
fi

section "App Lab"
if have arduino-app-cli; then
  try "CLI version" arduino-app-cli version
  echo
  echo "Subcommands available on this build:"
  arduino-app-cli --help 2>&1 | sed -n '1,40p'
else
  echo "(arduino-app-cli not on PATH)"
fi

section "LEDs"
if [[ -d /sys/class/leds ]]; then
  ls /sys/class/leds
else
  echo "(no /sys/class/leds)"
fi

section "Network"
try "Addresses" hostname -I
if have nmcli; then
  nmcli -t -f DEVICE,TYPE,STATE device 2>/dev/null | column -t -s: || true
fi

section "Containers"
if have docker; then
  try "Docker" docker --version
  docker ps --format '  {{.Names}}\t{{.Status}}' 2>/dev/null || echo "  (cannot list — permissions?)"
else
  echo "(docker not on PATH)"
fi

section "Cameras"
if compgen -G '/dev/video*' >/dev/null; then
  ls -1 /dev/video*
else
  echo "(no /dev/video* — needed for app 07)"
fi

printf '\n\033[1m== Done\033[0m\n'
echo "Save this output. It is your known-good baseline."
