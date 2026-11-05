#!/usr/bin/env bash
# Fixify local development launcher (Linux, macOS, Git Bash / WSL).
#
#   ./fixify.sh            interactive menu
#   ./fixify.sh start      start the whole local stack (with health checks)
#   ./fixify.sh stop       stop it (database data is always kept)
#   ./fixify.sh --help     all commands
#
# A thin wrapper: the launcher itself is scripts/launcher/fixify.py (standard-library Python),
# shared with fixify.ps1 so both platforms behave the same.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$ROOT/scripts/launcher/fixify.py"

# Prefer the API virtual environment; fall back to a system Python so that 'status' and
# '--help' still work before the virtual environment exists.
PYTHON=""
for candidate in \
    "$ROOT/services/api/.venv/bin/python" \
    "$ROOT/services/api/.venv/Scripts/python.exe" \
    python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[XX] Python 3.12+ was not found." >&2
    echo "     Install it (python.org, your package manager, or Homebrew) and create the API venv:" >&2
    echo "     cd services/api && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

export FIXIFY_WRAPPER=sh
export PYTHONIOENCODING=utf-8
exec "$PYTHON" "$LAUNCHER" "$@"
