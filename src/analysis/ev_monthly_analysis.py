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

# 期待値1.3設定のフィルター（勝率 >= 10%, オッズ < 30倍, EV >= 1.3）
target_df = df[
    (df['norm_win_prob'] >= 0.1) & 
    (df['tansho_odds'] < 30.0) & 
    (df['expected_value'] >= 1.3)
].copy()

# 月カラムの作成
target_df['month'] = pd.to_datetime(target_df['kaisai_date']).dt.month

print("=== MONTHLY SIMULATION (EV >= 1.3, WinProb >= 10%, Odds < 30x) ===")
print("-" * 80)
print("{:<8} | {:<10} | {:<10} | {:<10} | {:<12} | {:<12} | {:<10}".format(
    "対象月", "開催日数", "購入頭数", "的中数", "的中率", "回収率", "純利益"
))
print("-" * 80)

for m in [4, 5]:
    m_df = target_df[target_df['month'] == m]
    total = len(m_df)
    if total == 0:
        print(f"2026年{m:02d}月: データなし")
        continue
    
    unique_dates = m_df['kaisai_date'].nunique()
    hits = m_df['is_win'].sum()
    hit_rate = hits / total * 100
    investment = total * 100
    payout_sum = m_df['payout'].sum()
    net_profit = payout_sum - investment
    recovery_rate = payout_sum / investment * 100
    
    print("2026年{:02d}月 | {:<10} | {:<10} | {:<10} | {:<12.1f}% | {:<12.1f}% | {:<+10,}円".format(
        m, unique_dates, total, hits, hit_rate, recovery_rate, int(net_profit)
    ))
