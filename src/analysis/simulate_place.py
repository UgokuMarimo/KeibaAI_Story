# C:\KeibaAI\scratch\simulate_place.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# パス設定
db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/place_recovery_simulation.png"

# データベース接続
conn = sqlite3.connect(db_path)

# 1. 予測データと払戻しデータの結合取得（複勝予測があるものに限定）
query = """
SELECT 
    p.race_id,
    p.umaban,
    p.horse_name,
    p.kaisai_date,
    p.pred_place,
    p.tansho_odds,
    p.result_rank,
    pay.fukusho_payouts
FROM predictions p
JOIN payouts pay ON p.race_id = pay.race_id
WHERE p.pred_place IS NOT NULL
ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
"""

df = pd.read_sql_query(query, conn)
conn.close()

if df.empty:
    print("No data found for simulation.")
    exit(1)

# 2. 複勝オッズ下限の推計と払戻金のデコード
# 推計複勝オッズ下限 = 0.15 * 単勝オッズ + 1.0
df['est_place_odds'] = 0.15 * df['tansho_odds'] + 1.0
df['place_ev'] = df['pred_place'] * df['est_place_odds']

# 実際の払戻金の取得
def get_actual_payout(row):
    try:
        payouts_dict = json.loads(row['fukusho_payouts'])
        # JSONのキーは文字列なので umaban を文字列にして引く
        umaban_str = str(row['umaban'])
        if umaban_str in payouts_dict:
            return float(payouts_dict[umaban_str])
        else:
            return 0.0
    except Exception:
        return 0.0

df['payout'] = df.apply(get_actual_payout, axis=1)

# シミュレーション対象しきい値
thresholds = [1.0, 1.1, 1.2, 1.3]

# プロット用の準備
plt.figure(figsize=(12, 7))
plt.rcParams['font.family'] = 'MS Gothic'
plt.rcParams['axes.unicode_minus'] = False

# 日付ごとに集計して時系列の推移にする
# レースを時系列順にインデックス化
df = df.sort_values(['kaisai_date', 'race_id']).reset_index(drop=True)

print("--- 複勝回収率シミュレーション結果 ---")

# 全件ベタ買い（比較用）
df['net_profit_all'] = df['payout'] - 100
cum_all = df['net_profit_all'].cumsum()
plt.plot(cum_all, label='ベタ買い (全馬)', color='gray', alpha=0.5, linestyle='--')
all_recovery = (df['payout'].sum() / (len(df) * 100)) * 100
all_hit_rate = (df['payout'] > 0).mean() * 100
print(f"ベタ買い(全馬): 購入点数={len(df):,}点, 的中率={all_hit_rate:.1f}%, 回収率={all_recovery:.2f}%")

for th in thresholds:
    # しきい値以上の馬を抽出
    selected_df = df[df['place_ev'] >= th].copy()
    
    if selected_df.empty:
        print(f"しきい値 EV >= {th}: 対象馬なし")
        continue
        
    selected_df['net_profit'] = selected_df['payout'] - 100
    # 累積利益
    cum_profit = selected_df['net_profit'].cumsum().reset_index(drop=True)
    
    # 統計情報の出力
    total_bets = len(selected_df)
    hit_count = (selected_df['payout'] > 0).sum()
    hit_rate = (hit_count / total_bets) * 100 if total_bets > 0 else 0
    total_payout = selected_df['payout'].sum()
    total_cost = total_bets * 100
    recovery_rate = (total_payout / total_cost) * 100 if total_cost > 0 else 0
    final_profit = selected_df['net_profit'].sum()
    
    print(f"しきい値 EV >= {th:.1f}: 購入点数={total_bets:,}点, 的中率={hit_rate:.1f}%, 回収率={recovery_rate:.2f}%, 最終純利益={final_profit:+,.0f}円")
    
    plt.plot(cum_profit, label=f"EV >= {th:.1f} (回収率: {recovery_rate:.1f}%)", linewidth=2)

plt.title("複勝回収率シミュレーション (期待値しきい値別 資金推移)", fontsize=14)
plt.xlabel("購入レース数 (累計)", fontsize=12)
plt.ylabel("累積純損益 (円, 1点100円購入時)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.5)
plt.axhline(0, color='red', linestyle='-', alpha=0.3)
plt.legend(loc='upper left', fontsize=10)

os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
plt.close()

print("\nSimulation plot saved successfully.")
