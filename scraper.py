"""
ミニモ サロンスクレイパー
キーワード検索でお気に入りが少ないサロンを抽出する
"""
import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright, Page
from typing import Optional, Callable
import urllib.parse


# カテゴリ（検出用）
CATEGORIES = {
    "nail": "ネイル",
    "eyelash": "マツエク・マツパ",
    "eyebrow": "眉毛",
    "relaxation": "エステ・リラク",
}

# 都道府県リスト
PREFECTURES = [
    "北海道", "青森県", "岩手県", "秋田県", "山形県", "宮城県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府",
    "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
]

# サロン数が少ない県（優先検索）
SMALL_PREFECTURES = [
    "秋田県", "岩手県", "島根県", "鳥取県", "青森県", "山形県", "福井県",
    "徳島県", "佐賀県", "長崎県", "宮崎県", "高知県", "山口県", "和歌山県",
    "大分県", "愛媛県", "香川県", "富山県", "石川県", "奈良県", "福島県"
]


def get_search_url(category: str = None, area: str = None) -> str:
    """検索URLを生成（カテゴリ+エリア）"""
    base_url = "https://minimodel.jp/search?"
    params = []
    
    if category:
        params.append(f"category={category}")
    if area:
        encoded_area = urllib.parse.quote(area)
        params.append(f"area={encoded_area}")
    
    # 新着順でソート
    params.append("order=updated_datetime")
    
    return base_url + "&".join(params) if params else base_url


async def click_sort_newest(page: Page) -> bool:
    """新着順ボタンをクリック"""
    try:
        sort_button = await page.query_selector('button:has-text("おすすめ順")')
        if sort_button:
            await sort_button.click()
            await page.wait_for_timeout(500)
            
            new_link = await page.query_selector('a:has-text("新着順")')
            if new_link:
                await new_link.click()
                await page.wait_for_timeout(2000)
                return True
    except:
        pass
    return False


async def extract_salons_with_urls(page: Page) -> list[dict]:
    """ページからサロン情報とURLを抽出（新着サロンスタッフ含む）"""
    
    script = """
    () => {
        const results = [];
        const addedUrls = new Set();
        
        // 方法1: 詳細を見るリンクから親要素を辿ってサロン情報を取得
        document.querySelectorAll('a[href^="/r/"]').forEach(link => {
            const href = link.getAttribute('href');
            if (!href || !/^\\/r\\/[A-Za-z0-9]+$/.test(href)) return;
            
            const fullUrl = 'https://minimodel.jp' + href;
            if (addedUrls.has(fullUrl)) return;
            
            // 親要素を辿って情報を探す
            let parent = link;
            let text = '';
            for (let i = 0; i < 10; i++) {
                parent = parent.parentElement;
                if (!parent) break;
                const pt = parent.innerText || '';
                if (pt.length > 100 && pt.length < 5000) {
                    text = pt;
                    break;
                }
            }
            
            if (!text) return;
            
            // お気に入り数を探す（❤️ 数字 または 数字のみの行）
            let favorites = -1;
            
            // ハートマーク付きの数字を探す
            const heartMatch = text.match(/[❤️♥💗🩷]\\s*(\\d+)/);
            if (heartMatch) {
                favorites = parseInt(heartMatch[1]);
            }
            
            // 「お気に入り」テキストの近くの数字
            if (favorites < 0) {
                const favTextMatch = text.match(/お気に入り[：:]?\\s*(\\d+)/);
                if (favTextMatch) {
                    favorites = parseInt(favTextMatch[1]);
                }
            }
            
            // 評価-レビュー-お気に入りパターン（例：4.9 20 581）
            if (favorites < 0) {
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                for (let i = 0; i < lines.length - 2; i++) {
                    const l1 = lines[i];
                    const l2 = lines[i+1];
                    const l3 = lines[i+2];
                    
                    if ((l1.match(/^[\\d.]+$/) || l1 === '-') &&
                        (l2.match(/^[\\d,]+$/) || l2 === '-') &&
                        l3.match(/^[\\d,]+$/)) {
                        favorites = parseInt(l3.replace(/,/g, ''));
                        break;
                    }
                }
            }
            
            if (favorites < 0) return;
            
            // サロン名を探す
            let name = '';
            const nameLinks = parent.querySelectorAll('a[href*="/r/"]');
            for (const nl of nameLinks) {
                const linkText = (nl.getAttribute('name') || nl.innerText || '').trim();
                if (linkText.includes('さんの詳細を見る')) {
                    name = linkText.replace('さんの詳細を見る', '').trim();
                    break;
                }
            }
            
            // テキストから名前を推測
            if (!name) {
                const lines = text.split('\\n').map(l => l.trim()).filter(l => l && l.length > 2);
                for (const line of lines) {
                    if (line.length > 2 && line.length < 50 &&
                        !line.match(/^[\\d.,¥]+/) &&
                        !line.includes('経験年数') &&
                        !line.includes('詳細を見る') &&
                        !line.includes('新規') &&
                        !line.includes('全員') &&
                        !line.includes('駅') &&
                        !line.includes('分')) {
                        name = line;
                        break;
                    }
                }
            }
            
            if (!name) return;
            
            // ジャンル検出
            let genre = '';
            if (text.includes('ネイル')) genre = 'ネイル';
            else if (text.includes('マツエク') || text.includes('まつげ') || text.includes('パーマ')) genre = 'マツエク・マツパ';
            else if (text.includes('眉')) genre = '眉毛';
            else if (text.includes('エステ') || text.includes('リラク') || text.includes('脱毛')) genre = 'エステ・リラク';
            else genre = '美容';
            
            results.push({
                name: name,
                genre: genre,
                favorites: favorites,
                url: fullUrl
            });
            addedUrls.add(fullUrl);
        });
        
        return results;
    }
    """
    
    try:
        return await page.evaluate(script)
    except Exception as e:
        print(f"Extract error: {e}")
        return []


async def get_salon_detail(page: Page, salon_url: str, prefecture: str) -> dict:
    """サロン詳細を取得（電話番号はリンククリックで取得）"""
    address = prefecture
    phone = ""
    
    try:
        # サロンページにアクセス
        await page.goto(salon_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)
        
        body = await page.evaluate('document.body.innerText')
        
        # 住所情報（駅情報を探す）
        match = re.search(r'([^\n]*駅[^\n]{0,20})', body)
        if match:
            address = f"{prefecture} {match.group(1).strip()}"
        
        # 電話番号リンクをクリック
        contact_link = await page.query_selector('a[href$="/tel"]')
        if contact_link:
            await contact_link.click()
            await page.wait_for_timeout(1500)
            
            tel_body = await page.evaluate('document.body.innerText')
            
            # 電話番号を探す（ハイフンなし10-11桁）
            phone_match = re.search(r'(\d{10,11})', tel_body)
            if phone_match:
                phone = phone_match.group(1)
            else:
                # ハイフンあり形式
                phone_match = re.search(r'(\d{2,4}-\d{2,4}-\d{4})', tel_body)
                if phone_match:
                    phone = phone_match.group(1)
        
    except Exception as e:
        pass
    
    return {"address": address, "phone": phone}


async def scrape_prefecture(
    page: Page,
    prefecture: str,
    max_favorites: int,
    existing_urls: set,
    progress_callback: Optional[Callable],
    target_categories: list[str] = None,
    max_pages: int = 5
) -> list[dict]:
    """都道府県をスクレイピング（カテゴリ別・ページネーション対応）"""
    
    results = []
    
    # 検索するカテゴリ（ヘアは除外）
    search_categories = target_categories if target_categories else list(CATEGORIES.keys())
    
    if progress_callback:
        progress_callback(f"🔍 {prefecture}")
    
    try:
        total_salons = 0
        
        # 各カテゴリごとに検索
        for cat in search_categories:
            cat_name = CATEGORIES.get(cat, cat)
            base_url = get_search_url(category=cat, area=prefecture)
            
            if progress_callback:
                progress_callback(f"  📂 {cat_name}")
            
            cat_salons = []
            
            # ページネーションでデータを読み込む
            for current_page in range(1, max_pages + 1):
                page_url = get_page_url(base_url, current_page)
                
                await page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                
                salons = await extract_salons_with_urls(page)
                
                # 新しいサロンを追加
                new_salons = [s for s in salons if s.get('url') and s['url'] not in [x.get('url') for x in cat_salons] and s['url'] not in existing_urls]
                
                if len(new_salons) == 0:
                    break
                    
                cat_salons.extend(new_salons)
                
                if progress_callback:
                    progress_callback(f"    ページ{current_page}: {len(new_salons)}件 (累計{len(cat_salons)}件)")
                
                # 次のページがあるか確認
                if current_page < max_pages:
                    has_next = await has_more_pages(page, current_page)
                    if not has_next:
                        break
            
            # お気に入り数でフィルターして結果に追加
            found = 0
            for salon in cat_salons:
                favorites = salon['favorites']
                name = salon['name']
                salon_url = salon.get('url', '')
                
                if not salon_url or salon_url in existing_urls:
                    continue
                
                if favorites <= max_favorites:
                    found += 1
                    if progress_callback:
                        progress_callback(f"    ✨ {name[:20]} お気に入り: {favorites}")
                    
                    # 詳細取得
                    detail = await get_salon_detail(page, salon_url, prefecture)
                    
                    results.append({
                        "サロン名": name,
                        "ジャンル": cat_name,
                        "住所": detail.get("address", prefecture),
                        "電話番号": detail.get("phone", ""),
                        "サロンURL": salon_url,
                        "いいね数": favorites,
                        "取得日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    existing_urls.add(salon_url)
            
            total_salons += len(cat_salons)
            if progress_callback:
                progress_callback(f"    → {cat_name}: {found}件発見 (全{len(cat_salons)}件中)")
        
        total = total_salons
        if progress_callback:
            progress_callback(f"📊 {prefecture}: {found}件発見 (全{total}件中)")
                
    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ {prefecture}: エラー - {str(e)[:30]}")
    
    return results


def get_page_url(base_url: str, page_num: int) -> str:
    """ページ番号付きURLを生成"""
    if page_num <= 1:
        return base_url
    
    if '?' in base_url:
        return f"{base_url}&p={page_num}"
    else:
        return f"{base_url}?p={page_num}"


async def has_more_pages(page: Page, current_page: int) -> bool:
    """次のページがあるか確認"""
    try:
        next_page = current_page + 1
        next_link = await page.query_selector(f'a:has-text("{next_page}")')
        if next_link:
            return True
        
        next_btn = await page.query_selector('a:has-text("次へ")')
        if next_btn:
            return True
    except:
        pass
    return False


async def scrape_category_nationwide(
    page: Page,
    category: str,
    max_favorites: int,
    existing_urls: set,
    progress_callback: Optional[Callable],
    max_pages: int = 10
) -> list[dict]:
    """カテゴリ全国検索（新着順・ページネーション対応）"""
    
    results = []
    category_name = CATEGORIES.get(category, category)
    base_url = get_search_url(category=category)
    
    if progress_callback:
        progress_callback(f"🌏 全国検索: {category_name}")
    
    try:
        all_salons = []
        
        # ページネーションでデータを読み込む
        for current_page in range(1, max_pages + 1):
            page_url = get_page_url(base_url, current_page)
            
            await page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            
            # 最初のページのみ新着順に切り替え
            if current_page == 1:
                sorted_ok = await click_sort_newest(page)
                if progress_callback and sorted_ok:
                    progress_callback(f"  → 新着順に切り替え完了")
            
            salons = await extract_salons_with_urls(page)
            
            # 新しいサロンを追加
            new_salons = [s for s in salons if s.get('url') and s['url'] not in [x.get('url') for x in all_salons]]
            
            if len(new_salons) == 0:
                if progress_callback:
                    progress_callback(f"  → ページ {current_page}: データなし、終了")
                break
                
            all_salons.extend(new_salons)
            
            if progress_callback:
                progress_callback(f"  ページ {current_page}: {len(new_salons)}件 (累計{len(all_salons)}件)")
            
            # 次のページがあるか確認
            if current_page < max_pages:
                has_next = await has_more_pages(page, current_page)
                if not has_next:
                    if progress_callback:
                        progress_callback(f"  → 最終ページ")
                    break
        
        found = 0
        for salon in all_salons:
            favorites = salon['favorites']
            name = salon['name']
            salon_url = salon.get('url', '')
            genre = salon.get('genre', '')
            
            if not salon_url or salon_url in existing_urls:
                continue
            
            if favorites <= max_favorites:
                found += 1
                if progress_callback:
                    progress_callback(f"✨ {name[:20]} ({genre}) お気に入り: {favorites}")
                
                # 詳細取得
                detail = await get_salon_detail(page, salon_url, "")
                
                results.append({
                    "サロン名": name,
                    "ジャンル": category_name,
                    "住所": detail.get("address", ""),
                    "電話番号": detail.get("phone", ""),
                    "サロンURL": salon_url,
                    "いいね数": favorites,
                    "取得日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                existing_urls.add(salon_url)
                
                # 検索ページに戻る
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)
                await click_sort_newest(page)
        
        total = len(all_salons)
        if progress_callback:
            progress_callback(f"📊 {category_name}全国: {found}件発見 (全{total}件中)")
                
    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ {category_name}: エラー - {str(e)[:30]}")
    
    return results


async def scrape_minimo(
    categories: list[str] = None,
    max_likes: int = 5,
    existing_urls: set = None,
    progress_callback: Optional[Callable] = None,
    prefectures: list[str] = None,
    max_pages: int = 5,
    nationwide: bool = False
) -> list[dict]:
    """ミニモをスクレイピング（ページネーション対応）"""
    
    if existing_urls is None:
        existing_urls = set()
    
    if prefectures is None:
        prefectures = SMALL_PREFECTURES
    
    all_results = []
    
    # カテゴリが指定されていない場合、全カテゴリ
    if categories is None:
        categories = list(CATEGORIES.keys())
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        )
        page = await context.new_page()
        
        try:
            if nationwide:
                # 全国検索モード（カテゴリごとに新着順で検索）
                for cat in categories:
                    results = await scrape_category_nationwide(
                        page=page,
                        category=cat,
                        max_favorites=max_likes,
                        existing_urls=existing_urls,
                        progress_callback=progress_callback,
                        max_pages=max_pages
                    )
                    all_results.extend(results)
            else:
                # 都道府県検索モード
                for pref in prefectures:
                    results = await scrape_prefecture(
                        page=page,
                        prefecture=pref,
                        max_favorites=max_likes,
                        existing_urls=existing_urls,
                        progress_callback=progress_callback,
                        target_categories=categories,
                        max_pages=max_pages
                    )
                    all_results.extend(results)
                    
        finally:
            await browser.close()
    
    if progress_callback:
        progress_callback(f"✅ 完了！ 合計 {len(all_results)} 件")
    
    return all_results


def run_scraper(
    categories: list[str] = None,
    max_likes: int = 5,
    existing_urls: set = None,
    progress_callback: Optional[Callable] = None,
    max_pages: int = 5,
    nationwide: bool = False
) -> list[dict]:
    """同期実行"""
    return asyncio.run(scrape_minimo(
        categories=categories,
        max_likes=max_likes,
        existing_urls=existing_urls,
        progress_callback=progress_callback,
        max_pages=max_pages,
        nationwide=nationwide
    ))


if __name__ == "__main__":
    def print_progress(msg):
        print(msg)
    
    print("=== テスト開始 ===")
    results = run_scraper(
        categories=None,  # 全カテゴリ
        max_likes=20,
        progress_callback=print_progress,
        max_pages=3
    )
    
    print(f"\n=== 結果: {len(results)}件 ===")
    for r in results:
        print(f"- {r['サロン名'][:20]} ({r['ジャンル']}): お気に入り{r['いいね数']}")
