import sqlite3
import pandas as pd

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

# 開催日数の取得
unique_dates = df['kaisai_date'].nunique()

# 固定セーフティ条件：勝率 >= 10% かつ オッズ < 30倍
base_df = df[(df['norm_win_prob'] >= 0.1) & (df['tansho_odds'] < 30.0)]

print(f"=== EV THRESHOLD SIMULATION (WinProb >= 10% & Odds < 30x, {unique_dates} days) ===")
print("{:<10} {:<10} {:<10} {:<10} {:<10} {:<12}".format("EV Threshold", "Total", "Hits", "Hit Rate", "Recovery", "Avg Per Day"))
print("-" * 68)

for ev_thresh in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]:
    sub_df = base_df[base_df['expected_value'] >= ev_thresh]
    total = len(sub_df)
    if total == 0:
        print("{:<10.1f} {:<10} {:<10} {:<10} {:<10} {:<12}".format(ev_thresh, 0, 0, "0.0%", "0.0%", "0.0 pt"))
        continue
    hits = sub_df['is_win'].sum()
    hit_rate = hits / total * 100
    investment = total * 100
    recovery = sub_df['payout'].sum()
    recovery_rate = recovery / investment * 100
    avg_per_day = total / unique_dates
    avg_yen = avg_per_day * 100
    print("{:<10.1f} {:<10} {:<10} {:<10.1f}% {:<10.1f}% {:<12.2f} pt ({:.0f} yen)".format(
        ev_thresh, total, hits, hit_rate, recovery_rate, avg_per_day, avg_yen
    ))
