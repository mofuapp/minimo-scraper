"""Streamlit Cloud等でPlaywrightブラウザをセットアップ"""
import subprocess
import sys
from pathlib import Path


def _browser_installed() -> bool:
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        return False
    for pattern in ("chromium-*", "chromium_headless_shell-*"):
        if list(cache.glob(pattern)):
            return True
    return False


def ensure_playwright_browsers() -> None:
    """Chromiumが未インストールならダウンロード"""
    if _browser_installed():
        return

    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "Playwrightブラウザのインストールに失敗しました。"
            f" ({detail[:200]})"
        )
