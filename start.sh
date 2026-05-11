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

# RPi でデスクトップ外から起動する場合に必要
export DISPLAY="${DISPLAY:-:0}"

# 仮想環境がなければ作成
if [ ! -d "venv" ]; then
  echo "仮想環境を作成中..."
  python3 -m venv venv
  venv/bin/pip install --upgrade pip
  venv/bin/pip install -r requirements.txt
fi

# ネイティブ Tkinter アプリを起動
echo "TransLink サイネージを起動中..."
exec venv/bin/python native.py
