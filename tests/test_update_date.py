"""最終更新日パース・フィルタのテスト"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper import (  # noqa: E402
    format_last_updated,
    parse_last_updated_from_text,
    passes_update_date_filter,
)


def test_parse_japanese_update_date():
    text = "大阪府\n2026年6月4日更新\nメニュー"
    assert parse_last_updated_from_text(text) == date(2026, 6, 4)


def test_parse_missing_returns_none():
    assert parse_last_updated_from_text("お気に入り 3") is None


def test_passes_update_date_filter():
    d = date(2026, 6, 1)
    assert passes_update_date_filter(d, date(2026, 5, 1), date(2026, 6, 30))
    assert not passes_update_date_filter(d, date(2026, 6, 2), None)
    assert passes_update_date_filter(None, None, None)


def test_format_last_updated():
    assert format_last_updated(date(2026, 1, 5)) == "2026-01-05"
    assert format_last_updated(None) == ""
