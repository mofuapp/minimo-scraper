"""
サロンデータの読み書き（消失防止ルール付き）
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

SALON_COLUMNS = [
    "サロン名",
    "ジャンル",
    "住所",
    "電話番号",
    "サロンURL",
    "いいね数",
    "取得日時",
]

DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "salons.csv"
BACKUP_DIR = DATA_DIR / "backups"
MAX_BACKUPS = 50


class DataSaveError(Exception):
    """安全ルールにより保存を拒否した"""


class DataLoadError(Exception):
    """CSVの読み込みに失敗した"""


def is_ephemeral_host() -> bool:
    """Streamlit Cloud など、再起動で data/ が消えるホスト"""
    if os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud":
        return True
    if Path("/mount/src").exists():
        return True
    return False


def normalize_phone_digits(phone) -> str:
    if phone is None or (isinstance(phone, float) and pd.isna(phone)):
        return ""
    s = str(phone).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.startswith("'"):
        s = s[1:].strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    if len(digits) == 9:
        digits = "0" + digits
    elif len(digits) == 10 and not digits.startswith("0"):
        digits = "0" + digits
    return digits


def format_phone_for_spreadsheet(phone) -> str:
    digits = normalize_phone_digits(phone)
    if not digits:
        return ""
    return f"'{digits}"


def normalize_phones_in_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "電話番号" not in df.columns:
        return df
    out = df.copy()
    out["電話番号"] = out["電話番号"].apply(format_phone_for_spreadsheet)
    return out


def dedupe_by_salon_url(df: pd.DataFrame, keep: str = "last") -> pd.DataFrame:
    if df.empty or "サロンURL" not in df.columns:
        return df
    out = df.copy()
    out["サロンURL"] = out["サロンURL"].astype(str).str.strip()
    out = out[
        out["サロンURL"].notna()
        & (out["サロンURL"] != "")
        & (out["サロンURL"] != "nan")
    ]
    if out.empty:
        return out
    if "取得日時" in out.columns:
        out = out.sort_values("取得日時", ascending=True)
    return out.drop_duplicates(subset=["サロンURL"], keep=keep).reset_index(drop=True)


def empty_salon_df() -> pd.DataFrame:
    return pd.DataFrame(columns=SALON_COLUMNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"電話番号": str})


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in SALON_COLUMNS if c not in df.columns]
    if missing:
        raise DataLoadError(f"CSVに必須列がありません: {', '.join(missing)}")
    out = df[SALON_COLUMNS].copy()
    return dedupe_by_salon_url(normalize_phones_in_df(out))


def backup_before_save() -> Path | None:
    if not DATA_FILE.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"salons_{ts}.csv"
    shutil.copy2(DATA_FILE, dest)
    backups = sorted(BACKUP_DIR.glob("salons_*.csv"), key=lambda p: p.stat().st_mtime)
    while len(backups) > MAX_BACKUPS:
        backups.pop(0).unlink(missing_ok=True)
    return dest


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("salons_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)


def _write_csv(df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _prepare_df(df).to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def save_data(df: pd.DataFrame) -> None:
    """新規保存（空上書き・急激な行数減少を拒否）"""
    prepared = _prepare_df(df)

    if DATA_FILE.exists():
        backup_before_save()
        try:
            current = _prepare_df(_read_csv(DATA_FILE))
        except Exception:
            current = empty_salon_df()

        if prepared.empty and not current.empty:
            raise DataSaveError(
                "空のデータで既存ファイルを上書きしようとしたため、保存を中止しました。"
            )

        if len(current) >= 5 and len(prepared) < len(current) // 2:
            raise DataSaveError(
                f"行数が急減しました（{len(current)}件→{len(prepared)}件）。"
                "保存を中止しました。バックアップを確認してください。"
            )

    _write_csv(prepared)


def save_data_quiet(df: pd.DataFrame) -> None:
    """重複整理・電話番号整形など、行数が減るだけの更新用"""
    if DATA_FILE.exists():
        backup_before_save()
    _write_csv(df)


def _try_load_latest_backup() -> pd.DataFrame | None:
    for path in list_backups():
        try:
            df = _prepare_df(_read_csv(path))
            if not df.empty:
                save_data_quiet(df)
                return df
        except Exception:
            continue
    return None


def load_data() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        return empty_salon_df()

    try:
        raw = _read_csv(DATA_FILE)
    except Exception as exc:
        restored = _try_load_latest_backup()
        if restored is not None:
            return restored
        raise DataLoadError(f"salons.csv の読み込みに失敗: {exc}") from exc

    if raw.empty:
        return empty_salon_df()

    normalized = _prepare_df(raw)

    if normalized.empty and not raw.empty:
        return normalize_phones_in_df(raw[SALON_COLUMNS].copy())

    if len(normalized) < len(raw):
        save_data_quiet(normalized)
    else:
        phone_fixed = normalize_phones_in_df(raw[SALON_COLUMNS].copy())
        if "電話番号" in raw.columns and not phone_fixed["電話番号"].equals(
            raw["電話番号"].astype(str)
        ):
            save_data_quiet(normalized)

    return normalized


def clear_all_data() -> None:
    if DATA_FILE.exists():
        backup_before_save()
        DATA_FILE.unlink()


def records_from_df(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    cols = [c for c in SALON_COLUMNS if c in df.columns]
    return df[cols].to_dict(orient="records")


def add_new_salons(
    new_salons: list[dict], df: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    if not new_salons:
        return df, []

    existing = set(df["サロンURL"].dropna().astype(str).str.strip().tolist())
    unique: list[dict] = []
    seen_in_batch: set[str] = set()

    for salon in new_salons:
        url = salon.get("サロンURL")
        if not url:
            continue
        url = str(url).strip()
        if url in existing or url in seen_in_batch:
            continue
        seen_in_batch.add(url)
        row = {col: salon.get(col, "") for col in SALON_COLUMNS}
        unique.append(row)

    if not unique:
        return df, []

    new_df = pd.DataFrame(unique)
    merged = normalize_phones_in_df(pd.concat([df, new_df], ignore_index=True))
    return dedupe_by_salon_url(merged), unique


def import_from_dataframe(imported: pd.DataFrame, df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    records = records_from_df(imported)
    merged, added = add_new_salons(records, df)
    if added:
        save_data(merged)
    return merged, len(added)


def prepare_for_spreadsheet(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "電話番号" in out.columns:
        out["電話番号"] = out["電話番号"].apply(format_phone_for_spreadsheet)
    return out
