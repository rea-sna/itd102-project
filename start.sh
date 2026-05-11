#!/bin/bash
# TransLink サイネージ起動スクリプト (Raspberry Pi 3 用)
#
# 使い方:
#   chmod +x start.sh
#   ./start.sh
#
# 自動起動 (crontab) に登録する場合:
#   @reboot sleep 10 && /path/to/start.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 仮想環境がなければ作成
if [ ! -d "venv" ]; then
  echo "仮想環境を作成中..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip
  venv/bin/pip install -r requirements.txt
fi

# Flask サーバーをバックグラウンドで起動
echo "Flask サーバーを起動中..."
venv/bin/python app.py &
FLASK_PID=$!

# サーバーが起動するまで待機
sleep 3

# surf をフルスクリーンで起動
surf -F http://localhost:5000

# surf 終了後に Flask を停止
kill $FLASK_PID 2>/dev/null || true
