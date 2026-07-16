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

# 固定セーフティ条件：勝率 >= 10% かつ オッズ < 30倍
base_df = df[(df['norm_win_prob'] >= 0.1) & (df['tansho_odds'] < 30.0)]

print("=== EV THRESHOLD PROFIT SIMULATION (1点100円購入, 13日間) ===")
print("-" * 85)
print("{:<12} | {:<12} | {:<12} | {:<12} | {:<12} | {:<12}".format(
    "EV下限", "購入頭数", "総購入額", "総払い戻し額", "回収率", "純利益 (回収額 - 購入額)"
))
print("-" * 85)

for ev_thresh in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]:
    sub_df = base_df[base_df['expected_value'] >= ev_thresh]
    total = len(sub_df)
    if total == 0:
        continue
    investment = total * 100
    payout_sum = sub_df['payout'].sum()
    net_profit = payout_sum - investment
    recovery_rate = payout_sum / investment * 100
    
    print("{:<12.1f} | {:<12} | {:<12,}円 | {:<12,}円 | {:<12.1f}% | {:<+12,}円".format(
        ev_thresh, total, investment, int(payout_sum), recovery_rate, int(net_profit)
    ))
