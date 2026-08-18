#!/usr/bin/env bash

set -u
set -o pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
STREAMLIT="$REPO_ROOT/.venv/bin/streamlit"

if [[ ! -x "$STREAMLIT" ]]; then
    echo "Dashboard Streamlit executable was not found: $STREAMLIT" >&2
    exit 78
fi

cd "$REPO_ROOT"
# Dashboard packages use the repository's flat layout. Do not inherit an unrelated shell path.
export PYTHONPATH="$REPO_ROOT"
export PATH="$REPO_ROOT/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

exec "$STREAMLIT" run "$REPO_ROOT/automation_dashboard/app.py" "$@"
