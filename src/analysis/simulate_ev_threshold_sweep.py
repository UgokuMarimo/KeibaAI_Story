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

def run_ev_threshold_sweep_simulation(db_path='data/db/predictions.db'):
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

    # 固定フィルタ: 勝率 >= 10% & オッズ <= 100
    base_cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] <= 100.0)
    base_df = df[base_cond].copy()

    # スイープするEV閾値のリスト
    ev_thresholds = [0.0, 0.8, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0]
    sweep_results = []

    for th in ev_thresholds:
        cand_df = base_df[base_df['ev'] >= th].copy()
        r_bought = cand_df['race_id'].nunique()
        if r_bought == 0:
            continue
        
        # レース内でEVが最大の1頭を選択
        cand_df['ev_rank'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
        selected = cand_df[cand_df['ev_rank'] == 1].copy()

        selected['is_hit'] = (selected['result_rank'] == 1).astype(int)
        selected['payout'] = selected['is_hit'] * selected['tansho_odds'] * 100
        selected['bet'] = 100

        hits_cnt = selected['is_hit'].sum()
        hit_rate = (hits_cnt / r_bought * 100)
        total_bet = r_bought * 100
        total_payout = selected['payout'].sum()
        profit = total_payout - total_bet
        recovery_rate = (total_payout / total_bet * 100)
        
        avg_odds = selected['tansho_odds'].mean()
        avg_prob = selected['norm_win_prob'].mean() * 100
        avg_ev = selected['ev'].mean()

        label_str = f"EV >= {th:.1f}" if th > 0 else "制限なし"
        sweep_results.append({
            'label': label_str,
            'th': th,
            'races': r_bought,
            'races_pct': (r_bought / total_all_races * 100),
            'hits': hits_cnt,
            'hit_rate': hit_rate,
            'bet': total_bet,
            'payout': int(total_payout),
            'profit': profit,
            'recovery_rate': recovery_rate,
            'avg_odds': avg_odds,
            'avg_prob': avg_prob,
            'avg_ev': avg_ev
        })

    sweep_df = pd.DataFrame(sweep_results)
    print("\n==================================================")
    print("EV Threshold Sweep Simulation Summary")
    print("==================================================")
    print(sweep_df[['label', 'races', 'races_pct', 'hits', 'hit_rate', 'profit', 'recovery_rate', 'avg_odds', 'avg_prob', 'avg_ev']].to_string(index=False))

    # 1. 可視化1: EV閾値ごとの「購入レース数」と「回収率」の複合比較グラフ
    fig, ax1 = plt.subplots(figsize=(13, 6.5))
    ax2 = ax1.twinx()

    x = np.arange(len(sweep_df))
    width = 0.38

    bars1 = ax1.bar(x - width/2, sweep_df['recovery_rate'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    bars2 = ax2.bar(x + width/2, sweep_df['races'], width, label='購入レース数', color='#1f77b4', alpha=0.85)

    ax1.set_xlabel('EV(期待値) 閾値条件 (勝率>=10% & オッズ<=100 固定)', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax2.set_ylabel('購入レース数 (全1,075レース中)', fontsize=12, color='#1f77b4')
    ax1.set_xticks(x)
    ax1.set_xticklabels(sweep_df['label'], rotation=30)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.6, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 5, f"{int(yval)}件", ha='center', va='bottom', fontsize=8)

    plt.title('EV閾値変化による購入レース数 & 回収率 スイープ比較 (単勝1点買い)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'ev_threshold_sweep_comparison.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # 2. 可視化2: EV閾値ごとの「純損益 (円)」比較バーチャート
    fig, ax = plt.subplots(figsize=(13, 6))
    colors = ['#d62728' if p < 0 else '#2ca02c' for p in sweep_df['profit']]
    
    bars = ax.bar(sweep_df['label'], sweep_df['profit'], color=colors, alpha=0.85, width=0.55)
    ax.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax.set_title('EV閾値変化による純損益 (円) 比較', fontsize=14, fontweight='bold')
    ax.set_xlabel('EV閾値条件', fontsize=12)
    ax.set_ylabel('純損益 (円)', fontsize=12)
    plt.xticks(rotation=30)
    ax.grid(True, alpha=0.2)

    for bar in bars:
        yval = bar.get_height()
        va_val = 'bottom' if yval >= 0 else 'top'
        offset = 500 if yval >= 0 else -1500
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + offset, f"{int(yval):+,}円", ha='center', va=va_val, fontsize=8)

    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'ev_threshold_sweep_profit.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    return sweep_df

if __name__ == '__main__':
    run_ev_threshold_sweep_simulation()
