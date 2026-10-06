#!/usr/bin/env bash
# Opens a new, read-only window. Never initializes/migrates/changes a saved game.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 spectator.py --fullscreen "$@"
