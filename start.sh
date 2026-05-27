#!/bin/bash
# TransLink signage launch script (Raspberry Pi 3)
#
# Usage:
#   chmod +x start.sh
#   ./start.sh
#
# To run on boot via crontab:
#   @reboot sleep 10 && /path/to/start.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Required when launching outside a desktop session on RPi
export DISPLAY="${DISPLAY:-:0}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip
  venv/bin/pip install -r requirements.txt
fi

# Launch the native Tkinter app
echo "Starting TransLink signage..."
exec venv/bin/python native.py
