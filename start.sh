#!/bin/bash
# ミニモ サロンスクレイパー 起動スクリプト

cd "$(dirname "$0")"

# 仮想環境が存在するか確認
if [ ! -d "venv" ]; then
    echo "📦 仮想環境を作成中..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📥 依存パッケージをインストール中..."
    pip install -r requirements.txt
    echo "🌐 ブラウザをインストール中..."
    playwright install chromium
else
    source venv/bin/activate
fi

echo "🚀 アプリを起動中..."
streamlit run app.py
