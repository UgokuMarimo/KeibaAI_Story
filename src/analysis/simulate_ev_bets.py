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

def run_ev_simulation(db_path='data/db/predictions.db'):
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

    # 1. レースごとの正規化勝率 & 勝率順位
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum
    df['win_rank'] = df.groupby('race_id')['pred_win'].rank(ascending=False, method='first')

    # 2. 期待値 (EV) 計算
    df['ev'] = df['norm_win_prob'] * df['tansho_odds']
    df['ev_rank_all'] = df.groupby('race_id')['ev'].rank(ascending=False, method='first')

    # 3. 戦術1: 単純全馬EV1位 (制限なし)
    ev_all_top = df[df['ev_rank_all'] == 1].copy().sort_values(['kaisai_date', 'race_id'])
    ev_all_top['is_hit'] = (ev_all_top['result_rank'] == 1).astype(int)
    ev_all_top['payout'] = ev_all_top['is_hit'] * ev_all_top['tansho_odds'] * 100
    ev_all_top['bet'] = 100
    ev_all_top['profit'] = ev_all_top['payout'] - ev_all_top['bet']
    ev_all_top['cum_profit'] = ev_all_top['profit'].cumsum()

    # 4. 戦術2: 勝率上位3頭の中でEV1位の馬
    top3_win = df[df['win_rank'] <= 3].copy()
    top3_win['ev_rank_top3'] = top3_win.groupby('race_id')['ev'].rank(ascending=False, method='first')
    ev_top3_top = top3_win[top3_win['ev_rank_top3'] == 1].copy().sort_values(['kaisai_date', 'race_id'])
    ev_top3_top['is_hit'] = (ev_top3_top['result_rank'] == 1).astype(int)
    ev_top3_top['payout'] = ev_top3_top['is_hit'] * ev_top3_top['tansho_odds'] * 100
    ev_top3_top['bet'] = 100
    ev_top3_top['profit'] = ev_top3_top['payout'] - ev_top3_top['bet']
    ev_top3_top['cum_profit'] = ev_top3_top['profit'].cumsum()

    # 5. 戦術3: 勝率1位馬の中でEV >= 1.0の馬だけ購入
    win1_df = df[df['win_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])
    win1_df['is_hit'] = (win1_df['result_rank'] == 1).astype(int)
    win1_df['payout'] = win1_df['is_hit'] * win1_df['tansho_odds'] * 100
    win1_df['bet'] = 100
    win1_df['profit'] = win1_df['payout'] - win1_df['bet']

    ev_win1_ev10 = win1_df[win1_df['ev'] >= 1.0].copy()
    ev_win1_ev10['cum_profit'] = ev_win1_ev10['profit'].cumsum()

    # 6. 集計・サマリー算出
    strategies = [
        ('勝率1位ベタ買い(前回の結果)', win1_df),
        ('全馬中EV1位(制限なし)', ev_all_top),
        ('勝率上位3頭の中でEV1位', ev_top3_top),
        ('勝率1位馬 & EV>=1.0', ev_win1_ev10),
    ]

    res_list = []
    for name, sdf in strategies:
        n_races = len(sdf)
        n_hits = sdf['is_hit'].sum()
        hr = (n_hits / n_races * 100) if n_races > 0 else 0
        b_sum = sdf['bet'].sum()
        p_sum = sdf['payout'].sum()
        prof = p_sum - b_sum
        rr = (p_sum / b_sum * 100) if b_sum > 0 else 0
        avg_o = sdf['tansho_odds'].mean()
        avg_ev = sdf['ev'].mean()

        res_list.append({
            '戦術': name,
            '対象レース': n_races,
            '的中数': n_hits,
            '的中率 (%)': f"{hr:.2f}%",
            '購入額 (円)': f"{b_sum:,}",
            '払戻額 (円)': f"{int(p_sum):,}",
            '損益 (円)': f"{int(prof):+,}",
            '回収率 (%)': f"{rr:.2f}%",
            '平均オッズ': f"{avg_o:.2f}倍",
            '平均EV': f"{avg_ev:.2f}"
        })

    summary_df = pd.DataFrame(res_list)
    print("\n==================================================")
    print("Strategy Comparison Summary")
    print("==================================================")
    print(summary_df.to_string(index=False))

    # 7. 可視化1: 戦術別の累積純損益推移比較
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(np.arange(1, len(win1_df) + 1), win1_df['profit'].cumsum(), label='勝率1位 ベタ買い', color='#2ca02c', alpha=0.8)
    ax.plot(np.arange(1, len(ev_all_top) + 1), ev_all_top['cum_profit'], label='全馬中EV1位 (制限なし)', color='#d62728', alpha=0.8)
    ax.plot(np.arange(1, len(ev_top3_top) + 1), ev_top3_top['cum_profit'], label='勝率上位3頭の中でEV1位', color='#1f77b4', linewidth=2)
    ax.plot(np.arange(1, len(ev_win1_ev10) + 1), ev_win1_ev10['cum_profit'], label='勝率1位馬 & EV>=1.0', color='#ff7f0e', linewidth=2)

    ax.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax.set_title('期待値(EV)活用戦術の累積純損益推移 比較', fontsize=14, fontweight='bold')
    ax.set_xlabel('購入レース数', fontsize=12)
    ax.set_ylabel('累積純損益 (円)', fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', fontsize=10)

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'ev_strategy_comparison.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # 8. 「勝率上位3頭の中でEV1位」のEV閾値分析
    ev_thresholds = [0.0, 1.0, 1.2, 1.5, 2.0]
    sub_res = []
    for th in ev_thresholds:
        sdf = ev_top3_top[ev_top3_top['ev'] >= th]
        n_races = len(sdf)
        if n_races == 0: continue
        n_hits = sdf['is_hit'].sum()
        hr = (n_hits / n_races * 100)
        b_sum = sdf['bet'].sum()
        p_sum = sdf['payout'].sum()
        prof = p_sum - b_sum
        rr = (p_sum / b_sum * 100)
        sub_res.append({
            'EV閾値': f"EV >= {th:.1f}" if th > 0 else "制限なし",
            'レース数': n_races,
            '的中数': n_hits,
            '的中率': f"{hr:.2f}%",
            '回収率': f"{rr:.2f}%",
            '損益': f"{int(prof):+,}円"
        })
    print("\n--- Top3 Win Prob -> EV Top Threshold Breakdown ---")
    print(pd.DataFrame(sub_res).to_string(index=False))

    return summary_df

if __name__ == '__main__':
    run_ev_simulation()
