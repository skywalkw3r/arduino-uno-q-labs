#!/usr/bin/env bash
# Download the two JS files the web_ui brick's pages expect.
#
# The official Arduino examples vendor these into each app's assets/libs/. They
# are third-party code, so this repo gitignores them and fetches them on demand
# instead of committing a copy that will drift.
#
# Usage: ./scripts/fetch-webui-libs.sh [app-dir]
#        defaults to apps/06-web-dashboard

set -euo pipefail

APP_DIR="${1:-apps/06-web-dashboard}"
LIBS_DIR="${APP_DIR}/assets/libs"

BASE_URL="https://raw.githubusercontent.com/arduino/app-bricks-examples/main/core-and-foundational/08-web-ui-basics/02-data-transmission/assets/libs"

if [[ ! -d "${APP_DIR}" ]]; then
  echo "error: no such app directory: ${APP_DIR}" >&2
  echo "usage: $0 [app-dir]" >&2
  exit 1
fi

mkdir -p "${LIBS_DIR}"

for lib in socket.io.min.js arduino.js; do
  echo "fetching ${lib} ..."
  if ! curl -fsSL "${BASE_URL}/${lib}" -o "${LIBS_DIR}/${lib}"; then
    echo "error: failed to download ${lib}" >&2
    echo "  Arduino may have moved the examples repo layout. Fall back to" >&2
    echo "  copying assets/libs/ out of any web_ui example in App Lab." >&2
    exit 1
  fi
done

echo
echo "done — ${LIBS_DIR} now contains:"
ls -la "${LIBS_DIR}"
