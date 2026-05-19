#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> フロントエンドをビルド中..."
cd "$ROOT/frontend"
npm install --silent
npm run build

echo "==> バックエンドを起動..."
cd "$ROOT/backend"
uv sync --quiet
uv run uvicorn main:app --reload --port 8000
