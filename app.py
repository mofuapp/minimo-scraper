"""
ミニモ サロンスクレイパー GUI
Streamlit アプリケーション
"""
import base64
import sys
from pathlib import Path
from typing import Optional

# Streamlit Cloud（サブディレクトリ実行）でも同フォルダのモジュールを読めるようにする
_APP_ROOT = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import streamlit.components.v1 as components

from scraper import CATEGORIES, PREFECTURES, SMALL_PREFECTURES
from salon_data_store import (
    DATA_FILE,
    DataLoadError,
    DataSaveError,
    add_new_salons,
    backup_entries,
    clear_all_data,
    dedupe_by_salon_url,
    empty_salon_df,
    import_from_dataframe,
    is_ephemeral_host,
    load_data,
    normalize_phones_in_df,
    prepare_for_spreadsheet,
    restore_from_backup,
    save_data,
)


def create_copy_button(
    df: pd.DataFrame,
    button_text: str = "📋 コピー",
    button_id: str = "copy_default",
):
    """スプレッドシート貼り付け用のコピーボタンを作成"""
    if df.empty:
        st.caption(f"{button_text}（0件）")
        return

    export_df = prepare_for_spreadsheet(df)
    tsv_data = export_df.to_csv(sep="\t", index=False)
    escaped_data = tsv_data.replace("`", "'").replace("$", "").replace("\\", "\\\\")
    btn_class = f"copy-btn-{button_id}"
    fn_name = f"copyToClipboard_{button_id}"

    copy_js = f"""
    <style>
        .{btn_class} {{
            background-color: #ff4b4b;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            width: 100%;
            transition: background-color 0.3s;
        }}
        .{btn_class}:hover {{
            background-color: #ff6b6b;
        }}
        .{btn_class}.copied {{
            background-color: #00c853;
        }}
    </style>
    <button class="{btn_class}" onclick="{fn_name}()">
        {button_text}（{len(export_df)}件）
    </button>
    <script>
        const tsvData_{button_id} = `{escaped_data}`;

        function {fn_name}() {{
            navigator.clipboard.writeText(tsvData_{button_id}).then(function() {{
                const btn = document.querySelector('.{btn_class}');
                btn.textContent = '✅ コピーしました！';
                btn.classList.add('copied');
                setTimeout(function() {{
                    btn.textContent = '{button_text}（{len(export_df)}件）';
                    btn.classList.remove('copied');
                }}, 2000);
            }}).catch(function(err) {{
                alert('コピーに失敗しました: ' + err);
            }});
        }}
    </script>
    """
    components.html(copy_js, height=50)


def create_csv_download_button(
    df: pd.DataFrame,
    button_text: str = "📥 CSVを保存",
    button_id: str = "csv_download",
    filename: Optional[str] = None,
):
    """スマホでも画面遷移しにくいCSV保存（共有シート or 端末保存）"""
    if df.empty:
        st.caption(f"{button_text}（0件）")
        return

    if not filename:
        filename = f"salons_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    csv_bytes = prepare_for_spreadsheet(df).to_csv(
        index=False, encoding="utf-8-sig"
    ).encode("utf-8-sig")
    b64 = base64.b64encode(csv_bytes).decode("ascii")
    btn_class = f"dl-btn-{button_id}"
    fn_name = f"downloadCsv_{button_id}"

    download_js = f"""
    <style>
        .{btn_class} {{
            background-color: #ff4b4b;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            width: 100%;
        }}
        .{btn_class}.done {{
            background-color: #00c853;
        }}
        .{btn_class}-hint {{
            font-size: 12px;
            color: #666;
            margin-top: 6px;
            line-height: 1.4;
        }}
    </style>
    <button class="{btn_class}" onclick="{fn_name}()">
        {button_text}（{len(df)}件）
    </button>
    <p class="{btn_class}-hint">
        スマホ: 共有メニューから「ファイルに保存」。キャンセルでこの画面に戻れます。
    </p>
    <script>
        function {fn_name}() {{
            const bytes = Uint8Array.from(atob("{b64}"), c => c.charCodeAt(0));
            const blob = new Blob([bytes], {{ type: "text/csv;charset=utf-8" }});
            const file = new File([blob], "{filename}", {{ type: "text/csv" }});
            const btn = document.querySelector(".{btn_class}");

            function done() {{
                btn.textContent = "✅ 保存メニューを開きました";
                btn.classList.add("done");
                setTimeout(function() {{
                    btn.textContent = "{button_text}（{len(df)}件）";
                    btn.classList.remove("done");
                }}, 2500);
            }}

            if (navigator.canShare && navigator.canShare({{ files: [file] }})) {{
                navigator.share({{ files: [file], title: "{filename}" }})
                    .then(done)
                    .catch(function(err) {{
                        if (err && err.name === "AbortError") return;
                        fallbackDownload();
                    }});
                return;
            }}
            fallbackDownload();

            function fallbackDownload() {{

                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = "{filename}";
                a.rel = "noopener";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                done();
            }}
        }}
    </script>
    """
    components.html(download_js, height=88)


def render_backup_restore(key_prefix: str, *, compact: bool = False) -> None:
    """自動バックアップからデータを復元するUI（呼び出し元のコンテキスト内に描画）"""
    entries = backup_entries()

    if not entries:
        st.caption(
            "自動バックアップはまだありません。"
            "（保存やクリアの直前に作成されます）"
        )
        return

    latest = entries[0]

    def _do_restore(path):
        try:
            _, count = restore_from_backup(path)
            st.success(f"✅ {count}件を復元しました")
            st.rerun()
        except DataLoadError as e:
            st.error(str(e))

    if compact:
        st.caption(f"バックアップ {len(entries)}件（最新 {latest['rows']}件）")
    else:
        st.caption(
            f"データクリア後はここから戻せます。"
            f" 最新: {latest['mtime']} · **{latest['rows']}件**"
        )

    if st.button(
        f"↩️ 最新のバックアップを復元（{latest['rows']}件）",
        key=f"{key_prefix}_latest",
        type="primary",
        use_container_width=True,
    ):
        _do_restore(latest["path"])

    with st.expander("別のバックアップを選ぶ"):
        labels = [e["label"] for e in entries]
        picked = st.selectbox(
            "復元するバックアップ",
            options=labels,
            key=f"{key_prefix}_select",
        )
        path = next(e["path"] for e in entries if e["label"] == picked)
        if st.button(
            "このバックアップで復元",
            key=f"{key_prefix}_pick",
            use_container_width=True,
        ):
            _do_restore(path)

ICON_PATH = Path(__file__).parent / ".streamlit" / "app-icon.png"
APPLE_ICON_PATH = Path(__file__).parent / ".streamlit" / "apple-touch-icon.png"
ICON_GITHUB_URL = (
    "https://raw.githubusercontent.com/mofuapp/minimo-scraper/main/"
    ".streamlit/apple-touch-icon.png"
)


def get_page_icon() -> str:
    """ページアイコン（ローカル優先、なければGitHub URL）"""
    if APPLE_ICON_PATH.exists():
        return str(APPLE_ICON_PATH)
    return ICON_GITHUB_URL


def inject_home_screen_icon(icon_url: str) -> None:
    """ホーム画面追加用のアイコン・タイトルを設定"""
    app_title = "ミニモスクレイパー"
    safe_url = icon_url.replace("\\", "\\\\").replace('"', '\\"')

    st.markdown(
        f'<link rel="apple-touch-icon" href="{safe_url}">'
        f'<link rel="apple-touch-icon-precomposed" href="{safe_url}">'
        f'<meta name="apple-mobile-web-app-title" content="{app_title}">',
        unsafe_allow_html=True,
    )

    components.html(
        f"""
        <script>
        (function() {{
            const iconUrl = "{safe_url}";
            const title = "{app_title}";
            const docs = [];
            try {{ docs.push(window.top.document); }} catch (e) {{}}
            try {{ docs.push(window.parent.document); }} catch (e) {{}}
            docs.push(document);

            docs.forEach(function(doc) {{
                if (!doc || !doc.head) return;
                ["apple-touch-icon", "apple-touch-icon-precomposed"].forEach(function(rel) {{
                    if (doc.querySelector('link[rel="' + rel + '"]')) return;
                    const link = doc.createElement("link");
                    link.rel = rel;
                    link.href = iconUrl;
                    doc.head.appendChild(link);
                }});
                let metaTitle = doc.querySelector('meta[name="apple-mobile-web-app-title"]');
                if (!metaTitle) {{
                    metaTitle = doc.createElement("meta");
                    metaTitle.name = "apple-mobile-web-app-title";
                    doc.head.appendChild(metaTitle);
                }}
                metaTitle.content = title;
            }});
        }})();
        </script>
        """,
        height=0,
    )


# ページ設定
_page_icon = get_page_icon()
st.set_page_config(
    page_title="ミニモ サロンスクレイパー",
    page_icon=_page_icon,
    layout="wide"
)

inject_home_screen_icon(ICON_GITHUB_URL)

# タイトル
st.title("💅 ミニモ サロンスクレイパー")
st.markdown("お気に入り数が少ないサロンを検索して収集します")

if is_ephemeral_host():
    st.error(
        "**クラウド版のデータは再起動・更新で消えます。** "
        "スクレイピング後は必ず「CSVダウンロード」でバックアップを取ってください。"
        "消えた場合は下の「CSVから復元」で戻せます。"
    )
else:
    st.info(
        "データは `data/salons.csv` に保存されます。"
        "念のため定期的にCSVダウンロードをおすすめします。"
    )

# サイドバー: データ復元
st.sidebar.header("💾 データ管理")
uploaded_csv = st.sidebar.file_uploader(
    "CSVから復元",
    type=["csv"],
    help="以前ダウンロードした salons_*.csv を選ぶと、既存データにマージします",
)
if uploaded_csv is not None:
    if st.sidebar.button("復元を実行", use_container_width=True):
        try:
            imported = pd.read_csv(
                uploaded_csv,
                encoding="utf-8-sig",
                dtype={"電話番号": str},
            )
            current = load_data()
            merged, added = import_from_dataframe(imported, current)
            st.sidebar.success(f"✅ {added}件を追加（合計{len(merged)}件）")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"復元失敗: {e}")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 検索設定")

# カテゴリ選択
category_options = {
    "nail": "💅 ネイル",
    "eyelash": "👁️ マツエク・マツパ",
    "eyebrow": "✨ 眉毛",
    "relaxation": "🧖 エステ・リラク",
    "other": "💫 その他美容",
}
selected_categories = st.sidebar.multiselect(
    "カテゴリ（空=全て）",
    options=list(category_options.keys()),
    default=[],
    format_func=lambda x: category_options[x],
    help="何も選択しないと全カテゴリを検索します"
)

# お気に入り数の上限
max_likes = st.sidebar.slider(
    "お気に入り数の上限",
    min_value=1,
    max_value=100,
    value=5,
    help="この数以下のサロンを抽出します"
)

# ページ数
max_pages = st.sidebar.slider(
    "検索ページ数",
    min_value=1,
    max_value=20,
    value=20,
    help="各カテゴリの最大ページ数（1ページ≈20件）。多いほど時間がかかります"
)

fetch_phone = st.sidebar.checkbox(
    "電話番号も取得する",
    value=True,
    help="ONで電話番号も取得（詳細ページは住所取得のため常に参照します）"
)

# 最終更新日フィルタ
st.sidebar.markdown("---")
st.sidebar.subheader("📅 最終更新日")
filter_by_updated = st.sidebar.checkbox(
    "更新日で絞る",
    value=False,
    help="ミニモ掲載ページの「○年○月○日更新」でフィルタします",
)
today = datetime.now().date()
update_min_date = None
update_max_date = None
if filter_by_updated:
    preset = st.sidebar.selectbox(
        "期間",
        ["直近7日", "直近14日", "直近30日", "直近90日", "カスタム"],
        index=2,
    )
    if preset == "直近7日":
        update_min_date = today - timedelta(days=7)
        update_max_date = today
    elif preset == "直近14日":
        update_min_date = today - timedelta(days=14)
        update_max_date = today
    elif preset == "直近30日":
        update_min_date = today - timedelta(days=30)
        update_max_date = today
    elif preset == "直近90日":
        update_min_date = today - timedelta(days=90)
        update_max_date = today
    else:
        update_min_date = st.sidebar.date_input(
            "この日以降",
            value=today - timedelta(days=30),
        )
        update_max_date = st.sidebar.date_input("この日まで", value=today)
    st.sidebar.caption(
        f"対象: {update_min_date} 〜 {update_max_date}"
    )

# 検索範囲
st.sidebar.markdown("---")
st.sidebar.subheader("🗾 検索範囲")

search_mode = st.sidebar.radio(
    "検索モード",
    options=["🌏 全国検索（新着順）", "📍 都道府県指定"],
    index=1,
    help="全国検索は新着サロンを見つけやすい！"
)

nationwide_search = search_mode == "🌏 全国検索（新着順）"

if nationwide_search:
    search_prefectures = []
    st.sidebar.success("全国からお気に入りが少ない新着サロンを検索します")
else:
    # 関西の都道府県
    KANSAI_PREFS = ["大阪府", "京都府", "兵庫県", "奈良県", "滋賀県", "和歌山県"]
    
    st.sidebar.markdown("**関西エリア（タップで選択）**")
    
    # セッション状態の初期化
    if "selected_kansai" not in st.session_state:
        st.session_state.selected_kansai = set()
    if "selected_other" not in st.session_state:
        st.session_state.selected_other = []
    
    # 関西の都道府県をボタン表示
    cols = st.sidebar.columns(2)
    for i, pref in enumerate(KANSAI_PREFS):
        col = cols[i % 2]
        is_selected = pref in st.session_state.selected_kansai
        
        if col.button(
            f"{'✅ ' if is_selected else ''}{pref}",
            key=f"btn_{pref}",
            use_container_width=True,
            type="primary" if is_selected else "secondary"
        ):
            if is_selected:
                st.session_state.selected_kansai.discard(pref)
            else:
                st.session_state.selected_kansai.add(pref)
            st.rerun()
    
    # その他の都道府県
    OTHER_PREFS = [p for p in PREFECTURES if p not in KANSAI_PREFS]
    with st.sidebar.expander("📍 その他の都道府県"):
        selected_other = st.multiselect(
            "選択",
            options=OTHER_PREFS,
            default=st.session_state.selected_other,
            key="other_prefs_select",
            label_visibility="collapsed"
        )
        st.session_state.selected_other = selected_other
    
    # 関西 + その他を合わせる
    search_prefectures = list(st.session_state.selected_kansai) + st.session_state.selected_other
    
    if search_prefectures:
        st.sidebar.success(f"選択中: {', '.join(search_prefectures)}")
    else:
        st.sidebar.warning("都道府県を選択してください")

# データ読み込み
try:
    df = load_data()
except DataLoadError as e:
    st.error(f"データ読み込みエラー: {e}")
    df = empty_salon_df()

existing_urls = set(df["サロンURL"].dropna().tolist())
with st.sidebar.expander("💾 バックアップから復元", expanded=df.empty and bool(backup_entries())):
    render_backup_restore("sidebar", compact=True)

if "last_scrape_new" not in st.session_state:
    st.session_state.last_scrape_new = empty_salon_df()
if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

# メインエリア
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 現在のデータ")
    st.metric("登録サロン数", f"{len(df)}件")
    if df.empty and backup_entries():
        render_backup_restore("header")

with col2:
    st.subheader("🔍 検索設定")
    cat_text = "全カテゴリ" if not selected_categories else f"{len(selected_categories)}カテゴリ"
    update_text = ""
    if filter_by_updated and update_min_date and update_max_date:
        update_text = f" / 更新 {update_min_date}〜{update_max_date}"
    if nationwide_search:
        st.info(f"{cat_text} / 🌏全国 / お気に入り{max_likes}以下{update_text}")
    else:
        st.info(
            f"{cat_text} / {len(search_prefectures)}県 / "
            f"お気に入り{max_likes}以下{update_text}"
        )

# スクレイピング開始ボタン（全国検索または都道府県指定の場合に有効）
can_search = nationwide_search or (len(search_prefectures) > 0)
if st.button(
    "🔍 スクレイピング開始",
    disabled=not can_search,
    type="primary",
    use_container_width=True
):
    with st.spinner("🔄 スクレイピング中... (数分かかる場合があります)"):
        progress_bar = st.progress(0)
        progress_label = st.empty()
        progress_area = st.empty()
        
        import importlib
        import scraper as scraper_mod
        importlib.reload(scraper_mod)
        from scraper import scrape_minimo
        import asyncio
        
        messages = []
        
        def progress(msg, percent=0):
            messages.append(msg)
            progress_bar.progress(percent / 100)
            progress_label.markdown(f"**進捗: {percent}%**")
            progress_area.code("\n".join(messages[-20:]), language=None)
        
        try:
            # カテゴリ指定（空なら全て）
            cats = selected_categories if selected_categories else None
            saved_count = [0]
            scrape_session_new = []
            work = {"df": df}

            def save_prefecture_batch(batch: list[dict]):
                work["df"], added = add_new_salons(batch, work["df"])
                if not added:
                    return
                try:
                    save_data(work["df"])
                except DataSaveError as e:
                    st.error(f"保存エラー: {e}")
                    raise
                saved_count[0] += len(added)
                scrape_session_new.extend(added)
                for row in added:
                    existing_urls.add(row["サロンURL"])

            with st.spinner("初回のみブラウザをセットアップ中...（1〜2分かかる場合があります）"):
                results = asyncio.run(scrape_minimo(
                    categories=cats,
                    max_likes=max_likes,
                    existing_urls=existing_urls,
                    progress_callback=progress,
                    prefectures=search_prefectures,
                    max_pages=max_pages,
                    nationwide=nationwide_search,
                    fetch_phone=fetch_phone,
                    on_prefecture_done=save_prefecture_batch if not nationwide_search else None,
                    min_updated_date=update_min_date if filter_by_updated else None,
                    max_updated_date=update_max_date if filter_by_updated else None,
                ))

            if scrape_session_new:
                st.session_state.last_scrape_new = dedupe_by_salon_url(
                    normalize_phones_in_df(pd.DataFrame(scrape_session_new))
                )
            elif results:
                df, added = add_new_salons(results, df)
                try:
                    save_data(df)
                except DataSaveError as e:
                    st.error(f"保存エラー: {e}")
                    raise
                st.session_state.last_scrape_new = (
                    dedupe_by_salon_url(normalize_phones_in_df(pd.DataFrame(added)))
                    if added
                    else empty_salon_df()
                )
            else:
                st.session_state.last_scrape_new = empty_salon_df()

            new_added_count = len(st.session_state.last_scrape_new)
            if new_added_count > 0:
                if not nationwide_search:
                    df = work["df"]
                st.success(f"✅ {new_added_count}件の新しいサロンを追加しました！")
            else:
                st.warning(
                    "条件に合うサロンは見つかりませんでした。"
                    "（既に登録済みの可能性があります。ログの「候補○件」を確認してください）"
                )
                
        except Exception as e:
            st.error(f"❌ エラー: {str(e)}")

# データ表示
st.markdown("---")
st.subheader("📋 サロンリスト")

if not df.empty:
    # フィルター
    col1, col2 = st.columns(2)
    with col1:
        genres = df["ジャンル"].unique().tolist() if len(df) > 0 else []
        filter_genre = st.multiselect(
            "ジャンルでフィルタ",
            options=genres,
            default=[]
        )
    with col2:
        max_fav = int(df["いいね数"].max()) if len(df) > 0 and not df["いいね数"].isna().all() else 50
        likes_filter = st.slider(
            "お気に入り数でフィルタ",
            min_value=0,
            max_value=max(max_fav, 1),
            value=(0, max(max_fav, 1))
        )
    
    def _filter_by_updated_col(frame: pd.DataFrame) -> pd.DataFrame:
        if not filter_by_updated or "最終更新日" not in frame.columns:
            return frame
        parsed = pd.to_datetime(frame["最終更新日"], errors="coerce")
        mask = parsed.notna()
        if update_min_date:
            mask &= parsed.dt.date >= update_min_date
        if update_max_date:
            mask &= parsed.dt.date <= update_max_date
        return frame[mask]

    filtered_df = df.copy()
    if filter_genre:
        filtered_df = filtered_df[filtered_df["ジャンル"].isin(filter_genre)]
    filtered_df = filtered_df[
        (filtered_df["いいね数"] >= likes_filter[0]) &
        (filtered_df["いいね数"] <= likes_filter[1])
    ]
    filtered_df = _filter_by_updated_col(filtered_df)

    def apply_list_filters(source_df: pd.DataFrame) -> pd.DataFrame:
        out = dedupe_by_salon_url(source_df.copy())
        if out.empty:
            return out
        if filter_genre:
            out = out[out["ジャンル"].isin(filter_genre)]
        out = out[
            (out["いいね数"] >= likes_filter[0]) &
            (out["いいね数"] <= likes_filter[1])
        ]
        out = _filter_by_updated_col(out)
        sort_cols = ["最終更新日", "いいね数"] if "最終更新日" in out.columns else ["いいね数"]
        return out.sort_values(sort_cols, ascending=[False, True])

    export_all_df = apply_list_filters(df)
    export_new_df = apply_list_filters(st.session_state.last_scrape_new)
    
    # テーブル表示（URL重複は表示上も1件に）
    display_df = dedupe_by_salon_url(filtered_df)

    sort_cols = ["最終更新日", "いいね数"] if "最終更新日" in display_df.columns else ["いいね数"]
    st.dataframe(
        display_df.sort_values(sort_cols, ascending=[False, True]),
        use_container_width=True,
        column_config={
            "サロンURL": st.column_config.LinkColumn("URL"),
            "いいね数": st.column_config.NumberColumn("お気に入り", format="%d"),
            "最終更新日": st.column_config.TextColumn("最終更新"),
        }
    )
    
    # コピー・ダウンロード・クリア
    st.markdown("---")
    st.subheader("📤 データ出力")

    new_count = len(export_new_df)
    all_count = len(export_all_df)
    st.caption(
        f"今回の新規: {new_count}件 / 登録済み合計: {all_count}件"
    )

    col1, col2 = st.columns(2)
    with col1:
        create_copy_button(
            export_new_df,
            "📋 今回分のみコピー",
            button_id="copy_new",
        )
    with col2:
        create_copy_button(
            export_all_df,
            "📋 全件コピー（過去分含む）",
            button_id="copy_all",
        )

    col3, col4 = st.columns(2)
    with col3:
        create_csv_download_button(
            export_all_df,
            "📥 CSVを保存（全件）",
            button_id="csv_all",
        )
    with col4:
        if st.session_state.confirm_clear:
            st.warning("登録データをすべて削除します。よろしいですか？")
            c_yes, c_no = st.columns(2)
            if c_yes.button("削除する", type="primary", use_container_width=True):
                clear_all_data()
                st.session_state.last_scrape_new = empty_salon_df()
                st.session_state.confirm_clear = False
                st.rerun()
            if c_no.button("キャンセル", use_container_width=True):
                st.session_state.confirm_clear = False
                st.rerun()
        elif st.button("🗑️ データクリア", use_container_width=True):
            st.session_state.confirm_clear = True
            st.rerun()
else:
    if backup_entries():
        st.warning("登録データがありません。バックアップから復元できます。")
        render_backup_restore("list_empty")
        st.caption("手元のCSVがある場合は、左サイドバーの「CSVから復元」も使えます。")
    else:
        st.info(
            "まだデータがありません。スクレイピングを実行するか、"
            "サイドバーの「CSVから復元」で以前のCSVを読み込んでください。"
        )

# フッター
st.markdown("---")
st.caption("💡 都道府県検索はアプリと同じ「都道府県×カテゴリ＋新着順」です")
