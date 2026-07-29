#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/namuwiki_trend.log"
LOCK_FILE="$LOG_DIR/namuwiki_trend.lock"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

start_epoch="$(date +%s)"
start_time="$(date --iso-8601=seconds)"
echo "[$start_time] start"

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
. "$REPO_ROOT/.env"
set +a

"$PYTHON" -m namuwiki_trend.main
status=$?

end_epoch="$(date +%s)"
end_time="$(date --iso-8601=seconds)"
echo "[$end_time] end exit_code=$status elapsed_seconds=$((end_epoch - start_epoch))"
exit "$status"
