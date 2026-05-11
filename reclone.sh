#!/bin/bash
set -e

TARGET_DIR="/home/pi/itd102-project"
REPO_URL="https://github.com/rea-sna/itd102-project.git"

echo "削除中: $TARGET_DIR"
rm -rf "$TARGET_DIR"

echo "クローン中: $REPO_URL"
git clone "$REPO_URL" "$TARGET_DIR"

echo "完了: $TARGET_DIR"
