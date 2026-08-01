import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- 日本語フォント設定 ---
plt.rcParams['font.family'] = 'MS Gothic'
plt.rcParams['axes.unicode_minus'] = False

# --- パス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

ARTIFACT_DIR = r"C:\Users\nao70\.gemini\antigravity-ide\brain\158c1ae1-f082-4367-bb54-36de09b8c467"

def run_golden_range_final_simulation(db_path='data/db/predictions.db'):
    if not os.path.isabs(db_path):
        db_path = os.path.join(PROJECT_ROOT, db_path)

    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, tansho_ninki, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND pred_win IS NOT NULL AND tansho_odds IS NOT NULL AND tansho_odds > 0
    ORDER BY kaisai_date ASC, race_id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    total_all_races = df['race_id'].nunique()

    # レースごとの正規化勝率
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum

    # 期待値 (EV) 計算
    df['ev'] = df['norm_win_prob'] * df['tansho_odds']

    # ----------------------------------------------------
    # 最終確定ルール: 勝率>=10%, オッズ2.0-30.0, 1.8 <= EV < 3.0
    # ----------------------------------------------------
    golden_cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] >= 2.0) & (df['tansho_odds'] <= 30.0) & (df['ev'] >= 1.8) & (df['ev'] < 3.0)
    cand_df = df[golden_cond].copy()

    # レース内で最高EVの1頭を選択
    cand_df['ev_rank'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
    selected_df = cand_df[cand_df['ev_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

    selected_df['is_hit'] = (selected_df['result_rank'] == 1).astype(int)
    selected_df['payout'] = selected_df['is_hit'] * selected_df['tansho_odds'] * 100
    selected_df['bet'] = 100
    selected_df['profit'] = selected_df['payout'] - selected_df['bet']
    selected_df['cum_profit'] = selected_df['profit'].cumsum()

    races_bought = len(selected_df)
    races_bought_pct = (races_bought / total_all_races * 100)
    hits_cnt = selected_df['is_hit'].sum()
    hit_rate = (hits_cnt / races_bought * 100) if races_bought > 0 else 0
    total_bet_amt = races_bought * 100
    total_payout_amt = selected_df['payout'].sum()
    net_profit = total_payout_amt - total_bet_amt
    recovery_rate = (total_payout_amt / total_bet_amt * 100) if total_bet_amt > 0 else 0

    avg_odds = selected_df['tansho_odds'].mean()
    avg_win_prob = selected_df['norm_win_prob'].mean() * 100
    avg_ev = selected_df['ev'].mean()

    print("\n==================================================")
    print("GOLDEN RANGE (1.8 <= EV < 3.0) FINAL BACKTEST RESULTS")
    print("==================================================")
    print(f"Total All Races    : {total_all_races:,} races")
    print(f"Bought Races       : {races_bought:,} races ({races_bought_pct:.1f}%)")
    print(f"Skipped Races      : {total_all_races - races_bought:,} races ({100 - races_bought_pct:.1f}%)")
    print(f"Hit Races (Hits)   : {hits_cnt:,} races")
    print(f"Hit Rate           : {hit_rate:.2f}%")
    print(f"Total Investment   : {total_bet_amt:,} yen")
    print(f"Total Payout       : {int(total_payout_amt):,} yen")
    print(f"Net Profit         : {int(net_profit):+,} yen")
    print(f"Recovery Rate      : {recovery_rate:.2f}%")
    print(f"Average Odds       : {avg_odds:.2f} x")
    print(f"Average Win Prob   : {avg_win_prob:.2f}%")
    print(f"Average EV         : {avg_ev:.2f}")
    print("==================================================")

    # 1. 月別成績集計
    selected_df['month'] = pd.to_datetime(selected_df['kaisai_date']).dt.to_period('M').astype(str)
    monthly_df = selected_df.groupby('month').agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100),
        bet=('bet', 'sum'),
        payout=('payout', 'sum'),
        profit=('profit', 'sum'),
        recovery_rate=('payout', lambda x: x.sum() / (len(x) * 100) * 100)
    ).reset_index()

    print("\n--- Monthly Performance ---")
    print(monthly_df.to_string(index=False))

    # 2. 可視化1: 黄金領域の累積純損益推移
    selected_df['race_idx'] = np.arange(1, len(selected_df) + 1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    ax1.plot(selected_df['race_idx'], selected_df['cum_profit'], color='#2ca02c', linewidth=2.5, label='黄金領域 (1.8<=EV<3.0) 累積純損益')
    ax1.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax1.set_title('新・実運用ルール (1.8 <= EV < 3.0, 勝率>=10%, オッズ2-30) 累積純損益推移', fontsize=14, fontweight='bold')
    ax1.set_ylabel('累積純損益 (円)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')

    selected_df['cum_bet'] = selected_df['bet'].cumsum()
    selected_df['cum_payout'] = selected_df['payout'].cumsum()
    selected_df['cum_recovery'] = selected_df['cum_payout'] / selected_df['cum_bet'] * 100
    selected_df['cum_hit_rate'] = selected_df['is_hit'].cumsum() / selected_df['race_idx'] * 100

    ax2.plot(selected_df['race_idx'], selected_df['cum_recovery'], color='#d62728', linewidth=2, label='累積回収率 (%)')
    ax2.plot(selected_df['race_idx'], selected_df['cum_hit_rate'], color='#1f77b4', linewidth=2, label='累積的中率 (%)')
    ax2.axhline(100, color='red', linestyle=':', linewidth=1.5, label='回収率 100%ライン')
    ax2.set_title('累積的中率・回収率の推移', fontsize=14, fontweight='bold')
    ax2.set_xlabel('購入レース数', fontsize=12)
    ax2.set_ylabel('パーセンテージ (%)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'golden_range_cumulative.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # 3. 可視化2: 黄金領域の月別成績
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(monthly_df))
    width = 0.35

    bars1 = ax1.bar(x - width/2, monthly_df['hit_rate'], width, label='的中率 (%)', color='#2ca02c', alpha=0.85)
    bars2 = ax2.bar(x + width/2, monthly_df['recovery_rate'], width, label='回収率 (%)', color='#d62728', alpha=0.85)

    ax1.set_xlabel('開催年月', fontsize=12)
    ax1.set_ylabel('的中率 (%)', fontsize=12, color='#2ca02c')
    ax2.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax1.set_xticks(x)
    ax1.set_xticklabels(monthly_df['month'], rotation=45)
    ax2.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    plt.title('新・黄金領域ルール 月別 的中率 & 回収率 推移', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'golden_range_monthly.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    return selected_df, monthly_df

if __name__ == '__main__':
    run_golden_range_final_simulation()
