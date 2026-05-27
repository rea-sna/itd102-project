#!/bin/bash
# TransLink signage launch script (web version)
#
# Usage:
#   chmod +x start_web.sh
#   ./start_web.sh
#
# Options:
#   PORT=8080 ./start_web.sh   # override the default port
#
# To run on boot via crontab:
#   @reboot sleep 10 && /path/to/start_web.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip
  venv/bin/pip install -r requirements.txt
fi

echo "Starting TransLink web signage..."
echo "URL: http://localhost:${PORT}"
exec venv/bin/python app.py --host "$HOST" --port "$PORT"
