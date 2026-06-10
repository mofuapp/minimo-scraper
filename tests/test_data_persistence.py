"""データ消失防止ルールの回帰テスト"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import salon_data_store as ds  # noqa: E402


@pytest.fixture
def isolated_data(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    backup_dir = data_dir / "backups"
    data_file = data_dir / "salons.csv"
    last_session_file = data_dir / "last_session.csv"
    monkeypatch.setattr(ds, "DATA_DIR", data_dir)
    monkeypatch.setattr(ds, "DATA_FILE", data_file)
    monkeypatch.setattr(ds, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(ds, "LAST_SESSION_FILE", last_session_file)
    return data_file


def _sample_rows(n: int = 3) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "サロン名": f"サロン{i}",
                "ジャンル": "ネイル",
                "住所": "大阪府",
                "電話番号": f"'06{i:08d}",
                "サロンURL": f"https://minimodel.jp/r/test{i}",
                "いいね数": i,
                "最終更新日": f"2026-06-0{(i % 9) + 1}",
                "取得日時": f"2026-06-01 10:00:{i:02d}",
            }
        )
    return pd.DataFrame(rows)


def test_save_empty_does_not_wipe_existing(isolated_data):
    df = _sample_rows(5)
    ds.save_data(df)
    assert len(ds.load_data()) == 5

    with pytest.raises(ds.DataSaveError):
        ds.save_data(ds.empty_salon_df())

    assert len(ds.load_data()) == 5


def test_save_rejects_mass_deletion(isolated_data):
    ds.save_data(_sample_rows(10))
    tiny = _sample_rows(1)

    with pytest.raises(ds.DataSaveError):
        ds.save_data(tiny)

    assert len(ds.load_data()) == 10


def test_dedupe_keeps_one_per_url(isolated_data):
    df = pd.DataFrame(
        [
            {
                "サロン名": "A",
                "ジャンル": "ネイル",
                "住所": "大阪",
                "電話番号": "",
                "サロンURL": "https://minimodel.jp/r/same",
                "いいね数": 1,
                "最終更新日": "2026-06-01",
                "取得日時": "2026-06-01 10:00:00",
            },
            {
                "サロン名": "A2",
                "ジャンル": "ネイル",
                "住所": "大阪",
                "電話番号": "",
                "サロンURL": "https://minimodel.jp/r/same",
                "いいね数": 2,
                "最終更新日": "2026-06-02",
                "取得日時": "2026-06-02 10:00:00",
            },
        ]
    )
    out = ds.dedupe_by_salon_url(df)
    assert len(out) == 1
    assert out.iloc[0]["取得日時"] == "2026-06-02 10:00:00"


def test_add_new_salons_skips_duplicate_in_batch(isolated_data):
    base = ds.empty_salon_df()
    dup = {
        "サロン名": "X",
        "ジャンル": "ネイル",
        "住所": "京都",
        "電話番号": "",
        "サロンURL": "https://minimodel.jp/r/dup",
        "いいね数": 3,
        "最終更新日": "2026-06-01",
        "取得日時": "2026-06-01 12:00:00",
    }
    merged, added = ds.add_new_salons([dup, dup], base)
    assert len(added) == 1
    assert len(merged) == 1


def test_import_merges_without_duplicates(isolated_data):
    ds.save_data(_sample_rows(2))
    current = ds.load_data()
    extra = _sample_rows(3)
    merged, n = ds.import_from_dataframe(extra, current)
    assert n == 1
    assert len(merged) == 3


def test_backup_created_on_save(isolated_data):
    ds.save_data(_sample_rows(2))
    ds.save_data(_sample_rows(4))
    backups = ds.list_backups()
    assert len(backups) >= 1


def test_restore_after_clear(isolated_data):
    ds.save_data(_sample_rows(5))
    ds.clear_all_data()
    assert ds.load_data().empty

    restored, count = ds.restore_from_backup()
    assert count == 5
    assert len(ds.load_data()) == 5


def test_last_session_save_and_load(isolated_data):
    rows = _sample_rows(2)
    ds.save_last_session(rows)
    loaded = ds.load_last_session()
    assert len(loaded) == 2
    assert loaded.iloc[0]["サロンURL"] == rows.iloc[0]["サロンURL"]


def test_clear_all_data_also_clears_last_session(isolated_data):
    ds.save_last_session(_sample_rows(2))
    ds.save_data(_sample_rows(3))
    ds.clear_all_data()
    assert ds.load_last_session().empty


def test_load_data_without_update_date_column(isolated_data):
    legacy = _sample_rows(2).drop(columns=["最終更新日"])
    isolated_data.parent.mkdir(parents=True, exist_ok=True)
    legacy.to_csv(isolated_data, index=False, encoding="utf-8-sig")
    loaded = ds.load_data()
    assert len(loaded) == 2
    assert "最終更新日" in loaded.columns
