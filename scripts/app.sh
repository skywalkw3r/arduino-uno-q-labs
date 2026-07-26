#!/usr/bin/env bash
# Start / stop / inspect App Lab apps.
#
#   ./scripts/app.sh start apps/00-hello-mpu
#   ./scripts/app.sh stop  apps/00-hello-mpu
#   ./scripts/app.sh logs  apps/00-hello-mpu
#   ./scripts/app.sh status
#   ./scripts/app.sh stop-all
#
# Runs on the board. From your laptop, set UNOQ_HOST and it forwards over SSH:
#
#   export UNOQ_HOST=arduino@<board-ip>
#   ./scripts/app.sh start apps/00-hello-mpu
#
# The work must happen on the board because arduino-app-cli and the Docker
# daemon are there. Your laptop's `arduino-cli` is a different tool and has no
# `app` subcommand.
#
# Each app gets a compose project at <app>/.cache/app-compose.yaml, which is how
# it gets stopped. If that file is deleted while the app runs, the container is
# orphaned — this wrapper verifies the stop actually took effect and cleans up
# directly when it didn't.

set -uo pipefail

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
  exit "${1:-1}"
}

CMD="${1:-}"
APP="${2:-}"

[[ -z "${CMD}" || "${CMD}" == "-h" || "${CMD}" == "--help" ]] && usage 0

# Not on the board? Forward the whole invocation over SSH rather than failing
# with a confusing "command not found".
if ! command -v arduino-app-cli >/dev/null 2>&1; then
  if [[ -z "${UNOQ_HOST:-}" ]]; then
    cat >&2 <<'EOF'
error: arduino-app-cli not found — this script does its work on the board.

Either run it there:
    ssh arduino@<board-ip> 'cd arduino-uno-q-labs && ./scripts/app.sh start apps/00-hello-mpu'

or point it at the board from here:
    export UNOQ_HOST=arduino@<board-ip>
    ./scripts/app.sh start apps/00-hello-mpu

(Your local `arduino-cli` is the classic Arduino CLI — a different tool, with no
`app` subcommand. The UNO Q's is `arduino-app-cli`.)
EOF
    exit 1
  fi

  # Quote each argument so app paths with spaces survive the trip.
  remote_args=""
  for a in "$@"; do remote_args+=" $(printf '%q' "$a")"; done

  # Allocate a TTY only when we have one, so `logs` stays interruptible with
  # Ctrl-C but piped/scripted use doesn't emit a pseudo-terminal warning.
  # Written as two branches rather than an array: macOS ships bash 3.2, where
  # expanding an empty array under `set -u` is itself an error.
  remote_cmd="cd ${UNOQ_DIR:-arduino-uno-q-labs} && ./scripts/app.sh${remote_args}"
  if [[ -t 0 ]]; then
    exec ssh -t "${UNOQ_HOST}" "${remote_cmd}"
  else
    exec ssh "${UNOQ_HOST}" "${remote_cmd}"
  fi
fi

need_app() {
  if [[ -z "${APP}" ]]; then
    echo "error: this command needs an app directory, e.g. apps/00-hello-mpu" >&2
    exit 1
  fi
  if [[ ! -f "${APP}/app.yaml" ]]; then
    echo "error: ${APP} doesn't look like an app (no app.yaml)" >&2
    exit 1
  fi
  APP_ABS="$(cd "${APP}" && pwd)"
  COMPOSE="${APP_ABS}/.cache/app-compose.yaml"
}

# Containers belonging to this app, found by compose label rather than by
# guessing at the generated name.
app_containers() {
  docker ps -q --filter "label=com.docker.compose.project.working_dir=${APP_ABS}/.cache"
}

case "${CMD}" in
  start)
    need_app
    arduino-app-cli app start "${APP}"
    ;;

  stop)
    need_app
    # Note the compose project name before anything is torn down — it's how we
    # find the network afterwards.
    project="$(docker ps --filter "label=com.docker.compose.project.working_dir=${APP_ABS}/.cache" \
      --format '{{.Label "com.docker.compose.project"}}' | head -1)"

    # Ask the CLI first, so its registry marks the app stopped.
    arduino-app-cli app stop "${APP}" >/dev/null 2>&1

    if [[ -n "$(app_containers)" ]]; then
      if [[ -f "${COMPOSE}" ]]; then
        echo "CLI left it running — bringing the compose project down"
        docker compose -f "${COMPOSE}" down 2>&1 | sed 's/^/  /'
      else
        # `app stop` deletes .cache/app-compose.yaml without stopping the
        # container, so this is the usual path, not the rare one.
        echo "CLI left it running and removed its compose file — cleaning up directly"
        docker rm -f $(app_containers) >/dev/null 2>&1
        if [[ -n "${project}" ]] && docker network inspect "${project}_default" >/dev/null 2>&1; then
          docker network rm "${project}_default" >/dev/null 2>&1 \
            && echo "  removed network ${project}_default"
        fi
      fi
    fi

    sleep 1
    if [[ -n "$(app_containers)" ]]; then
      echo "FAILED — still running:" >&2
      docker ps --filter "label=com.docker.compose.project.working_dir=${APP_ABS}/.cache" \
        --format '  {{.Names}}  {{.Status}}' >&2
      exit 1
    fi
    echo "stopped: ${APP}"
    ;;

  logs)
    need_app
    ids="$(app_containers)"
    if [[ -z "${ids}" ]]; then
      echo "not running: ${APP}" >&2
      exit 1
    fi
    # docker logs directly, because `arduino-app-cli app logs` follows forever
    # and has no --tail.
    docker logs --tail "${3:-40}" -f ${ids}
    ;;

  status)
    echo "Running app containers:"
    if [[ -z "$(docker ps -q)" ]]; then
      echo "  (none)"
    else
      docker ps --format '  {{.Names}}\t{{.Status}}'
    fi
    echo
    echo "CLI registry (non-example apps):"
    arduino-app-cli app list 2>/dev/null | awk 'NR==1 || $0 !~ /examples:/' | sed 's/^/  /'
    ;;

  stop-all)
    running="$(docker ps -q)"
    if [[ -z "${running}" ]]; then
      echo "nothing running"
      exit 0
    fi
    # Group by compose project so each app's network is cleaned up too.
    docker ps --format '{{.Label "com.docker.compose.project.config_files"}}' \
      | sort -u | while read -r compose_file; do
        [[ -f "${compose_file}" ]] || continue
        echo "stopping $(dirname "$(dirname "${compose_file}")")"
        docker compose -f "${compose_file}" down 2>&1 | sed 's/^/  /'
      done

    # Fallback: an app's sidecar (e.g. the llamacpp-models-runner) can outlive
    # its compose file once the app shuts down, so `docker compose down` above
    # can't find it. Sweep up anything still running that belongs to an app.
    strays="$(docker ps -q --filter 'label=com.docker.compose.project')"
    if [[ -n "${strays}" ]]; then
      echo "removing $(echo "${strays}" | wc -l | tr -d ' ') straggler container(s)"
      docker rm -f ${strays} >/dev/null 2>&1
    fi

    remaining="$(docker ps -q | wc -l | tr -d ' ')"
    echo "done — ${remaining} container(s) still running"
    ;;

  *)
    echo "error: unknown command '${CMD}'" >&2
    usage 1
    ;;
esac
