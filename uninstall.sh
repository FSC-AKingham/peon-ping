#!/bin/bash
# peon-ping uninstaller — thin wrapper around uninstall.py
set -euo pipefail

INSTALL_DIR="$HOME/.claude/hooks/peon-ping"

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

if [ -f "$INSTALL_DIR/uninstall.py" ]; then
  exec "$PYTHON" "$INSTALL_DIR/uninstall.py" "$@"
else
  # Fallback: try local copy
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  if [ -f "$SCRIPT_DIR/uninstall.py" ]; then
    exec "$PYTHON" "$SCRIPT_DIR/uninstall.py" "$@"
  else
    echo "Error: uninstall.py not found"
    exit 1
  fi
fi
