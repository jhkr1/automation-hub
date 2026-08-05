#!/usr/bin/env bash

set -u
set -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PYTHON="$REPO_ROOT/.venv/bin/python"
export PATH="$REPO_ROOT/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/namuwiki_trend.log"
LOCK_FILE="$LOG_DIR/namuwiki_trend.lock"
TIMEOUT_SECONDS="${NAMUWIKI_TREND_TIMEOUT_SECONDS:-600}"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

child_pid=""
SECONDS=0

finish() {
    local status="$1"
    local end_time
    end_time="$(date --iso-8601=seconds)"
    echo "[$end_time] end exit_code=$status elapsed_seconds=$SECONDS"
    exit "$status"
}

require_env() {
    local required_name
    for required_name in "$@"; do
        if [[ -z "${!required_name:-}" ]]; then
            echo "[$(date --iso-8601=seconds)] failed: required environment is missing: $required_name"
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
    echo "[$(date --iso-8601=seconds)] interrupted signal=$signal"
    finish "$exit_code"
}

trap 'forward_signal TERM 143' TERM
trap 'forward_signal INT 130' INT

start_time="$(date --iso-8601=seconds)"
echo "[$start_time] start"

if [[ "$#" -ne 2 || "$1" != "--key-profile" || ( "$2" != "production" && "$2" != "test" ) ]]; then
    echo "usage: $0 --key-profile production|test" >&2
    finish 2
fi
key_profile="$2"

if ! [[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "[$(date --iso-8601=seconds)] failed: invalid timeout configuration"
    finish 78
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date --iso-8601=seconds)] skipped: another run is active"
    exit 75
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "[$(date --iso-8601=seconds)] failed: Python not found: $PYTHON"
    exit 78
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
    echo "[$(date --iso-8601=seconds)] failed: .env not found"
    exit 78
fi

cd "$REPO_ROOT"
set -a
# .env 값은 자식 프로세스에만 전달하며 로그에 출력하지 않는다.
# shellcheck disable=SC1091
if ! . "$REPO_ROOT/.env"; then
    echo "[$(date --iso-8601=seconds)] failed: could not load .env"
    finish 78
fi
set +a

export APP_ENV="$key_profile"
if [[ "$key_profile" == "production" ]]; then
    require_env GEMINI_NAMUWIKI_API_KEY_PROD
else
    require_env GEMINI_NAMUWIKI_API_KEY_TEST
fi

timeout --signal=TERM --kill-after=30s "${TIMEOUT_SECONDS}s" \
    "$PYTHON" -m namuwiki_trend.main --key-profile "$key_profile" &
child_pid="$!"
wait "$child_pid"
status="$?"
child_pid=""

finish "$status"
