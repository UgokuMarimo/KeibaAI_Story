# C:\KeibaAI\src\utils\result_scraper.py

"""
レース確定結果の取得ユーティリティ。

HTMLDownloader（キャッシュ優先）と NetkeibaParser を使って
ローカルキャッシュ済みのHTMLから直接データを抽出します。
すでにスクレイピング済みのレースについてはネットアクセスが発生しません。
"""

import os
import sys
import re
from typing import Optional, List, Tuple

from bs4 import BeautifulSoup

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from data_collection.html_downloader import HTMLDownloader

# キャッシュHTMLの保存先（html_downloader と共通）
_HTML_SAVE_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw_html')

# シングルトン的に使い回す HTMLDownloader インスタンス
_downloader = HTMLDownloader(save_dir=_HTML_SAVE_DIR, wait_time=1.0)


def _get_soup(race_id: str) -> Optional[BeautifulSoup]:
    """
    指定レースIDのHTMLを取得して BeautifulSoup オブジェクトを返す。
    キャッシュがあればネットアクセスなし。なければダウンロードしてキャッシュ保存。
    """
    html_content = _downloader.get_html(race_id)
    if not html_content:
        return None
    return BeautifulSoup(html_content, "html.parser")


def get_tansho_result(race_id: str) -> Tuple[Optional[List[int]], Optional[List[int]]]:
    """
    指定されたレースIDの確定結果から、1着の馬番リストおよび
    単勝払戻金（配当）リストを取得する。
    キャッシュHTMLがあれば再スクレイピングなしで即座に返す。
    同着の場合は複数の要素を返す。

    Args:
        race_id: 12桁のレースID

    Returns:
        (馬番リスト, 払戻金リスト)。まだ結果がない、またはエラーの場合は (None, None)
    """
    soup = _get_soup(race_id)
    if soup is None:
        print(f"[SCRAPER ERROR] Failed to get HTML for race {race_id}")
        return None, None

    # 払戻金テーブルを検索
    pay_table = soup.find("table", class_="pay_table_01")
    if not pay_table:
        # 払い戻しテーブルがない = まだ結果が反映されていない
        return None, None

    tansho_row = None
    for tr in pay_table.find_all("tr"):
        th = tr.find("th")
        if th and "単勝" in th.get_text(strip=True):
            tansho_row = tr
            break

    if not tansho_row:
        return None, None

    tds = tansho_row.find_all("td")
    if len(tds) < 2:
        return None, None

    # 同着時などの br タグを改行コードに変換
    for br in tds[0].find_all("br"):
        br.replace_with("\n")
    for br in tds[1].find_all("br"):
        br.replace_with("\n")

    umaban_text = tds[0].get_text().strip()
    payout_text = tds[1].get_text().strip()

    umaban_list = []
    payout_list = []

    for u in umaban_text.split("\n"):
        u_cleaned = re.sub(r'\D', '', u)
        if u_cleaned:
            umaban_list.append(int(u_cleaned))

    for p in payout_text.split("\n"):
        p_cleaned = re.sub(r'\D', '', p)
        if p_cleaned:
            payout_list.append(int(p_cleaned))

    if not umaban_list or not payout_list:
        return None, None

    return umaban_list, payout_list


def get_race_odds_and_popularity(race_id: str) -> Optional[dict]:
    """
    指定されたレースIDの確定結果から、全出走馬の確定単勝オッズおよび人気を取得する。
    キャッシュHTMLがあれば再スクレイピングなしで即座に返す。

    Returns:
        {馬番(int): {'odds': float, 'ninki': int}}
    """
    soup = _get_soup(race_id)
    if soup is None:
        print(f"[SCRAPER ERROR] Failed to get HTML for odds of {race_id}")
        return None

    table = soup.find("table", class_="race_table_01")
    if not table:
        return None

    rows = table.find_all("tr")
    if len(rows) <= 1:
        return None

    # ヘッダーから列インデックスを取得
    ths = rows[0].find_all("th")
    umaban_idx = -1
    odds_idx = -1
    ninki_idx = -1

    for idx, th in enumerate(ths):
        text = th.get_text(strip=True)
        if "馬番" in text:
            umaban_idx = idx
        elif "単勝" in text:
            odds_idx = idx
        elif "人気" in text:
            ninki_idx = idx

    # フォールバック
    if umaban_idx == -1: umaban_idx = 2
    if odds_idx == -1: odds_idx = 16
    if ninki_idx == -1: ninki_idx = 17

    results = {}
    for row in rows[1:]:
        tds = row.find_all("td")
        if len(tds) <= max(umaban_idx, odds_idx, ninki_idx):
            continue
        try:
            u_text = tds[umaban_idx].get_text(strip=True)
            u_cleaned = re.sub(r'\D', '', u_text)
            if not u_cleaned:
                continue
            umaban = int(u_cleaned)

            o_text = tds[odds_idx].get_text(strip=True)
            o_cleaned = re.sub(r'[^\d.]', '', o_text)
            odds_val = float(o_cleaned) if o_cleaned else 0.0

            n_text = tds[ninki_idx].get_text(strip=True)
            n_cleaned = re.sub(r'\D', '', n_text)
            ninki_val = int(n_cleaned) if n_cleaned else 0

            results[umaban] = {
                'odds': odds_val,
                'ninki': ninki_val
            }
        except Exception:
            continue

    return results


# 単体テスト用コード
if __name__ == "__main__":
    test_race_id = "202665052401"
    print(f"Testing scraper for race_id: {test_race_id}")
    u_list, p_list = get_tansho_result(test_race_id)
    print(f"Result - Horse ID: {u_list}, Payout: {p_list}")

    print("\nTesting odds and popularity scraper:")
    odds_pop = get_race_odds_and_popularity(test_race_id)
    if odds_pop:
        print(f"Successfully scraped odds for {len(odds_pop)} horses.")
        for k, v in list(odds_pop.items())[:3]:
            print(f"  Horse {k}番: Odds={v['odds']}, Popularity={v['ninki']}")
    else:
        print("Failed to scrape odds and popularity.")
