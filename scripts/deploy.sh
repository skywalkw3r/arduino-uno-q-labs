#!/usr/bin/env bash
# Copy this repo's apps onto a UNO Q over SSH.
#
#   ./scripts/deploy.sh unoq.local
#   ./scripts/deploy.sh user@192.168.1.42
#   REMOTE_DIR=/home/me/lab ./scripts/deploy.sh unoq.local
#
# Unpacks over the existing tree so a running app's <app>/.cache survives.
# Use --clean for a fresh sync; it refuses while containers are up.

set -euo pipefail

HOST="${1:-}"
REMOTE_DIR="${REMOTE_DIR:-arduino-uno-q-labs}"

if [[ -z "${HOST}" ]]; then
  cat >&2 <<'USAGE'
usage: ./scripts/deploy.sh <host> [--dry-run] [--clean]

  <host>      ssh target, e.g. unoq.local or arduino@192.168.1.42
  --dry-run   show what would be copied, write nothing
  --clean     wipe the remote tree first. Refuses while apps are running,
              because it would delete their .cache and orphan the containers.

env:
  REMOTE_DIR   destination path on the board (default: arduino-uno-q-labs)
USAGE
  exit 1
fi

DRY_RUN=""
CLEAN=""
for arg in "${@:2}"; do
  case "${arg}" in
    --dry-run) DRY_RUN="--dry-run" ;;
    --clean)   CLEAN=1 ;;
    *) echo "error: unknown flag '${arg}'" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> checking ssh to ${HOST}"
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${HOST}" true 2>/dev/null; then
  echo "error: cannot ssh to ${HOST} without a password." >&2
  echo "  Set up a key first:  ssh-copy-id ${HOST}" >&2
  echo "  If the hostname doesn't resolve, the board may not be advertising over" >&2
  echo "  mDNS — try its IP address instead." >&2
  exit 1
fi

EXCLUDES=(.git __pycache__ .pytest_cache .DS_Store)

# The UNO Q's Debian image ships without rsync, so fall back to tar over ssh.
# Same result, minus the incremental transfer.
if ssh -o BatchMode=yes "${HOST}" 'command -v rsync >/dev/null 2>&1'; then
  echo "==> syncing to ${HOST}:${REMOTE_DIR} (rsync)"
  rsync -av ${DRY_RUN} --delete \
    "${EXCLUDES[@]/#/--exclude=}" \
    "${REPO_ROOT}/" "${HOST}:${REMOTE_DIR}/"

  if [[ -n "${DRY_RUN}" ]]; then
    echo
    echo "(dry run — nothing was written)"
    exit 0
  fi
else
  echo "==> no rsync on the board, using tar over ssh"

  if [[ -n "${DRY_RUN}" ]]; then
    echo "would copy:"
    # COPYFILE_DISABLE stops macOS bsdtar emitting a ._ AppleDouble file
  # alongside every entry, which would litter the board.
  COPYFILE_DISABLE=1 tar -c -f - -C "${REPO_ROOT}" "${EXCLUDES[@]/#/--exclude=}" . | tar -t -f - | sed 's|^\./|  |'
    echo
    echo "(dry run — nothing was written)"
    exit 0
  fi

  # Unpack over the existing tree rather than wiping it. App Lab keeps per-app
  # state in <app>/.cache (including the compose file its containers are
  # managed by), so a blind rm -rf here orphans anything that's running.
  # Use --clean when you genuinely want a fresh tree.
  if [[ -n "${CLEAN}" ]]; then
    running="$(ssh -o BatchMode=yes "${HOST}" 'docker ps -q 2>/dev/null | wc -l' | tr -d ' ')"
    if [[ "${running}" != "0" ]]; then
      echo "warning: ${running} app container(s) running — --clean will orphan them." >&2
      echo "         Stop them first:  ./scripts/app.sh stop-all" >&2
      exit 1
    fi
    ssh -o BatchMode=yes "${HOST}" "rm -rf ${REMOTE_DIR}"
  fi

  ssh -o BatchMode=yes "${HOST}" "mkdir -p ${REMOTE_DIR}"
  # COPYFILE_DISABLE stops macOS bsdtar emitting a ._ AppleDouble file
  # alongside every entry, which would litter the board.
  COPYFILE_DISABLE=1 tar -c -f - -C "${REPO_ROOT}" "${EXCLUDES[@]/#/--exclude=}" . \
    | ssh -o BatchMode=yes "${HOST}" "tar -x -f - -C ${REMOTE_DIR}"
  echo "    copied $(find "${REPO_ROOT}" -type f -not -path '*/.git/*' | wc -l | tr -d ' ') files"
fi

cat <<EOF

==> synced.

Run the bring-up checks:

  ssh ${HOST} 'cd ${REMOTE_DIR} && python3 tests/run_checks.py'

Capture a baseline inventory:

  ssh ${HOST} 'bash ${REMOTE_DIR}/scripts/board-info.sh' | tee board-baseline.txt

Start an app:

  ssh ${HOST} 'cd ${REMOTE_DIR} && arduino-app-cli app start apps/00-hello-mpu'

Or drive it from here:

  export UNOQ_HOST=${HOST}
  ./scripts/app.sh start apps/00-hello-mpu
EOF
