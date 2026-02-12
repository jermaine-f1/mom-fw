#!/bin/bash
# Sync index.html from mom-fw to sibling mom-fw-ui repo
# Usage: ./sync_ui.sh [--commit]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UI_DIR="$(dirname "$SCRIPT_DIR")/mom-fw-ui"

if [ ! -d "$UI_DIR" ]; then
  echo "Error: mom-fw-ui not found at $UI_DIR"
  echo "Clone it first: git clone <url> $UI_DIR"
  exit 1
fi

cp "$SCRIPT_DIR/index.html" "$UI_DIR/index.html"
echo "Copied index.html -> $UI_DIR/index.html"

if [ "$1" = "--commit" ]; then
  cd "$UI_DIR"
  git add index.html
  if git diff --cached --quiet; then
    echo "No changes to commit in mom-fw-ui"
  else
    HASH=$(cd "$SCRIPT_DIR" && git rev-parse --short HEAD)
    git commit -m "Sync index.html from mom-fw@$HASH"
    git push
    echo "Pushed to mom-fw-ui"
  fi
fi
