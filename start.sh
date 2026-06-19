#!/bin/bash
# AbsoluteSpace one-click launcher (Linux). Run: ./start.sh  (or double-click if your
# file manager allows running scripts).
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 start.py
elif command -v python >/dev/null 2>&1; then
    exec python start.py
else
    echo "Python 3 was not found. Install it with your package manager, e.g.:"
    echo "    sudo apt install python3 python3-pip      (Debian/Ubuntu)"
    echo "    sudo dnf install python3 python3-pip       (Fedora)"
    read -r -p "Press Enter to close…"
fi
