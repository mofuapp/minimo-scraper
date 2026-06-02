"""
ミニモ サロンスクレイパー GUI
Streamlit アプリケーション
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import streamlit.components.v1 as components

from scraper import CATEGORIES, PREFECTURES, SMALL_PREFECTURES


def normalize_phone_digits(phone) -> str:
    """電話番号を数字のみに正規化（スプシで0が消えた分を復元）"""
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
    """スプレッドシート用に電話番号の先頭0を保持（'を付与）"""
    digits = normalize_phone_digits(phone)
    if not digits:
        return ""
    return f"'{digits}"


def normalize_phones_in_df(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame内の電話番号をスプシ用形式に統一"""
    if df.empty or "電話番号" not in df.columns:
        return df
    out = df.copy()
    out["電話番号"] = out["電話番号"].apply(format_phone_for_spreadsheet)
    return out


def dedupe_by_salon_url(df: pd.DataFrame, keep: str = "last") -> pd.DataFrame:
    """サロンURLで重複行を除去（同一URLは取得日時が新しい方を残す）"""
    if df.empty or "サロンURL" not in df.columns:
        return df
    out = df.copy()
    out["サロンURL"] = out["サロンURL"].astype(str).str.strip()
    out = out[out["サロンURL"].notna() & (out["サロンURL"] != "") & (out["サロンURL"] != "nan")]
    if "取得日時" in out.columns:
        out = out.sort_values("取得日時", ascending=True)
    return out.drop_duplicates(subset=["サロンURL"], keep=keep).reset_index(drop=True)


def prepare_for_spreadsheet(df: pd.DataFrame) -> pd.DataFrame:
    """コピー・CSV出力用に電話番号を整形"""
    out = df.copy()
    if "電話番号" in out.columns:
        out["電話番号"] = out["電話番号"].apply(format_phone_for_spreadsheet)
    return out


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

# データファイルパス
DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "salons.csv"
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


def load_data() -> pd.DataFrame:
    """CSVからデータを読み込み"""
    DATA_DIR.mkdir(exist_ok=True)
    
    if DATA_FILE.exists():
        try:
            df = pd.read_csv(
                DATA_FILE,
                encoding="utf-8-sig",
                dtype={"電話番号": str},
            )
            normalized = dedupe_by_salon_url(normalize_phones_in_df(df))
            if len(normalized) < len(df):
                normalized.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
            elif "電話番号" in df.columns and not normalized["電話番号"].equals(
                df["電話番号"].astype(str)
            ):
                normalized.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
            return normalized
        except:
            pass
    
    return pd.DataFrame(columns=[
        "サロン名", "ジャンル", "住所", "電話番号",
        "サロンURL", "いいね数", "取得日時"
    ])


def save_data(df: pd.DataFrame):
    """CSVにデータを保存"""
    DATA_DIR.mkdir(exist_ok=True)
    dedupe_by_salon_url(normalize_phones_in_df(df)).to_csv(
        DATA_FILE, index=False, encoding="utf-8-sig"
    )


def add_new_salons(
    new_salons: list[dict], df: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    """新しいサロン情報を追加（URL重複は1件のみ）"""
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
        unique.append(salon)

    if not unique:
        return df, []

    new_df = pd.DataFrame(unique)
    merged = normalize_phones_in_df(pd.concat([df, new_df], ignore_index=True))
    return dedupe_by_salon_url(merged), unique


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

# サイドバー設定
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
df = load_data()
existing_urls = set(df["サロンURL"].dropna().tolist())

if "last_scrape_new" not in st.session_state:
    st.session_state.last_scrape_new = pd.DataFrame(
        columns=[
            "サロン名", "ジャンル", "住所", "電話番号",
            "サロンURL", "いいね数", "取得日時",
        ]
    )

# メインエリア
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 現在のデータ")
    st.metric("登録サロン数", f"{len(df)}件")

with col2:
    st.subheader("🔍 検索設定")
    cat_text = "全カテゴリ" if not selected_categories else f"{len(selected_categories)}カテゴリ"
    if nationwide_search:
        st.info(f"{cat_text} / 🌏全国 / お気に入り{max_likes}以下")
    else:
        st.info(f"{cat_text} / {len(search_prefectures)}県 / お気に入り{max_likes}以下")

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
                save_data(work["df"])
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
                ))

            if scrape_session_new:
                st.session_state.last_scrape_new = dedupe_by_salon_url(
                    normalize_phones_in_df(pd.DataFrame(scrape_session_new))
                )
            elif results:
                df, added = add_new_salons(results, df)
                save_data(df)
                st.session_state.last_scrape_new = (
                    dedupe_by_salon_url(normalize_phones_in_df(pd.DataFrame(added)))
                    if added
                    else pd.DataFrame(columns=st.session_state.last_scrape_new.columns)
                )
            else:
                st.session_state.last_scrape_new = pd.DataFrame(
                    columns=st.session_state.last_scrape_new.columns
                )

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
    
    filtered_df = df.copy()
    if filter_genre:
        filtered_df = filtered_df[filtered_df["ジャンル"].isin(filter_genre)]
    filtered_df = filtered_df[
        (filtered_df["いいね数"] >= likes_filter[0]) &
        (filtered_df["いいね数"] <= likes_filter[1])
    ]

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
        return out.sort_values("いいね数", ascending=True)

    export_all_df = apply_list_filters(df)
    export_new_df = apply_list_filters(st.session_state.last_scrape_new)
    
    # テーブル表示（URL重複は表示上も1件に）
    display_df = dedupe_by_salon_url(filtered_df)

    st.dataframe(
        display_df.sort_values("いいね数", ascending=True),
        use_container_width=True,
        column_config={
            "サロンURL": st.column_config.LinkColumn("URL"),
            "いいね数": st.column_config.NumberColumn("お気に入り", format="%d")
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
        csv_data = prepare_for_spreadsheet(export_all_df).to_csv(
            index=False, encoding="utf-8-sig"
        ).encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード（全件）",
            csv_data,
            f"salons_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv",
            use_container_width=True,
        )
    with col4:
        if st.button("🗑️ データクリア", use_container_width=True):
            if DATA_FILE.exists():
                DATA_FILE.unlink()
            st.session_state.last_scrape_new = pd.DataFrame(
                columns=st.session_state.last_scrape_new.columns
            )
            st.rerun()
else:
    st.info("まだデータがありません。スクレイピングを実行してください。")

# フッター
st.markdown("---")
st.caption("💡 都道府県検索はアプリと同じ「都道府県×カテゴリ＋新着順」です")
