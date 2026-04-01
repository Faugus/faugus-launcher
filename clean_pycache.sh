#!/usr/bin/env bash
set -e

PYTHON_SITE=$(python3 -c "import site; print(site.getsitepackages()[0])")
TARGET="$PYTHON_SITE/faugus"

if [ -d "$TARGET" ]; then
    echo "Cleaning old __pycache__..."

    find "$TARGET" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$TARGET" -type f -name "*.pyc" -delete 2>/dev/null || true
fi
