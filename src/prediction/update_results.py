"""
python code/a4_prediction/m05_update_results.py

 C:\KeibaAI\code\a4_prediction\m05_update_results.py (最終完成版)

 ■ スクリプトの目的
 AI予測を完了したレースについて、レース終了後にNetkeibaから実際の確定結果を収集し、
 データベース (SQLite) を更新すること。
 これにより、予測データと実際の着順・払い戻し情報が結合され、
 モデルの評価（的中率、回収率の計算など）に必要なデータ基盤を確立する。

 ■ 主な機能
 1. 未更新レースの特定: predictionsテーブルでresult_rankがNULLのレースIDをリストアップ。
 2. 結果のスクレイピング: Netkeibaのレース結果ページから以下の情報を抽出。
    - 各馬の確定情報: 実際の着順、レース終了時点の最終オッズ・人気。
    - 払い戻し情報: 単勝、複勝、三連単などの配当結果。
 3. データベースの更新: 
    - predictionsテーブル: 実際の着順 (result_rank)、最終オッズ、最終人気を追記。
    - payoutsテーブル: 払い戻し情報 (配当、的中番号) を保存。

 ■ 実行方法
 python code/a4_prediction/m05_update_results.py

 ■ 依存関係
 - config.py: DB_PATH (データベースパス) の設定。
 - 予測が完了し、predictionsテーブルが作成されていること。
 - requests, bs4, sqlite3, pandas モジュール

 ■ 注意事項
 - Netkeibaへのアクセスが発生するため、config.pyで設定された待機時間 (time.sleep) を遵守する。
 - 404や解析エラーが発生した場合、該当レースをスキップし、他のレースの処理を続行する。

"""

import os
import sys
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
import json
from typing import Dict, Any, List, Tuple
import traceback

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__)); PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..')); sys.path.append(PROJECT_ROOT); sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
import config

def setup_database(conn):
    # (変更なし)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payouts (
        race_id TEXT PRIMARY KEY, tansho_payout INTEGER, tansho_numbers TEXT,
        fukusho_payouts TEXT, wakuren_payout INTEGER, wakuren_numbers TEXT,
        umaren_payout INTEGER, umaren_numbers TEXT, wide_payouts TEXT,
        umatan_payout INTEGER, umatan_numbers TEXT, sanrenpuku_payout INTEGER,
        sanrenpuku_numbers TEXT, sanrentan_payout INTEGER, sanrentan_numbers TEXT
    );
    """)
    conn.commit()

def get_pending_race_ids(db_path: str) -> List[str]:
    # (変更なし - 前回修正版のまま)
    if not os.path.exists(db_path): return []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query_pred = "SELECT DISTINCT race_id FROM predictions WHERE result_rank IS NULL;"
            cursor.execute(query_pred); pending_by_rank = {row[0] for row in cursor.fetchall()}
            pending_by_payout = set()
            try:
                cursor.execute("SELECT race_id FROM payouts;"); existing_payout_ids = {row[0] for row in cursor.fetchall()}
                cursor.execute("SELECT DISTINCT race_id FROM predictions;"); all_prediction_ids = {row[0] for row in cursor.fetchall()}
                pending_by_payout = all_prediction_ids - existing_payout_ids
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    cursor.execute("SELECT DISTINCT race_id FROM predictions;"); pending_by_payout = {row[0] for row in cursor.fetchall()}
                else: raise e
            return sorted(list(pending_by_rank | pending_by_payout))
    except Exception as e:
        print(f"[ERROR] DBからのレースID取得中にエラー: {e}"); return []

def parse_payouts_for_db(soup: BeautifulSoup) -> Dict[str, Any]:
    """払い戻し情報を解析し、DB保存用の辞書を作成する (バグ修正・堅牢化版)"""
    payout_data_for_db = {}
    pay_block = soup.find('dl', class_='pay_block')
    if not pay_block: return payout_data_for_db
    payout_map = {
        'tan': 'tansho', 'fuku': 'fukusho', 'waku': 'wakuren', 'uren': 'umaren',
        'wide': 'wide', 'utan': 'umatan', 'sanfuku': 'sanrenpuku', 'santan': 'sanrentan'
    }
    for row in pay_block.find_all('tr'):
        th = row.find('th')
        if not th or not th.has_attr('class') or not th.get('class')[0] in payout_map: continue
        key_prefix = payout_map[th.get('class')[0]]
        try:
            tds = row.find_all('td')
            if len(tds) < 2: continue
            
            # get_text(separator)を使い、<br>タグを安全に処理する
            nums_text = [n.strip() for n in tds[0].get_text(separator='<br>').split('<br>') if n.strip()]
            payouts = [int(p.strip().replace(',', '')) for p in tds[1].get_text(separator='<br>').split('<br>') if p.strip().replace(',', '').isdigit()]

            if not payouts: continue
            if key_prefix in ['fukusho', 'wide']:
                payout_data_for_db[f'{key_prefix}_payouts'] = json.dumps({num: pay for num, pay in zip(nums_text, payouts)}, ensure_ascii=False)
            else:
                payout_data_for_db[f'{key_prefix}_payout'] = payouts[0]
                payout_data_for_db[f'{key_prefix}_numbers'] = nums_text[0]
        except Exception as e: print(f"  [PARSER WARN] '{key_prefix}'の解析中にエラー: {e}"); continue
    return payout_data_for_db

def scrape_race_results(race_id: str) -> Tuple[pd.DataFrame, dict]:
    """着順、最終オッズ/人気、払い戻し情報を取得する (結果確定後の最新HTMLを常に取得するためforce_fetch=True)"""
    from data_collection.html_downloader import HTMLDownloader

    # HTMLDownloaderの初期化 (キャッシュディレクトリを指定)
    downloader = HTMLDownloader(
        save_dir=os.path.join(PROJECT_ROOT, "data", "raw_html"),
        wait_time=1.0
    )
    
    try:
        # ローカルキャッシュがある場合でも結果が載っていない可能性があるため、
        # force_fetch=True を指定して常にネットから最新の確定結果を取得・上書きします。
        html_content = downloader.get_html(race_id, force_fetch=True)
        if not html_content:
            return pd.DataFrame(), {}

        soup = BeautifulSoup(html_content, 'html.parser')
        results_table = soup.find('table', class_='race_table_01')
        if not results_table:
            return pd.DataFrame(), {}
        
        payouts_for_db = parse_payouts_for_db(soup)
        
        headers_text = [th.text.strip() for th in results_table.find_all('tr')[0].find_all(['th', 'td'])]
        try:
            odds_idx = headers_text.index('単勝')
            ninki_idx = headers_text.index('人気')
        except ValueError:
            odds_idx, ninki_idx = 12, 13

        race_results = []
        for row in results_table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) <= max(odds_idx, ninki_idx): continue
            try:
                umaban = int(cols[2].text.strip())
            except (ValueError, IndexError):
                continue
                
            try:
                rank_str = cols[0].text.strip()
                rank = int(rank_str) if rank_str.isdigit() else 99
            except Exception:
                rank = 99
                
            try:
                final_odds = float(cols[odds_idx].text.strip())
            except Exception:
                final_odds = 0.0
                
            try:
                final_ninki = int(cols[ninki_idx].text.strip())
            except Exception:
                final_ninki = 0
                
            race_results.append({
                'umaban': umaban, 
                'result_rank': rank,
                'tansho_odds': final_odds,
                'tansho_ninki': final_ninki
            })
        return pd.DataFrame(race_results), payouts_for_db
    except Exception as e:
        print(f"  [ERROR] 結果パース・取得中に予期せぬエラー (race_id: {race_id}): {e}"); return pd.DataFrame(), {}

def update_database(db_path: str, race_id: str, results_df: pd.DataFrame, payouts_data: dict):
    """データベースのpredictionsとpayoutsテーブルを更新する"""
    if results_df.empty or not payouts_data:
        print(f"  [INFO] 更新に必要なデータが不足 (race_id: {race_id})。"); return
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor(); setup_database(conn)
            
            # ★★★ ここからが修正箇所 ★★★
            # 1. predictionsテーブルの着順、最終オッズ、最終人気を更新
            update_count = 0
            for _, row in results_df.iterrows():
                query = """
                UPDATE predictions 
                SET result_rank = ?, tansho_odds = ?, tansho_ninki = ? 
                WHERE race_id = ? AND umaban = ?;
                """
                params = (
                    int(row['result_rank']), 
                    row['tansho_odds'], 
                    int(row['tansho_ninki']),
                    race_id, 
                    int(row['umaban'])
                )
                cursor.execute(query, params); update_count += cursor.rowcount
            print(f"  -> [predictions]テーブルを更新: {update_count}件")
            # ★★★ 修正ここまで ★★★

            # 2. payoutsテーブルに払い戻し情報を保存
            payouts_data['race_id'] = race_id
            columns = ', '.join(payouts_data.keys()); placeholders = ', '.join(['?'] * len(payouts_data))
            query = f"INSERT OR REPLACE INTO payouts ({columns}) VALUES ({placeholders});"
            cursor.execute(query, list(payouts_data.values()))
            print(f"  -> [payouts]テーブルを更新: 1件")
            conn.commit()
    except sqlite3.Error as e:
        print(f"  [DB ERROR] DB更新中にエラー: {e}"); traceback.print_exc()

def main():
    # (変更なし)
    print("--- [START] レース結果更新スクリプト (最終完成版) ---")
    db_path = config.DB_PATH
    if not os.path.exists(db_path):
        print(f"DB '{db_path}' が見つかりません。先に予測を実行してください。"); print("--- [HALT] ---"); return
    pending_ids = get_pending_race_ids(db_path)
    if not pending_ids:
        print("すべてのレース結果は最新です。"); print("--- [COMPLETE] ---"); return
    print(f"{len(pending_ids)}件の未更新レースが見つかりました。")
    for i, race_id in enumerate(pending_ids):
        print(f"\n[{i+1}/{len(pending_ids)}] 処理中 race_id: {race_id}")
        results_df, payouts_data = scrape_race_results(race_id)
        update_database(db_path, race_id, results_df, payouts_data)
        time.sleep(1)
    print("\n--- [COMPLETE] すべての処理が完了しました。 ---")

if __name__ == "__main__":
    main()