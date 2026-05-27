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


class ProgressTracker:
    """スクレイピング進捗を管理"""

    def __init__(self, callback: Optional[Callable[[str, int], None]] = None):
        self.callback = callback
        self.listing_total = 1
        self.listing_done = 0
        self.detail_total = 0
        self.detail_done = 0
        self.message = ""

    def configure_listing(self, total: int):
        self.listing_total = max(total, 1)
        self.listing_done = 0
        self.detail_total = 0
        self.detail_done = 0

    def add_detail_total(self, count: int):
        self.detail_total += count

    def listing_step(self, message: str):
        self.listing_done += 1
        self.message = message
        self._notify()

    def detail_step(self, message: str):
        self.detail_done += 1
        self.message = message
        self._notify()

    def set_message(self, message: str):
        self.message = message
        self._notify()

    @property
    def percent(self) -> int:
        listing_p = self.listing_done / self.listing_total
        if self.detail_total == 0:
            return min(int(listing_p * 99), 99)
        detail_p = self.detail_done / self.detail_total
        combined = listing_p * 0.7 + detail_p * 0.3
        return min(int(combined * 100), 99)

    def complete(self, message: str):
        self.message = message
        if self.callback:
            self.callback(message, 100)

    def _notify(self):
        if self.callback:
            self.callback(self.message, self.percent)


# カテゴリ（検出用）
CATEGORIES = {
    "nail": "ネイル",
    "eyelash": "マツエク・マツパ",
    "eyebrow": "眉毛",
    "relaxation": "エステ・リラク",
    "other": "その他美容",
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
    """検索URLを生成（カテゴリ+都道府県キーワード）"""
    base_url = "https://minimodel.jp/search?"
    params = []

    if category:
        params.append(f"category={category}")
    if area:
        # area= は結果が全国になるため keyword= を使用
        encoded_area = urllib.parse.quote(area)
        params.append(f"keyword={encoded_area}")

    params.append("order=updated_datetime")

    return base_url + "&".join(params) if params else base_url


def normalize_prefecture(name: str) -> str:
    """パンくず等の短い地名を都道府県名に正規化"""
    if not name:
        return ""
    name = name.strip().split("\n")[0].strip()
    if name in PREFECTURES:
        return name
    if name == "東京":
        return "東京都"
    for pref in PREFECTURES:
        base = pref.replace("県", "").replace("府", "").replace("都", "")
        if name == base:
            return pref
    return name


def prefecture_matches(detected: str, target: str) -> bool:
    """検出した都道府県が検索対象と一致するか"""
    return normalize_prefecture(detected) == normalize_prefecture(target)


async def extract_location_from_page(page: Page) -> dict:
    """サロン詳細ページから都道府県・住所情報を取得"""
    location = {"prefecture": "", "address": "", "station": ""}

    try:
        links = await page.evaluate(
            """
            () => [...document.querySelectorAll('a')]
                .map(a => (a.innerText || '').trim().split('\\n')[0])
                .filter(Boolean)
            """
        )

        prefecture = ""
        city = ""
        station = ""

        if "トップ" in links:
            top_idx = links.index("トップ")
            breadcrumb = links[top_idx + 1: top_idx + 10]

            pref_idx = -1
            for i, t in enumerate(breadcrumb):
                if normalize_prefecture(t) in PREFECTURES:
                    prefecture = normalize_prefecture(t)
                    pref_idx = i
                    break

            if pref_idx >= 0:
                for t in breadcrumb[pref_idx + 1:]:
                    if "駅" in t:
                        station = t
                        break
                    if (
                        normalize_prefecture(t) not in PREFECTURES
                        and len(t) <= 20
                        and t not in {"フォト", "メニュー", "口コミ"}
                    ):
                        city = t

        body = await page.evaluate("document.body.innerText")

        if not station:
            match = re.search(r"([^\n]{0,25}駅[^\n]{0,25})", body)
            if match:
                station = match.group(1).strip()

        location["prefecture"] = prefecture
        location["station"] = station

        parts = [p for p in [prefecture, city, station] if p]
        location["address"] = " ".join(parts)

        if not location["address"]:
            zip_match = re.search(r"〒\d{3}-\d{4}[^\n]+", body)
            if zip_match:
                location["address"] = zip_match.group(0).strip()

    except Exception:
        pass

    return location

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


async def get_salon_detail(page: Page, salon_url: str, target_prefecture: str = "") -> dict:
    """サロン詳細を取得（都道府県確認・電話番号は/telリンクから）"""
    phone = ""
    location = {"prefecture": "", "address": "", "station": ""}

    try:
        await page.goto(salon_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)

        location = await extract_location_from_page(page)

        contact_link = await page.query_selector('a[href$="/tel"]')
        if contact_link:
            await contact_link.click()
            await page.wait_for_timeout(1500)

            tel_body = await page.evaluate('document.body.innerText')

            phone_match = re.search(r'(\d{10,11})', tel_body)
            if phone_match:
                phone = phone_match.group(1)
            else:
                phone_match = re.search(r'(\d{2,4}-\d{2,4}-\d{4})', tel_body)
                if phone_match:
                    phone = phone_match.group(1)

    except Exception:
        pass

    return {
        "prefecture": location.get("prefecture", ""),
        "address": location.get("address", ""),
        "station": location.get("station", ""),
        "phone": phone,
        "matches_target": (
            not target_prefecture
            or prefecture_matches(location.get("prefecture", ""), target_prefecture)
        ),
    }


async def scrape_prefecture(
    page: Page,
    prefecture: str,
    max_favorites: int,
    existing_urls: set,
    progress: Optional[ProgressTracker],
    target_categories: list[str] = None,
    max_pages: int = 5
) -> list[dict]:
    """都道府県をスクレイピング（カテゴリ別・ページネーション対応）"""
    
    results = []
    
    # 検索するカテゴリ（ヘアは除外）
    search_categories = target_categories if target_categories else list(CATEGORIES.keys())
    
    if progress:
        progress.set_message(f"🔍 {prefecture}")
    
    try:
        total_salons = 0
        found = 0
        
        # 各カテゴリごとに検索
        for cat in search_categories:
            cat_name = CATEGORIES.get(cat, cat)
            base_url = get_search_url(category=cat, area=prefecture)
            
            if progress:
                progress.set_message(f"  📂 {cat_name}")
            
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
                    if progress:
                        progress.listing_step(f"    ページ{current_page}: データなし、終了")
                    break
                    
                cat_salons.extend(new_salons)
                
                if progress:
                    progress.listing_step(f"    ページ{current_page}: {len(new_salons)}件 (累計{len(cat_salons)}件)")
                
                # 次のページがあるか確認
                if current_page < max_pages:
                    has_next = await has_more_pages(page, current_page)
                    if not has_next:
                        break
            
            # お気に入り数でフィルターして結果に追加
            matching = [
                s for s in cat_salons
                if s.get('url') and s['url'] not in existing_urls and s['favorites'] <= max_favorites
            ]
            if progress:
                progress.add_detail_total(len(matching))

            found = 0
            for salon in matching:
                favorites = salon['favorites']
                name = salon['name']
                salon_url = salon['url']

                detail = await get_salon_detail(page, salon_url, prefecture)

                if not detail.get("matches_target"):
                    if progress:
                        detected = detail.get("prefecture") or "不明"
                        progress.set_message(
                            f"    ⏭️ {name[:20]} スキップ（{detected} ≠ {prefecture}）"
                        )
                    continue

                found += 1
                if progress:
                    progress.detail_step(f"    ✨ {name[:20]} お気に入り: {favorites}")

                results.append({
                    "サロン名": name,
                    "ジャンル": cat_name,
                    "住所": detail.get("address") or prefecture,
                    "電話番号": detail.get("phone", ""),
                    "サロンURL": salon_url,
                    "いいね数": favorites,
                    "取得日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

                existing_urls.add(salon_url)
            
            total_salons += len(cat_salons)
            if progress:
                progress.set_message(f"    → {cat_name}: {found}件発見 (全{len(cat_salons)}件中)")
        
        total = total_salons
        if progress:
            progress.set_message(f"📊 {prefecture}: {found}件発見 (全{total}件中)")
                
    except Exception as e:
        if progress:
            progress.set_message(f"⚠️ {prefecture}: エラー - {str(e)[:30]}")
    
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
    progress: Optional[ProgressTracker],
    max_pages: int = 10
) -> list[dict]:
    """カテゴリ全国検索（新着順・ページネーション対応）"""
    
    results = []
    category_name = CATEGORIES.get(category, category)
    base_url = get_search_url(category=category)
    
    if progress:
        progress.set_message(f"🌏 全国検索: {category_name}")
    
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
                if progress and sorted_ok:
                    progress.set_message(f"  → 新着順に切り替え完了")
            
            salons = await extract_salons_with_urls(page)
            
            # 新しいサロンを追加
            new_salons = [s for s in salons if s.get('url') and s['url'] not in [x.get('url') for x in all_salons]]
            
            if len(new_salons) == 0:
                if progress:
                    progress.listing_step(f"  → ページ {current_page}: データなし、終了")
                break
                
            all_salons.extend(new_salons)
            
            if progress:
                progress.listing_step(f"  ページ {current_page}: {len(new_salons)}件 (累計{len(all_salons)}件)")
            
            # 次のページがあるか確認
            if current_page < max_pages:
                has_next = await has_more_pages(page, current_page)
                if not has_next:
                    if progress:
                        progress.set_message(f"  → 最終ページ")
                    break
        
        matching = [
            s for s in all_salons
            if s.get('url') and s['url'] not in existing_urls and s['favorites'] <= max_favorites
        ]
        if progress:
            progress.add_detail_total(len(matching))

        found = 0
        for salon in matching:
            favorites = salon['favorites']
            name = salon['name']
            salon_url = salon['url']
            genre = salon.get('genre', '')

            detail = await get_salon_detail(page, salon_url, "")

            found += 1
            if progress:
                progress.detail_step(f"✨ {name[:20]} ({genre}) お気に入り: {favorites}")

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

            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)
            await click_sort_newest(page)
        
        total = len(all_salons)
        if progress:
            progress.set_message(f"📊 {category_name}全国: {found}件発見 (全{total}件中)")
                
    except Exception as e:
        if progress:
            progress.set_message(f"⚠️ {category_name}: エラー - {str(e)[:30]}")
    
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
    from playwright_setup import ensure_playwright_browsers

    ensure_playwright_browsers()

    if existing_urls is None:
        existing_urls = set()
    
    if prefectures is None:
        prefectures = SMALL_PREFECTURES
    
    all_results = []
    
    # カテゴリが指定されていない場合、全カテゴリ
    if categories is None:
        categories = list(CATEGORIES.keys())

    tracker = None
    if progress_callback:
        listing_total = len(categories) * max_pages
        if not nationwide:
            listing_total *= len(prefectures)
        tracker = ProgressTracker(progress_callback)
        tracker.configure_listing(listing_total)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
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
                        progress=tracker,
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
                        progress=tracker,
                        target_categories=categories,
                        max_pages=max_pages
                    )
                    all_results.extend(results)
                    
        finally:
            await browser.close()
    
    if tracker:
        tracker.complete(f"✅ 完了！ 合計 {len(all_results)} 件")
    elif progress_callback:
        progress_callback(f"✅ 完了！ 合計 {len(all_results)} 件", 100)
    
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
    def print_progress(msg, percent=0):
        print(f"[{percent:3d}%] {msg}")
    
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
