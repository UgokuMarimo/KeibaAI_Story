# C:\KeibaAI\scratch\simulate_place_harville.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# パス設定
db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/place_recovery_simulation_harville.png"

def calculate_harville_place_probs(win_probs_dict):
    """
    ハルビル公式による複勝（3着以内）確率の算出
    """
    umabans = list(win_probs_dict.keys())
    probs = np.array(list(win_probs_dict.values()), dtype=float)
    
    # 勝率の合計が1.0になるようにノーマライズ
    probs_sum = np.sum(probs)
    if probs_sum > 0:
        probs = probs / probs_sum
    else:
        return {u: 0.0 for u in umabans}
        
    n = len(probs)
    place_probs = np.zeros(n)
    
    for i in range(n):
        p_i = probs[i]
        
        # 1着になる確率
        p_1st = p_i
        
        # 2着になる確率
        p_2nd = 0.0
        for j in range(n):
            if j == i: continue
            p_j = probs[j]
            # 分母ゼロ防止
            denom = 1.0 - p_j
            if denom > 0:
                p_2nd += p_j * (p_i / denom)
            
        # 3着になる確率
        p_3rd = 0.0
        for j in range(n):
            if j == i: continue
            p_j = probs[j]
            for k in range(n):
                if k == i or k == j: continue
                p_k = probs[k]
                # 分母ゼロ防止
                denom = 1.0 - p_j - p_k
                if denom > 0:
                    p_3rd += p_j * (p_k / (1.0 - p_j)) * (p_i / denom)
                
        place_probs[i] = p_1st + p_2nd + p_3rd
        
    return dict(zip(umabans, place_probs))

# 1. データの全件読み込み
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
    pay.fukusho_payouts
FROM predictions p
JOIN payouts pay ON p.race_id = pay.race_id
ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
"""
df = pd.read_sql_query(query, conn)
conn.close()

if df.empty:
    print("No data found for simulation.")
    exit(1)

print(f"Loaded {len(df)} predictions from DB.")

# 2. レースごとにハルビル公式を適用して複勝率を計算
print("Calculating mathematical place probabilities using Harville's Formula...")
place_prob_list = []

# race_idごとにグループ化して処理
grouped = df.groupby('race_id')
for race_id, group in grouped:
    win_probs_dict = group.set_index('umaban')['pred_win'].to_dict()
    # ハルビル複勝率を計算
    place_probs_dict = calculate_harville_place_probs(win_probs_dict)
    
    for idx, row in group.iterrows():
        umaban = row['umaban']
        place_prob = place_probs_dict.get(umaban, 0.0)
        place_prob_list.append(place_prob)

df['harville_place_prob'] = place_prob_list

# 3. 期待値(EV)の計算
# 推計複勝オッズ下限 = 0.08 * 単勝オッズ + 1.0 (最大5.0倍で頭打ちにする。より現実的な下限値)
df['est_place_odds'] = np.minimum(5.0, 0.08 * df['tansho_odds'] + 1.0)
df['place_ev'] = df['harville_place_prob'] * df['est_place_odds']

# 実際の払戻金の取得
def get_actual_payout(row):
    try:
        payouts_dict = json.loads(row['fukusho_payouts'])
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

# 日付とレースIDで時系列ソート
df = df.sort_values(['kaisai_date', 'race_id']).reset_index(drop=True)

# 有効なオッズフィルター（単勝15倍以下の中人気馬までを母集団とする）
# 穴馬の予測ノイズを完全に遮断するための実用的設定
df_filtered = df[df['tansho_odds'] <= 15.0].copy().reset_index(drop=True)

print("\n--- 複勝回収率シミュレーション結果 (単勝15倍以下・複勝オッズ推計保守化) ---")

# 全件ベタ買い（比較用・フィルター後）
df_filtered['net_profit_all'] = df_filtered['payout'] - 100
cum_all = df_filtered['net_profit_all'].cumsum()
plt.plot(cum_all, label='ベタ買い (単勝15倍以下)', color='gray', alpha=0.5, linestyle='--')
all_recovery = (df_filtered['payout'].sum() / (len(df_filtered) * 100)) * 100
all_hit_rate = (df_filtered['payout'] > 0).mean() * 100
print(f"ベタ買い(全馬): 購入点数={len(df_filtered):,}点, 的中率={all_hit_rate:.1f}%, 回収率={all_recovery:.2f}%")

for th in thresholds:
    # しきい値以上の馬を抽出
    selected_df = df_filtered[df_filtered['place_ev'] >= th].copy()
    
    if selected_df.empty:
        print(f"しきい値 EV >= {th}: 対象馬なし")
        continue
        
    selected_df['net_profit'] = selected_df['payout'] - 100
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

plt.title("複勝回収率シミュレーション (勝率モデル➡ハルビル複勝率変換版)", fontsize=14)
plt.xlabel("購入レース数 (累計)", fontsize=12)
plt.ylabel("累積純損益 (円, 1点100円購入時)", fontsize=12)
plt.grid(True, linestyle='--', alpha=0.5)
plt.axhline(0, color='red', linestyle='-', alpha=0.3)
plt.legend(loc='upper left', fontsize=10)

os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
plt.close()

print("\nSimulation plot saved successfully.")
