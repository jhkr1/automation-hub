#!/usr/bin/env bash

set -u
set -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PYTHON="$REPO_ROOT/.venv/bin/python"
TARGET_ID="2"
export PATH="$REPO_ROOT/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/bus_monitor.log"
LOCK_FILE="$LOG_DIR/bus_monitor_target_${TARGET_ID}.lock"
TIMEOUT_SECONDS="${BUS_MONITOR_TIMEOUT_SECONDS:-600}"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

child_pid=""
SECONDS=0

finish() {
    local status="$1"
    echo "[$(date --iso-8601=seconds)] end target_id=$TARGET_ID exit_code=$status elapsed_seconds=$SECONDS"
    exit "$status"
}

require_env() {
    local required_name
    for required_name in "$@"; do
        if [[ -z "${!required_name:-}" ]]; then
            echo "[$(date --iso-8601=seconds)] failed target_id=$TARGET_ID missing_env=$required_name"
            finish 78
        fi
    done
}

forward_signal() {
    local signal="$1"
    local exit_code="$2"
    if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
        kill "-$signal" "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    echo "[$(date --iso-8601=seconds)] interrupted target_id=$TARGET_ID signal=$signal"
    finish "$exit_code"
}

trap 'forward_signal TERM 143' TERM
trap 'forward_signal INT 130' INT

if [[ "$#" -ne 0 ]]; then
    echo "usage: $0" >&2
    finish 2
fi

echo "[$(date --iso-8601=seconds)] start target_id=$TARGET_ID"

if ! [[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "[$(date --iso-8601=seconds)] failed target_id=$TARGET_ID invalid_timeout"
    finish 78
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date --iso-8601=seconds)] skipped target_id=$TARGET_ID reason=lock_held"
    finish 75
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "[$(date --iso-8601=seconds)] failed target_id=$TARGET_ID python_not_found"
    finish 78
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
    echo "[$(date --iso-8601=seconds)] failed target_id=$TARGET_ID env_not_found"
    finish 78
fi

cd "$REPO_ROOT"
set -a
# .env values are passed only to the child process and are never printed.
# shellcheck disable=SC1091
if ! . "$REPO_ROOT/.env"; then
    echo "[$(date --iso-8601=seconds)] failed target_id=$TARGET_ID env_load_failed"
    finish 78
fi
set +a

require_env DATABASE_URL ODSAY_API_KEY GYEONGGI_SERVICE_KEY

timeout --signal=TERM --kill-after=30s "${TIMEOUT_SECONDS}s" \
    "$PYTHON" -m bus_monitor.main --target-id "$TARGET_ID" &
child_pid="$!"
wait "$child_pid"
status="$?"
child_pid=""

finish "$status"
