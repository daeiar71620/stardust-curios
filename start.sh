#!/bin/sh
# Start from this file's directory in a graphical Linux desktop session.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "${PYTHON:-python3}" spectator.py --fullscreen "$@"
