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

def run_ev_fine_bins_simulation(db_path='data/db/predictions.db'):
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
    print(f"Total Rows: {len(df)}")
    print(f"Total All Races: {total_all_races}")

    # レースごとの正規化勝率
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum

    # 期待値 (EV) 計算
    df['ev'] = df['norm_win_prob'] * df['tansho_odds']

    # 固定条件: 勝率>=10%, オッズ2.0-30.0, EV>=1.0
    cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] >= 2.0) & (df['tansho_odds'] <= 30.0) & (df['ev'] >= 1.0)
    cand_df = df[cond].copy()

    # 各レースで最高EVの1頭を選択
    cand_df['ev_rank'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
    selected_df = cand_df[cand_df['ev_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

    selected_df['is_hit'] = (selected_df['result_rank'] == 1).astype(int)
    selected_df['payout'] = selected_df['is_hit'] * selected_df['tansho_odds'] * 100
    selected_df['bet'] = 100
    selected_df['profit'] = selected_df['payout'] - selected_df['bet']

    # 0.2刻みのEV帯ビン定義
    bins = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 3.0, 100.0]
    labels = [
        '1.0-1.19',
        '1.2-1.39',
        '1.4-1.59',
        '1.6-1.79',
        '1.8-1.99',
        '2.0-2.19',
        '2.2-2.39',
        '2.4-2.59',
        '2.6-2.99',
        '3.0+'
    ]
    selected_df['ev_bin'] = pd.cut(selected_df['ev'], bins=bins, labels=labels, right=False)

    # ビン別集計
    bin_summary = selected_df.groupby('ev_bin', observed=False).agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100 if len(x)>0 else 0),
        bet=('bet', 'sum'),
        payout=('payout', 'sum'),
        profit=('profit', 'sum'),
        recovery_rate=('payout', lambda x: x.sum() / (len(x) * 100) * 100 if len(x)>0 else 0),
        avg_odds=('tansho_odds', 'mean'),
        avg_prob=('norm_win_prob', lambda x: x.mean() * 100 if len(x)>0 else 0),
        avg_ev=('ev', 'mean')
    ).reset_index()

    bin_summary['races_pct'] = bin_summary['races'] / total_all_races * 100

    print("\n==================================================")
    print("Fine-Grained 0.2 EV Bin Breakdown Summary")
    print("==================================================")
    print(bin_summary[['ev_bin', 'races', 'races_pct', 'hits', 'hit_rate', 'profit', 'recovery_rate', 'avg_odds', 'avg_prob', 'avg_ev']].to_string(index=False))

    # 1. 可視化1: 0.2刻みEV帯別の回収率・的中率・購入レース数
    fig, ax1 = plt.subplots(figsize=(13, 6.5))
    ax2 = ax1.twinx()

    x = np.arange(len(bin_summary))
    width = 0.35

    bars1 = ax1.bar(x - width/2, bin_summary['recovery_rate'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    bars2 = ax2.bar(x + width/2, bin_summary['races'], width, label='購入レース数', color='#1f77b4', alpha=0.85)

    ax1.set_xlabel('0.2刻み EV帯 (勝率>=10% & オッズ2.0-30.0 固定)', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax2.set_ylabel('購入レース数', fontsize=12, color='#1f77b4')
    ax1.set_xticks(x)
    ax1.set_xticklabels(bin_summary['ev_bin'], rotation=30)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')

    for bar in bars1:
        yval = bar.get_height()
        if yval > 0:
            ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    for bar in bars2:
        yval = bar.get_height()
        if yval > 0:
            ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 1.5, f"{int(yval)}件", ha='center', va='bottom', fontsize=8)

    plt.title('0.2刻み EV帯別の購入レース数 & 回収率 比較 (単勝1点買い)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'ev_fine_bins_comparison.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # 2. 可視化2: 0.2刻みEV帯別の純損益 (円) バーチャート
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = ['#d62728' if p < 0 else '#2ca02c' for p in bin_summary['profit']]
    
    bars = ax.bar(bin_summary['ev_bin'], bin_summary['profit'], color=colors, alpha=0.85, width=0.55)
    ax.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax.set_title('0.2刻み EV帯別の純損益 (円) 比較', fontsize=14, fontweight='bold')
    ax.set_xlabel('0.2刻み EV帯', fontsize=12)
    ax.set_ylabel('純損益 (円)', fontsize=12)
    plt.xticks(rotation=30)
    ax.grid(True, alpha=0.2)

    for bar in bars:
        yval = bar.get_height()
        va_val = 'bottom' if yval >= 0 else 'top'
        offset = 500 if yval >= 0 else -1500
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + offset, f"{int(yval):+,}円", ha='center', va=va_val, fontsize=8)

    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'ev_fine_bins_profit.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    return bin_summary

if __name__ == '__main__':
    run_ev_fine_bins_simulation()
