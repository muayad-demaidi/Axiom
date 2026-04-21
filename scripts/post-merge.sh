#!/bin/bash
set -e

uv sync --frozen 2>/dev/null || uv sync
