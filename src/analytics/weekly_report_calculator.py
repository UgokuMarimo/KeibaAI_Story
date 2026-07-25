import os
import sys
import sqlite3
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config
from data_collection.live_result_scraper import get_live_race_result


def get_votes_for_date_range(start_date: str, end_date: str) -> pd.DataFrame:
    """
    指定日付範囲の votes テーブルレコードを取得する。
    """
    conn = sqlite3.connect(config.DB_PATH)
    query = """
    SELECT * FROM votes 
    WHERE kaisai_date >= ? AND kaisai_date <= ? AND status = 'success'
    ORDER BY kaisai_date ASC, race_id ASC;
    """
    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()
    return df


def calculate_performance_for_votes(votes_df: pd.DataFrame, results_cache: dict = None) -> Tuple[dict, dict]:
    """
    votes DataFrame に対する購入金額、回収金額、的中数を計算する。
    """
    if votes_df.empty:
        return {
            'total_amount': 0,
            'payout_amount': 0,
            'recovery_rate': 0.0,
            'total_bets': 0,
            'hit_bets': 0
        }, results_cache or {}

    if results_cache is None:
        results_cache = {}

    total_amount = 0
    payout_amount = 0
    total_bets = len(votes_df)
    hit_bets = 0

    for _, vote in votes_df.iterrows():
        race_id = str(vote['race_id'])
        umaban = int(vote['umaban'])
        amount = int(vote.get('amount', 100))
        vote_type = str(vote.get('vote_type', 'win')).lower()
        total_amount += amount

        # キャッシュになければ当日の速報結果を取得
        if race_id not in results_cache:
            res_df, pay_dict = get_live_race_result(race_id)
            results_cache[race_id] = (res_df, pay_dict)

        res_df, pay_dict = results_cache[race_id]

        if res_df.empty or not pay_dict:
            continue

        # 1. 単勝判定
        if vote_type in ('win', 'tansho'):
            win_num_str = str(pay_dict.get('tansho_numbers', '')).strip()
            if win_num_str and win_num_str.isdigit() and int(win_num_str) == umaban:
                hit_bets += 1
                pay_val = pay_dict.get('tansho_payout', 0)
                payout_amount += int(amount * (pay_val / 100.0))

        # 2. 複勝判定
        elif vote_type in ('place', 'fukusho'):
            fukusho_json = pay_dict.get('fukusho_payouts', '{}')
            try:
                fukusho_dict = json.loads(fukusho_json) if isinstance(fukusho_json, str) else fukusho_json
                if str(umaban) in fukusho_dict:
                    hit_bets += 1
                    pay_val = fukusho_dict[str(umaban)]
                    payout_amount += int(amount * (pay_val / 100.0))
            except Exception:
                pass

    recovery_rate = (payout_amount / total_amount * 100.0) if total_amount > 0 else 0.0

    return {
        'total_amount': total_amount,
        'payout_amount': payout_amount,
        'recovery_rate': recovery_rate,
        'total_bets': total_bets,
        'hit_bets': hit_bets
    }, results_cache


def generate_weekly_report_data(target_date_str: str = None) -> dict:
    """
    指定日（省略時は今日）の土日・年間累計の収支報告データを生成する。
    """
    if not target_date_str:
        target_date_str = datetime.now().strftime('%Y-%m-%d')

    dt = datetime.strptime(target_date_str, '%Y-%m-%d')
    weekday = dt.weekday() # 0:月 ... 5:土 6:日

    is_saturday = (weekday == 5)
    is_sunday = (weekday == 6)

    # 1. 当日成績
    daily_votes = get_votes_for_date_range(target_date_str, target_date_str)
    daily_perf, results_cache = calculate_performance_for_votes(daily_votes)

    # 2. 今週 (土日) 成績の範囲計算
    if is_sunday:
        sat_date_str = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        weekly_votes = get_votes_for_date_range(sat_date_str, target_date_str)
        weekly_perf, results_cache = calculate_performance_for_votes(weekly_votes, results_cache)
    else:
        weekly_perf = daily_perf

    # 3. 年間累計 (本年 1月1日 〜 今日の日付)
    year_start_str = f"{dt.year}-01-01"
    yearly_votes = get_votes_for_date_range(year_start_str, target_date_str)
    yearly_perf, _ = calculate_performance_for_votes(yearly_votes, results_cache)

    return {
        'target_date': target_date_str,
        'is_saturday': is_saturday,
        'is_sunday': is_sunday,
        'daily': daily_perf,
        'weekly': weekly_perf,
        'yearly': yearly_perf
    }


if __name__ == "__main__":
    test_date = datetime.now().strftime('%Y-%m-%d')
    print(f"Calculating weekly report data for target_date: {test_date}...")
    report_data = generate_weekly_report_data(test_date)
    print("\n--- Report Data Summary ---")
    print(json.dumps(report_data, ensure_ascii=False, indent=2))
