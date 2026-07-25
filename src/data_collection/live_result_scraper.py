import os
import sys
import time
import requests
import json
import pandas as pd
from bs4 import BeautifulSoup
from typing import Tuple, Dict, Any, Optional

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config


def fetch_live_html(race_id: str) -> Optional[str]:
    """
    race.netkeiba.com から当日の確定速報HTMLを取得する。
    """
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        time.sleep(0.5)
        # race.netkeiba は EUC-JP または UTF-8 (encoding判定)
        r.encoding = r.apparent_encoding or 'euc-jp'
        return r.text
    except Exception as e:
        print(f"[WARN] Failed to fetch live race result for {race_id}: {e}")
        return None


def parse_live_race_html(html_content: str, race_id: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    race.netkeiba.com のHTMLから着順と払い戻し情報(payouts)をパースする。
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. 着順テーブルのパース (RaceTable01 または .ResultTable)
    results = []
    table = soup.find('table', class_=lambda c: c and ('RaceTable01' in c or 'ResultTable' in c))
    
    if table:
        for row in table.find_all('tr'):
            # ヘッダー行をスキップ
            if row.find('th'):
                continue
            
            cols = row.find_all('td')
            if len(cols) < 3:
                continue
            
            try:
                # 着順
                rank_text = cols[0].text.strip()
                if not rank_text.isdigit():
                    # 中止、失格などの場合
                    result_rank = 99
                else:
                    result_rank = int(rank_text)

                # 馬番 (通常 col 2 または 1)
                umaban_elem = row.find(class_=lambda c: c and 'Umaban' in c)
                if umaban_elem:
                    umaban = int(umaban_elem.text.strip())
                else:
                    umaban = int(cols[2].text.strip())

                # 馬名
                horse_elem = row.find(class_=lambda c: c and 'Horse' in c)
                if horse_elem and horse_elem.find('a'):
                    horse_name = horse_elem.find('a').text.strip()
                else:
                    horse_name = cols[3].text.strip() if len(cols) > 3 else "不明"

                # 単勝オッズ
                odds_elem = row.find(class_=lambda c: c and ('Odds' in c or 'Popular' in c))
                odds = 0.0
                if odds_elem:
                    try:
                        odds = float(odds_elem.text.strip().replace(',', ''))
                    except ValueError:
                        odds = 0.0

                results.append({
                    'race_id': race_id,
                    'result_rank': result_rank,
                    'umaban': umaban,
                    'horse_name': horse_name,
                    'tansho_odds': odds
                })
            except Exception:
                continue

    results_df = pd.DataFrame(results)

    # 2. 払い戻しテーブルのパース (ResultPayBack)
    payouts_data = {'race_id': race_id}
    payback_tables = soup.find_all('table', class_=lambda c: c and 'PayBack' in c)
    if not payback_tables:
        payback_tables = soup.find_all('div', class_=lambda c: c and 'PayBack' in c)

    for p_table in payback_tables:
        for tr in p_table.find_all('tr'):
            th = tr.find('th')
            tds = tr.find_all('td')
            if not th or len(tds) < 2:
                continue
            
            pay_type = th.text.strip()
            num_text = tds[0].text.strip()
            pay_text = tds[1].text.strip()

            # 単勝
            if '単勝' in pay_type:
                try:
                    payouts_data['tansho_numbers'] = num_text
                    payouts_data['tansho_payout'] = int(pay_text.replace('円', '').replace(',', '').strip())
                except ValueError:
                    pass

            # 複勝
            elif '複勝' in pay_type:
                try:
                    nums = [n.strip() for n in num_text.split('<br>') if n.strip()] if '<br>' in num_text else [n.strip() for n in num_text.split('\n') if n.strip()]
                    pays = [int(p.replace('円', '').replace(',', '').strip()) for p in pay_text.split('\n') if p.replace('円', '').replace(',', '').strip().isdigit()]
                    if not nums or not pays:
                        # タグ区切りの試行
                        nums = [tds[0].get_text(separator='|').split('|')[0].strip()]
                    
                    fukusho_dict = {}
                    for n, p in zip(nums, pays):
                        if n.isdigit():
                            fukusho_dict[n] = p
                    payouts_data['fukusho_payouts'] = json.dumps(fukusho_dict, ensure_ascii=False)
                except Exception:
                    pass

            # 馬連
            elif '馬連' in pay_type:
                try:
                    payouts_data['umaren_numbers'] = num_text
                    payouts_data['umaren_payout'] = int(pay_text.replace('円', '').replace(',', '').strip())
                except ValueError:
                    pass

            # ワイド
            elif 'ワイド' in pay_type:
                try:
                    payouts_data['wide_payouts'] = json.dumps({num_text: int(pay_text.replace('円', '').replace(',', '').strip())}, ensure_ascii=False)
                except Exception:
                    pass

            # 三連複
            elif '3連複' in pay_type or '三連複' in pay_type:
                try:
                    payouts_data['sanrenpuku_numbers'] = num_text
                    payouts_data['sanrenpuku_payout'] = int(pay_text.replace('円', '').replace(',', '').strip())
                except ValueError:
                    pass

            # 三連単
            elif '3連単' in pay_type or '三連単' in pay_type:
                try:
                    payouts_data['sanrentan_numbers'] = num_text
                    payouts_data['sanrentan_payout'] = int(pay_text.replace('円', '').replace(',', '').strip())
                except ValueError:
                    pass

    return results_df, payouts_data


def get_live_race_result(race_id: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    指定レースの当日確定速報結果を取得する。
    """
    html = fetch_live_html(race_id)
    if not html:
        return pd.DataFrame(), {}
    return parse_live_race_html(html, race_id)


if __name__ == "__main__":
    # テスト実行 (例: 札幌9R 202601010109)
    test_id = "202601010109"
    print(f"Testing live_result_scraper for race_id: {test_id}...")
    res_df, pay_dict = get_live_race_result(test_id)
    print("\n--- Results DF ---")
    print(res_df.head(5))
    print("\n--- Payouts Dict ---")
    print(pay_dict)
