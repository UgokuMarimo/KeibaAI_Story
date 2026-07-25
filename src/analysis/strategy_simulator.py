import os
import sys
import sqlite3
import json
import pandas as pd
import numpy as np

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config
from analysis.weekly_report_calculator import calculate_performance_for_votes, get_votes_for_date_range

def run_strategy_analysis():
    conn = sqlite3.connect(config.DB_PATH)
    votes_df = pd.read_sql_query("""
    SELECT * FROM votes 
    WHERE status = 'success' AND kaisai_date >= '2026-01-01'
    ORDER BY kaisai_date ASC, race_id ASC;
    """, conn)
    conn.close()

    perf, cache = calculate_performance_for_votes(votes_df)

    results_detail = []
    for _, vote in votes_df.iterrows():
        race_id = str(vote['race_id'])
        umaban = int(vote['umaban'])
        amount = int(vote.get('amount', 100))
        vote_odds = float(vote.get('vote_odds', 0.0) or 0.0)
        pred_win_prob = float(vote.get('pred_win_prob', 0.0) or 0.0)
        
        res_df, pay_dict = cache.get(race_id, (pd.DataFrame(), {}))
        
        is_hit = False
        pay_val = 0
        if pay_dict:
            win_num_str = str(pay_dict.get('tansho_numbers', '')).strip()
            if win_num_str and win_num_str.isdigit() and int(win_num_str) == umaban:
                is_hit = True
                pay_val = int(amount * (pay_dict.get('tansho_payout', 0) / 100.0))
                
        ev = pred_win_prob * vote_odds if pred_win_prob > 0 and vote_odds > 0 else 0.0
        
        results_detail.append({
            'race_id': race_id,
            'umaban': umaban,
            'horse_name': vote['horse_name'],
            'vote_odds': vote_odds,
            'pred_win_prob': pred_win_prob,
            'ev': ev,
            'amount': amount,
            'is_hit': is_hit,
            'pay_val': pay_val
        })

    detail_df = pd.DataFrame(results_detail)

    print("==================================================")
    print("📊 1. 基本的中率 & 収支サマリー")
    print("==================================================")
    print(f"■ 総購入点数   : {perf['total_bets']} 点")
    print(f"■ 総的中点数   : {perf['hit_bets']} 点")
    print(f"■ 的中率 (Hit) : {perf['hit_bets'] / perf['total_bets']:.2%} ({perf['hit_bets']}/{perf['total_bets']})")
    print(f"■ 総購入金額   : {perf['total_amount']:,} 円")
    print(f"■ 総回収金額   : {perf['payout_amount']:,} 円")
    print(f"■ 回収率 (ROI) : {perf['recovery_rate']:.2f}%")

    print("\n==================================================")
    print("🎯 2. オッズ帯ごとの的中率・回収率分析")
    print("==================================================")
    bins_odds = [0, 3.0, 5.0, 10.0, 20.0, 100.0]
    labels_odds = ['1.0〜2.9倍', '3.0〜4.9倍', '5.0〜9.9倍', '10.0〜19.9倍', '20.0倍以上']
    detail_df['odds_band'] = pd.cut(detail_df['vote_odds'], bins=bins_odds, labels=labels_odds)

    odds_summary = detail_df.groupby('odds_band', observed=False).agg(
        購入点数=('is_hit', 'count'),
        的中点数=('is_hit', 'sum'),
        的中率=('is_hit', 'mean'),
        購入額=('amount', 'sum'),
        回収額=('pay_val', 'sum')
    )
    odds_summary['回収率'] = (odds_summary['回収額'] / odds_summary['購入額'] * 100).fillna(0)
    odds_summary['的中率'] = (odds_summary['的中率'] * 100).fillna(0)
    print(odds_summary.to_string())

    print("\n==================================================")
    print("💡 3. 期待値 (EV) 帯ごとの的中率・回収率分析")
    print("==================================================")
    bins_ev = [0, 1.2, 1.5, 2.0, 3.0, 100.0]
    labels_ev = ['EV 1.0〜1.19', 'EV 1.2〜1.49', 'EV 1.5〜1.99', 'EV 2.0〜2.99', 'EV 3.0以上']
    detail_df['ev_band'] = pd.cut(detail_df['ev'], bins=bins_ev, labels=labels_ev)

    ev_summary = detail_df.groupby('ev_band', observed=False).agg(
        購入点数=('is_hit', 'count'),
        的中点数=('is_hit', 'sum'),
        的中率=('is_hit', 'mean'),
        購入額=('amount', 'sum'),
        回収額=('pay_val', 'sum')
    )
    ev_summary['回収率'] = (ev_summary['回収額'] / ev_summary['購入額'] * 100).fillna(0)
    ev_summary['的中率'] = (ev_summary['的中率'] * 100).fillna(0)
    print(ev_summary.to_string())

if __name__ == "__main__":
    run_strategy_analysis()
