#!/bin/bash
# Render Blueprint デプロイ用スクリプト
# 事前準備: https://dashboard.render.com/account → API Keys でキーを作成

set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${RENDER_API_KEY:-}" ]; then
  echo "RENDER_API_KEY が未設定です。"
  echo "1. https://dashboard.render.com/account で API Key を作成"
  echo "2. export RENDER_API_KEY=rnd_xxxx"
  echo "3. このスクリプトを再実行"
  exit 1
fi

echo "Blueprint を作成します..."
RESP=$(curl -sS -X POST "https://api.render.com/v1/blueprints" \
  -H "Authorization: Bearer ${RENDER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "minimo-scraper-api",
    "repo": "https://github.com/mofuapp/minimo-scraper",
    "branch": "main"
  }')

echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"
echo ""
echo "ダッシュボード: https://dashboard.render.com/blueprints"
