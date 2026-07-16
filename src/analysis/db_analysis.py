import sqlite3
import pandas as pd
import numpy as np

conn = sqlite3.connect('predictions.db')
df = pd.read_sql_query('''
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND tansho_odds IS NOT NULL AND tansho_odds > 0
''', conn)

# 正規化勝率と期待値の計算
df['sum_pred_win'] = df.groupby('race_id')['pred_win'].transform('sum')
df['norm_win_prob'] = df['pred_win'] / df['sum_pred_win']
df['expected_value'] = df['norm_win_prob'] * df['tansho_odds']
df['is_win'] = (df['result_rank'] == 1).astype(int)
df['payout'] = df['is_win'] * df['tansho_odds'] * 100

def get_stats(sub_df):
    total = len(sub_df)
    if total == 0:
        return pd.Series({'total': 0, 'hits': 0, 'hit_rate': 0.0, 'recovery_rate': 0.0})
    hits = sub_df['is_win'].sum()
    hit_rate = hits / total * 100
    investment = total * 100
    recovery = sub_df['payout'].sum()
    recovery_rate = recovery / investment * 100
    return pd.Series({
        'total': int(total),
        'hits': int(hits),
        'hit_rate': hit_rate,
        'recovery_rate': recovery_rate
    })

# 1. 基本統計（勝率10%以上、期待値1.2以上）
print('=== 1. BASIC STATS (WinProb >= 10% & EV >= 1.2) ===')
cond_a = (df['norm_win_prob'] >= 0.1) & (df['expected_value'] >= 1.2)
stats_a = get_stats(df[cond_a])
stats_b = get_stats(df[cond_a & (df['tansho_odds'] < 30.0)])
print(f"Pattern A (No Cap): Total={int(stats_a['total'])}, Hits={int(stats_a['hits'])}, HitRate={stats_a['hit_rate']:.1f}%, Recovery={stats_a['recovery_rate']:.1f}%")
print(f"Pattern B (Odds < 30x): Total={int(stats_b['total'])}, Hits={int(stats_b['hits'])}, HitRate={stats_b['hit_rate']:.1f}%, Recovery={stats_b['recovery_rate']:.1f}%")

# 2. オッズ帯別の分析
print('\n=== 2. ODDS BAND ANALYSIS (All Horses) ===')
odds_bins = [0, 2, 5, 10, 20, 30, 50, 100, 9999]
odds_labels = ['1.0-1.9', '2.0-4.9', '5.0-9.9', '10.0-19.9', '20.0-29.9', '30.0-49.9', '50.0-99.9', '100.0+']
df['odds_band'] = pd.cut(df['tansho_odds'], bins=odds_bins, labels=odds_labels, right=False)
odds_grouped = df.groupby('odds_band', observed=False).apply(get_stats)
print(odds_grouped[['total', 'hits', 'hit_rate', 'recovery_rate']].to_string())

# 3. 予測勝率帯別の分析
print('\n=== 3. WIN PROBABILITY BAND ANALYSIS (All Horses) ===')
prob_bins = [0, 0.05, 0.10, 0.15, 0.20, 0.30, 1.0]
prob_labels = ['<5%', '5%-9.9%', '10%-14.9%', '15%-19.9%', '20%-29.9%', '30%+']
df['prob_band'] = pd.cut(df['norm_win_prob'], bins=prob_bins, labels=prob_labels, right=False)
prob_grouped = df.groupby('prob_band', observed=False).apply(get_stats)
print(prob_grouped[['total', 'hits', 'hit_rate', 'recovery_rate']].to_string())

# 4. 期待値帯別の分析
print('\n=== 4. EXPECTED VALUE BAND ANALYSIS (All Horses) ===')
ev_bins = [0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 9999]
ev_labels = ['<0.5', '0.5-0.79', '0.8-0.99', '1.0-1.19', '1.2-1.49', '1.5-1.99', '2.0+']
df['ev_band'] = pd.cut(df['expected_value'], bins=ev_bins, labels=ev_labels, right=False)
ev_grouped = df.groupby('ev_band', observed=False).apply(get_stats)
print(ev_grouped[['total', 'hits', 'hit_rate', 'recovery_rate']].to_string())
