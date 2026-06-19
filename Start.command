#!/bin/bash
# AbsoluteSpace one-click launcher (macOS). Double-click this file in Finder.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 start.py
elif command -v python >/dev/null 2>&1; then
    exec python start.py
else
    echo "Python 3 was not found. Install it from https://python.org or via 'brew install python'."
    read -r -p "Press Enter to close…"
fi
