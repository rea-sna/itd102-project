#!/bin/bash
# TransLink サイネージ起動スクリプト (Web 版)
#
# 使い方:
#   chmod +x start_web.sh
#   ./start_web.sh
#
# オプション:
#   PORT=8080 ./start_web.sh   # ポートを変更する場合
#
# 自動起動 (crontab) に登録する場合:
#   @reboot sleep 10 && /path/to/start_web.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"

# 仮想環境がなければ作成
if [ ! -d "venv" ]; then
  echo "仮想環境を作成中..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip
  venv/bin/pip install -r requirements.txt
fi

echo "TransLink Web サイネージを起動中..."
echo "URL: http://localhost:${PORT}"
exec venv/bin/python app.py --host "$HOST" --port "$PORT"
