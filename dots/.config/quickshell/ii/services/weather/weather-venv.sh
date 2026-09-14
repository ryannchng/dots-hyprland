#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ILLOGICAL_IMPULSE_VIRTUAL_ENV:-${XDG_STATE_HOME:-$HOME/.local/state}/quickshell/.venv}"
VENV="${VENV/#\~/$HOME}"

# The Quickshell installer places Python dependencies in this shared venv.
# exec keeps the wrapper transparent to Quickshell and preserves all arguments.
source "$VENV/bin/activate"
exec python3 "$SCRIPT_DIR/weather.py" "$@"
