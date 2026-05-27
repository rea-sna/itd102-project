#!/bin/bash
set -e

TARGET_DIR="/home/pi/itd102-project"
REPO_URL="https://github.com/rea-sna/itd102-project.git"

echo "Removing: $TARGET_DIR"
rm -rf "$TARGET_DIR"

echo "Cloning: $REPO_URL"
git clone "$REPO_URL" "$TARGET_DIR"

echo "Done: $TARGET_DIR"
