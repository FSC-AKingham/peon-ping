#!/bin/bash
# peon-ping installer — thin wrapper around install.py
# Works both via `curl | bash` (downloads install.py first) and local clone
set -euo pipefail

REPO_BASE="https://raw.githubusercontent.com/tonyyont/peon-ping/main"

# Detect if running from local clone
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
  CANDIDATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  if [ -f "$CANDIDATE/install.py" ]; then
    SCRIPT_DIR="$CANDIDATE"
  fi
fi

# Find python
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: python3 or python is required"
  exit 1
fi

if [ -n "$SCRIPT_DIR" ]; then
  exec "$PYTHON" "$SCRIPT_DIR/install.py" "$@"
else
  # curl|bash mode — download install.py to a temp file and run it
  TMPFILE="$(mktemp)"
  trap 'rm -f "$TMPFILE"' EXIT
  curl -fsSL "$REPO_BASE/install.py" -o "$TMPFILE"
  exec "$PYTHON" "$TMPFILE" "$@"
fi
