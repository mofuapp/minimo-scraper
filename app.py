"""
ミニモ サロンスクレイパー GUI
Streamlit アプリケーション
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import streamlit.components.v1 as components

from scraper import CATEGORIES, PREFECTURES, SMALL_PREFECTURES


def format_phone_for_spreadsheet(phone) -> str:
    """スプレッドシート用に電話番号の先頭0を保持（'を付与）"""
    if phone is None or (isinstance(phone, float) and pd.isna(phone)):
        return ""
    phone = str(phone).strip()
    if not phone:
        return ""
    if phone.startswith("'"):
        return phone
    return f"'{phone}"


def prepare_for_spreadsheet(df: pd.DataFrame) -> pd.DataFrame:
    """コピー・CSV出力用に電話番号を整形"""
    out = df.copy()
    if "電話番号" in out.columns:
        out["電話番号"] = out["電話番号"].apply(format_phone_for_spreadsheet)
    return out


def create_copy_button(df: pd.DataFrame, button_text: str = "📋 コピー"):
    """スプレッドシート貼り付け用のコピーボタンを作成"""
    export_df = prepare_for_spreadsheet(df)
    tsv_data = export_df.to_csv(sep='\t', index=False)
    # JavaScriptで使えるようにエスケープ
    escaped_data = tsv_data.replace('`', "'").replace('$', '')
    
    # JavaScriptでクリップボードにコピー
    copy_js = f"""
    <style>
        .copy-btn {{
            background-color: #ff4b4b;
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            width: 100%;
            transition: background-color 0.3s;
        }}
        .copy-btn:hover {{
            background-color: #ff6b6b;
        }}
        .copy-btn.copied {{
            background-color: #00c853;
        }}
    </style>
    <button class="copy-btn" onclick="copyToClipboard()">
        {button_text}（スプシに貼り付けOK）
    </button>
    <script>
        const tsvData = `{escaped_data}`;
        
        function copyToClipboard() {{
            navigator.clipboard.writeText(tsvData).then(function() {{
                const btn = document.querySelector('.copy-btn');
                btn.textContent = '✅ コピーしました！';
                btn.classList.add('copied');
                setTimeout(function() {{
                    btn.textContent = '{button_text}（スプシに貼り付けOK）';
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


def load_data() -> pd.DataFrame:
    """CSVからデータを読み込み"""
    DATA_DIR.mkdir(exist_ok=True)
    
    if DATA_FILE.exists():
        try:
            df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
            return df
        except:
            pass
    
    return pd.DataFrame(columns=[
        "サロン名", "ジャンル", "住所", "電話番号",
        "サロンURL", "いいね数", "取得日時"
    ])


def save_data(df: pd.DataFrame):
    """CSVにデータを保存"""
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def add_new_salons(new_salons: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    """新しいサロン情報を追加"""
    if not new_salons:
        return df
    
    existing = set(df["サロンURL"].tolist())
    unique = [s for s in new_salons if s.get("サロンURL") and s["サロンURL"] not in existing]
    
    if not unique:
        return df
    
    new_df = pd.DataFrame(unique)
    return pd.concat([df, new_df], ignore_index=True)


# ページ設定
st.set_page_config(
    page_title="ミニモ サロンスクレイパー",
    page_icon="💅",
    layout="wide"
)

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
    "relaxation": "🧖 エステ・リラク"
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
    help="各検索での最大ページ数（1ページ=約20件）"
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

            with st.spinner("初回のみブラウザをセットアップ中...（1〜2分かかる場合があります）"):
                results = asyncio.run(scrape_minimo(
                    categories=cats,
                    max_likes=max_likes,
                    existing_urls=existing_urls,
                    progress_callback=progress,
                    prefectures=search_prefectures,
                    max_pages=max_pages,
                    nationwide=nationwide_search
                ))
            
            if results:
                df = add_new_salons(results, df)
                save_data(df)
                st.success(f"✅ {len(results)}件の新しいサロンを追加しました！")
            else:
                st.warning("条件に合うサロンは見つかりませんでした")
                
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
    
    # テーブル表示
    st.dataframe(
        filtered_df.sort_values("いいね数", ascending=True),
        use_container_width=True,
        column_config={
            "サロンURL": st.column_config.LinkColumn("URL"),
            "いいね数": st.column_config.NumberColumn("お気に入り", format="%d")
        }
    )
    
    # コピー・ダウンロード・クリア
    st.markdown("---")
    st.subheader("📤 データ出力")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        create_copy_button(filtered_df.sort_values("いいね数", ascending=True))
    with col2:
        csv_data = prepare_for_spreadsheet(filtered_df).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード",
            csv_data,
            f"salons_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv",
            use_container_width=True
        )
    with col3:
        if st.button("🗑️ データクリア", use_container_width=True):
            if DATA_FILE.exists():
                DATA_FILE.unlink()
            st.rerun()
else:
    st.info("まだデータがありません。スクレイピングを実行してください。")

# フッター
st.markdown("---")
st.caption("💡 ヒント: カテゴリを空にすると全カテゴリ（ネイル・マツエク・眉毛・エステ）を検索します")
