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

def run_ev_single_filtered_simulation(db_path='data/db/predictions.db'):
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

    # ----------------------------------------------------
    # 1. メイン条件: 勝率 >= 0.10, オッズ <= 100, EV >= 1.0
    # ----------------------------------------------------
    cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] <= 100.0) & (df['ev'] >= 1.0)
    cand_df = df[cond].copy()

    # 各レースで上記条件を満たす馬の中から、EVが最大の1頭を選択
    cand_df['ev_rank_in_cand'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
    selected_df = cand_df[cand_df['ev_rank_in_cand'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

    # 集計計算
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

    summary_text = (
        f"==================================================\n"
        f"Keiba AI Filtered Single Bet Results (Prob>=10%, Odds<=100, EV>=1.0)\n"
        f"==================================================\n"
        f"Total All Races    : {total_all_races:,} races\n"
        f"Bought Races       : {races_bought:,} races ({races_bought_pct:.1f}%)\n"
        f"Skipped Races      : {total_all_races - races_bought:,} races ({100 - races_bought_pct:.1f}%)\n"
        f"Hit Races (Hits)   : {hits_cnt:,} races\n"
        f"Hit Rate           : {hit_rate:.2f}%\n"
        f"Total Investment   : {total_bet_amt:,} yen\n"
        f"Total Payout       : {int(total_payout_amt):,} yen\n"
        f"Net Profit         : {int(net_profit):+,} yen\n"
        f"Recovery Rate      : {recovery_rate:.2f}%\n"
        f"Average Odds       : {avg_odds:.2f} x\n"
        f"Average Win Prob   : {avg_win_prob:.2f}%\n"
        f"Average EV         : {avg_ev:.2f}\n"
        f"==================================================\n"
    )
    print(summary_text)

    # 2. 可視化1: 累積損益推移 (レース順)
    selected_df['race_idx'] = np.arange(1, len(selected_df) + 1)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    ax1.plot(selected_df['race_idx'], selected_df['cum_profit'], color='#2ca02c', linewidth=2, label='累積純損益 (円)')
    ax1.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax1.set_title('勝率>=10% & オッズ<=100 & EV>=1.0 最高馬単勝1点買い 累積純損益推移', fontsize=14, fontweight='bold')
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
    chart1_path = os.path.join(ARTIFACT_DIR, 'ev_single_filtered_cumulative_profit.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"Saved: {chart1_path}")

    # 3. 勝率下限の感度分析 (オッズ<=100 & EV>=1.0 固定)
    prob_limits = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    prob_res = []

    for p_min in prob_limits:
        c_sub = df[(df['norm_win_prob'] >= p_min) & (df['tansho_odds'] <= 100.0) & (df['ev'] >= 1.0)].copy()
        if len(c_sub) == 0:
            continue
        c_sub['ev_rank_in_cand'] = c_sub.groupby('race_id')['ev'].rank(ascending=False, method='first')
        sel = c_sub[c_sub['ev_rank_in_cand'] == 1].copy()
        
        r_bought = len(sel)
        if r_bought == 0:
            continue
        sel['is_hit'] = (sel['result_rank'] == 1).astype(int)
        sel['payout'] = sel['is_hit'] * sel['tansho_odds'] * 100
        
        h_cnt = sel['is_hit'].sum()
        hr = (h_cnt / r_bought * 100)
        b_amt = r_bought * 100
        p_amt = sel['payout'].sum()
        prof = p_amt - b_amt
        rr = (p_amt / b_amt * 100)
        avg_o = sel['tansho_odds'].mean()
        avg_p = sel['norm_win_prob'].mean() * 100

        label_str = f"勝率 >= {int(p_min*100)}%" if p_min > 0 else "制限なし"
        prob_res.append({
            '勝率下限': label_str,
            'p_min': p_min,
            '購入レース数': r_bought,
            '購入割合': f"{r_bought/total_all_races*100:.1f}%",
            '的中数': h_cnt,
            '的中率': hr,
            '総購入額': b_amt,
            '総払戻額': int(p_amt),
            '純損益': prof,
            '回収率': rr,
            '平均オッズ': avg_o,
            '平均予測勝率': avg_p
        })

    prob_df = pd.DataFrame(prob_res)
    print("\n--- Win Prob Limit Sensitivity Analysis (Odds<=100 & EV>=1.0, Single Bet) ---")
    print(prob_df[['勝率下限', '購入レース数', '購入割合', '的中率', '純損益', '回収率', '平均オッズ', '平均予測勝率']].to_string(index=False))

    # 4. 可視化2: 勝率下限別の購入レース数 & 回収率バーチャート
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(prob_df))
    width = 0.35

    bars1 = ax1.bar(x - width/2, prob_df['回収率'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    bars2 = ax2.bar(x + width/2, prob_df['購入レース数'], width, label='購入レース数', color='#2ca02c', alpha=0.85)

    ax1.set_xlabel('勝率下限条件 (オッズ<=100 & EV>=1.0 固定)', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax2.set_ylabel('購入レース数 (全1,075レース中)', fontsize=12, color='#2ca02c')
    ax1.set_xticks(x)
    ax1.set_xticklabels(prob_df['勝率下限'], rotation=15)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=9)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 5, f"{int(yval)}件", ha='center', va='bottom', fontsize=9)

    plt.title('勝率下限別の購入レース数 & 回収率 比較 (単勝1点買い)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'win_prob_limit_comparison.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    return selected_df, prob_df

if __name__ == '__main__':
    run_ev_single_filtered_simulation()
