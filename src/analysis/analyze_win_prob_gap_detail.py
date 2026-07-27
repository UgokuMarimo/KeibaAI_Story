import sqlite3
import pandas as pd
import numpy as np

def analyze_win_prob_gap_detail(db_path='data/db/predictions.db'):
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, tansho_ninki, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND pred_win IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 正規化
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum
    df['pred_rank'] = df.groupby('race_id')['norm_win_prob'].rank(ascending=False, method='min')
    
    races_1st = df[df['pred_rank'] == 1].drop_duplicates(subset=['race_id'], keep='first')
    races_2nd = df[df['pred_rank'] == 2].drop_duplicates(subset=['race_id'], keep='first')
    
    merged = pd.merge(
        races_1st, 
        races_2nd[['race_id', 'norm_win_prob', 'result_rank', 'tansho_odds', 'horse_name', 'tansho_ninki']], 
        on='race_id', 
        suffixes=('_1st', '_2nd')
    )
    
    merged['prob_gap'] = merged['norm_win_prob_1st'] - merged['norm_win_prob_2nd']
    merged['prob_ratio'] = merged['norm_win_prob_1st'] / merged['norm_win_prob_2nd']
    merged['is_win_1st'] = (merged['result_rank_1st'] == 1).astype(int)
    merged['is_top3_1st'] = (merged['result_rank_1st'] <= 3).astype(int)
    merged['payout_1st'] = merged['is_win_1st'] * merged['tansho_odds_1st'] * 100
    merged['is_win_2nd'] = (merged['result_rank_2nd'] == 1).astype(int)
    
    # AI 1位が「1番人気」か「2番人気以下（穴馬）」かで分類
    merged['is_1st_favorite'] = (merged['tansho_ninki_1st'] == 1)
    
    gap_bins = [-0.001, 0.03, 0.06, 0.10, 1.00]
    gap_labels = ['< 3% (接戦)', '3% ~ 6%', '6% ~ 10%', '10%+ (抜けて強い)']
    merged['gap_band'] = pd.cut(merged['prob_gap'], bins=gap_bins, labels=gap_labels)

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

    print("=== AI 1位が「1番人気（本命）」の場合のギャップ別成績 ===")
    res_fav = []
    for label in gap_labels:
        sub = merged[(merged['is_1st_favorite'] == True) & (merged['gap_band'] == label)]
        m = calc_metrics(sub)
        if m:
            m['gap_band'] = label
            res_fav.append(m)
    print(pd.DataFrame(res_fav).to_string(index=False))

    print("\n=== AI 1位が「2番人気以下（中穴・穴馬）」の場合のギャップ別成績 ===")
    res_non_fav = []
    for label in gap_labels:
        sub = merged[(merged['is_1st_favorite'] == False) & (merged['gap_band'] == label)]
        m = calc_metrics(sub)
        if m:
            m['gap_band'] = label
            res_non_fav.append(m)
    print(pd.DataFrame(res_non_fav).to_string(index=False))

if __name__ == '__main__':
    analyze_win_prob_gap_detail()
