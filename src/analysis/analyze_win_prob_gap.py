import sqlite3
import pandas as pd
import numpy as np

def analyze_win_prob_gap(db_path='data/db/predictions.db'):
    conn = sqlite3.connect(db_path)
    
    # データを取得
    query = """
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, tansho_ninki, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND pred_win IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # レースごとの正規化予測勝率を計算
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum
    
    # 各レース内での勝率ランクを算出
    df['pred_rank'] = df.groupby('race_id')['norm_win_prob'].rank(ascending=False, method='min')
    
    # レースごとに1位と2位の勝率を抽出
    races_1st = df[df['pred_rank'] == 1].drop_duplicates(subset=['race_id'], keep='first')
    races_2nd = df[df['pred_rank'] == 2].drop_duplicates(subset=['race_id'], keep='first')
    
    # 1位と2位をレースIDで結合
    merged = pd.merge(
        races_1st, 
        races_2nd[['race_id', 'norm_win_prob', 'result_rank', 'tansho_odds', 'horse_name']], 
        on='race_id', 
        suffixes=('_1st', '_2nd')
    )
    
    # ギャップ計算
    merged['prob_gap'] = merged['norm_win_prob_1st'] - merged['norm_win_prob_2nd']
    merged['prob_ratio'] = merged['norm_win_prob_1st'] / merged['norm_win_prob_2nd']
    
    merged['is_win_1st'] = (merged['result_rank_1st'] == 1).astype(int)
    merged['is_top3_1st'] = (merged['result_rank_1st'] <= 3).astype(int)
    merged['payout_1st'] = merged['is_win_1st'] * merged['tansho_odds_1st'] * 100
    merged['is_win_2nd'] = (merged['result_rank_2nd'] == 1).astype(int)
    
    # ギャップ（絶対値）の分割
    gap_bins = [-0.001, 0.03, 0.06, 0.10, 0.15, 0.20, 1.00]
    gap_labels = ['< 3% (接戦)', '3% ~ 6%', '6% ~ 10%', '10% ~ 15%', '15% ~ 20%', '20%+ (抜けて強い)']
    merged['gap_band'] = pd.cut(merged['prob_gap'], bins=gap_bins, labels=gap_labels)

    # ギャップ（比率）の分割
    ratio_bins = [0, 1.2, 1.5, 2.0, 3.0, 100.0]
    ratio_labels = ['1.0 ~ 1.2倍 (接戦)', '1.2 ~ 1.5倍', '1.5 ~ 2.0倍', '2.0 ~ 3.0倍 (かなり優勢)', '3.0倍+ (圧倒的1強)']
    merged['ratio_band'] = pd.cut(merged['prob_ratio'], bins=ratio_bins, labels=ratio_labels)

    def calc_metrics(df_sub):
        n = len(df_sub)
        if n == 0:
            return {}
        wins_1 = df_sub['is_win_1st'].sum()
        top3_1 = df_sub['is_top3_1st'].sum()
        wins_2 = df_sub['is_win_2nd'].sum()
        avg_p1 = df_sub['norm_win_prob_1st'].mean()
        avg_p2 = df_sub['norm_win_prob_2nd'].mean()
        avg_odds1 = df_sub['tansho_odds_1st'].mean()
        rec_1 = df_sub['payout_1st'].sum() / (n * 100) * 100
        
        return {
            'races': n,
            'avg_prob_1st': avg_p1 * 100,
            'avg_prob_2nd': avg_p2 * 100,
            'actual_win_rate_1st': (wins_1 / n) * 100,
            'actual_top3_rate_1st': (top3_1 / n) * 100,
            'actual_win_rate_2nd': (wins_2 / n) * 100,
            'avg_odds_1st': avg_odds1,
            'recovery_rate_1st': rec_1
        }

    print("=== 1. 1位と2位の勝率差 (Prob_1st - Prob_2nd) 別の集計 ===")
    res_gap = []
    for label in gap_labels:
        sub = merged[merged['gap_band'] == label]
        m = calc_metrics(sub)
        m['gap_band'] = label
        res_gap.append(m)
    df_gap_res = pd.DataFrame(res_gap)
    print(df_gap_res.to_string(index=False))

    print("\n=== 2. 1位と2位の勝率比 (Prob_1st / Prob_2nd) 別の集計 ===")
    res_ratio = []
    for label in ratio_labels:
        sub = merged[merged['ratio_band'] == label]
        m = calc_metrics(sub)
        m['ratio_band'] = label
        res_ratio.append(m)
    df_ratio_res = pd.DataFrame(res_ratio)
    print(df_ratio_res.to_string(index=False))

    print("\n=== 3. 予測1位馬の勝率帯 (<20%, 20-30%, 30%+) × 2位との勝率ギャップ ===")
    merged['p1_band'] = pd.cut(merged['norm_win_prob_1st'], bins=[0, 0.20, 0.30, 1.00], labels=['1位勝率<20%', '1位勝率20-30%', '1位勝率30%+'])
    res_cross = []
    for p_label in ['1位勝率<20%', '1位勝率20-30%', '1位勝率30%+']:
        for g_label in ['< 3% (接戦)', '3% ~ 6%', '6% ~ 10%', '10%+ (抜けて強い)']:
            if g_label == '10%+ (抜けて強い)':
                sub = merged[(merged['p1_band'] == p_label) & (merged['prob_gap'] >= 0.10)]
            else:
                sub = merged[(merged['p1_band'] == p_label) & (merged['gap_band'] == g_label)]
            m = calc_metrics(sub)
            if m and m['races'] > 0:
                m['p1_band'] = p_label
                m['gap_band'] = g_label
                res_cross.append(m)
    df_cross_res = pd.DataFrame(res_cross)
    print(df_cross_res.to_string(index=False))

if __name__ == '__main__':
    analyze_win_prob_gap()
