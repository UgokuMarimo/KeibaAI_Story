# C:\KeibaAI\src\analysis\generate_april_report.py
import sqlite3
import pandas as pd
import numpy as np

db_path = "C:/KeibaAI/predictions.db"

def main():
    # 1. データの読み込み
    conn = sqlite3.connect(db_path)
    query = """
    SELECT 
        p.race_id,
        p.umaban,
        p.horse_name,
        p.kaisai_date,
        p.pred_win,
        p.tansho_odds,
        p.result_rank,
        pay.tansho_payout
    FROM predictions p
    JOIN payouts pay ON p.race_id = pay.race_id
    WHERE p.kaisai_date >= '2026-04-01' AND p.kaisai_date <= '2026-04-30'
    ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("2026年4月のデータが見つかりませんでした。")
        return

    # 2. 前処理
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    
    df['expected_value'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    # 単勝払戻金の取得と補完
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 開催日数の取得
    unique_dates = df['kaisai_date'].nunique()

    # 3. 条件：勝率 >= 10%, オッズ < 30倍, 期待値 >= 1.3
    selected = df[
        (df['norm_win_prob'] >= 0.1) & 
        (df['tansho_odds'] < 30.0) & 
        (df['expected_value'] >= 1.3)
    ]

    total = len(selected)
    
    print(f"=== 2026年4月度 成績シミュレーション (EV >= 1.3) ===")
    print(f"集計期間: 2026-04-01 〜 2026-04-30 (開催日数: {unique_dates}日)")
    print("-" * 50)
    
    if total == 0:
        print("該当する馬はいませんでした。")
        return

    hits = selected['is_win'].sum()
    hit_rate = (hits / total) * 100
    investment = total * 100
    payout_sum = selected['payout'].sum()
    recovery_rate = (payout_sum / investment) * 100
    net_profit = payout_sum - investment
    avg_per_day = total / unique_dates

    print(f"購入頭数    : {total} 頭 (1日平均: {avg_per_day:.2f}頭)")
    print(f"的中数      : {hits} 頭")
    print(f"的中率      : {hit_rate:.1f} %")
    print(f"総投資額    : {investment:,} 円")
    print(f"総払戻額    : {int(payout_sum):,} 円")
    print(f"回収率      : {recovery_rate:.1f} %")
    print(f"純損益      : {int(net_profit):+,} 円")

if __name__ == '__main__':
    main()
