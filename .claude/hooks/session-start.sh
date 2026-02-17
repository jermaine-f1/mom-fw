#!/bin/bash
set -euo pipefail

# Only run in remote (web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Install the project in editable mode with dev dependencies
pip install -e ".[dev]"

# Export PYTHONPATH so the package is importable
echo 'export PYTHONPATH="."' >> "$CLAUDE_ENV_FILE"

# Ensure pytest and ruff use the system Python (not uv-managed tools)
echo 'alias pytest="python3 -m pytest"' >> "$CLAUDE_ENV_FILE"
echo 'alias ruff="python3 -m ruff"' >> "$CLAUDE_ENV_FILE"
