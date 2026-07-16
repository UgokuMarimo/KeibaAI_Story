import sqlite3
import pandas as pd
import numpy as np

def main():
    conn = sqlite3.connect('predictions.db')
    query = """
    SELECT race_id, umaban, pred_win, tansho_odds, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND tansho_odds IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 正規化
    sum_pred = df.groupby('race_id')['pred_win'].transform('sum')
    df['win_prob'] = df['pred_win'] / sum_pred
    df['expected_value'] = df['win_prob'] * df['tansho_odds']
    df['is_winner'] = (df['result_rank'] == 1).astype(int)
    df['payout'] = df['is_winner'] * df['tansho_odds'] * 100
    
    # 期待値1.2の時の、最低勝率ごとの成績比較
    print("=== 最低期待値 1.20 固定時の、最低勝率(P_min)ごとの成績推移 ===")
    for p in [0.05, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.15, 0.20]:
        sel = df[(df['win_prob'] >= p) & (df['expected_value'] >= 1.20)]
        bets = len(sel)
        if bets == 0: continue
        hits = sel['is_winner'].sum()
        hr = hits / bets
        rr = sel['payout'].sum() / (bets * 100)
        print(f"  - 最低勝率 {p:2.0%}: 回収率 {rr:7.2%} | 的中率 {hr:6.2%} (購入: {bets:3d}回 / 的中: {hits:2d})")

    # 最低勝率 9% 固定時の、期待値閾値ごとの成績比較
    print("\n=== 最低勝率 9.0% 固定時の、期待値閾値(EV_min)ごとの成績推移 ===")
    for ev in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]:
        sel = df[(df['win_prob'] >= 0.09) & (df['expected_value'] >= ev)]
        bets = len(sel)
        if bets == 0: continue
        hits = sel['is_winner'].sum()
        hr = hits / bets
        rr = sel['payout'].sum() / (bets * 100)
        print(f"  - 最低期待値 {ev:.2f}: 回収率 {rr:7.2%} | 的中率 {hr:6.2%} (購入: {bets:3d}回 / 的中: {hits:2d})")

    # 最低勝率 10% 固定時の、期待値閾値ごとの成績比較
    print("\n=== 最低勝率 10.0% 固定時の、期待値閾値(EV_min)ごとの成績推移 ===")
    for ev in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]:
        sel = df[(df['win_prob'] >= 0.10) & (df['expected_value'] >= ev)]
        bets = len(sel)
        if bets == 0: continue
        hits = sel['is_winner'].sum()
        hr = hits / bets
        rr = sel['payout'].sum() / (bets * 100)
        print(f"  - 最低期待値 {ev:.2f}: 回収率 {rr:7.2%} | 的中率 {hr:6.2%} (購入: {bets:3d}回 / 的中: {hits:2d})")

if __name__ == '__main__':
    main()
