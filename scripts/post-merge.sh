#!/bin/bash
set -e

# Sync Python dependencies (backend + Streamlit legacy)
uv sync --frozen 2>/dev/null || uv sync

# Install Next.js frontend dependencies if package.json exists
if [ -f frontend/package.json ]; then
  (cd frontend && npm install --include=dev --no-audit --no-fund)
fi
