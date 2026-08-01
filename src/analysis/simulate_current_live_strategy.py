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

def run_live_strategy_simulation(db_path='data/db/predictions.db'):
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
    # 1. 現行実運用ルール: 勝率>=10%, オッズ2.0~30.0, EV>=1.3
    # ----------------------------------------------------
    live_cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] >= 2.0) & (df['tansho_odds'] <= 30.0) & (df['ev'] >= 1.3)
    cand_df = df[live_cond].copy()

    # 各レースで最高EVの1頭を選択
    cand_df['ev_rank'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
    selected_df = cand_df[cand_df['ev_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

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
        f"CURRENT LIVE STRATEGY BACKTEST RESULTS\n"
        f"Condition: WinProb >= 10%, Odds 2.0-30.0, EV >= 1.3\n"
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

    # 2. 月別成績集計
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

    print("--- Current Live Strategy Monthly Performance ---")
    print(monthly_df.to_string(index=False))

    # 3. 可視化1: 累積損益推移
    selected_df['race_idx'] = np.arange(1, len(selected_df) + 1)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    ax1.plot(selected_df['race_idx'], selected_df['cum_profit'], color='#1f77b4', linewidth=2, label='累積純損益 (円)')
    ax1.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax1.set_title('現行実運用ルール (勝率>=10%, オッズ2-30, EV>=1.3) 累積純損益推移', fontsize=14, fontweight='bold')
    ax1.set_ylabel('累積純損益 (円)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')

    selected_df['cum_bet'] = selected_df['bet'].cumsum()
    selected_df['cum_payout'] = selected_df['payout'].cumsum()
    selected_df['cum_recovery'] = selected_df['cum_payout'] / selected_df['cum_bet'] * 100
    selected_df['cum_hit_rate'] = selected_df['is_hit'].cumsum() / selected_df['race_idx'] * 100

    ax2.plot(selected_df['race_idx'], selected_df['cum_recovery'], color='#d62728', linewidth=2, label='累積回収率 (%)')
    ax2.plot(selected_df['race_idx'], selected_df['cum_hit_rate'], color='#2ca02c', linewidth=2, label='累積的中率 (%)')
    ax2.axhline(100, color='red', linestyle=':', linewidth=1.5, label='回収率 100%ライン')
    ax2.axhline(80, color='gray', linestyle=':', label='JRA控除率ライン(80%)')
    ax2.set_title('累積的中率・回収率の推移', fontsize=14, fontweight='bold')
    ax2.set_xlabel('購入レース数', fontsize=12)
    ax2.set_ylabel('パーセンテージ (%)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'live_strategy_cumulative_profit.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # 4. 可視化2: 月別成績バーチャート
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

    plt.title('現行実運用ルール 月別 的中率 & 回収率 推移', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'live_strategy_monthly.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    # 5. 実運用ルールの改善チューニング比較
    tuning_configs = [
        ('現行ルール (EV>=1.3, オッズ2-30)', 0.10, 2.0, 30.0, 1.3),
        ('改善案1 (EV>=1.6, オッズ2-30)', 0.10, 2.0, 30.0, 1.6),
        ('改善案2 (EV>=1.8, オッズ2-30)', 0.10, 2.0, 30.0, 1.8),
        ('改善案3 (EV>=1.6, オッズ2-50)', 0.10, 2.0, 50.0, 1.6),
        ('改善案4 (EV>=1.8, オッズ2-50)', 0.10, 2.0, 50.0, 1.8),
        ('改善案5 (EV>=1.8, オッズ2-100)', 0.10, 2.0, 100.0, 1.8),
    ]

    tuning_res = []
    for cname, pmin, omin, omax, evmin in tuning_configs:
        c_df = df[(df['norm_win_prob'] >= pmin) & (df['tansho_odds'] >= omin) & (df['tansho_odds'] <= omax) & (df['ev'] >= evmin)].copy()
        if len(c_df) == 0: continue
        c_df['ev_rank'] = c_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
        sel = c_df[c_df['ev_rank'] == 1].copy()
        
        r_bought = len(sel)
        if r_bought == 0: continue
        sel['is_hit'] = (sel['result_rank'] == 1).astype(int)
        sel['payout'] = sel['is_hit'] * sel['tansho_odds'] * 100
        
        h_cnt = sel['is_hit'].sum()
        hr = (h_cnt / r_bought * 100)
        b_amt = r_bought * 100
        p_amt = sel['payout'].sum()
        prof = p_amt - b_amt
        rr = (p_amt / b_amt * 100)

        tuning_res.append({
            'ルール設定': cname,
            '購入レース数': r_bought,
            '購入割合': f"{r_bought/total_all_races*100:.1f}%",
            '的中数': h_cnt,
            '的中率': f"{hr:.2f}%",
            '総購入額': f"{b_amt:,}円",
            '総払戻額': f"{int(p_amt):,}円",
            '純損益': f"{int(prof):+,}円",
            '回収率': f"{rr:.2f}%",
            'prof_val': prof,
            'rr_val': rr,
            'avg_odds': sel['tansho_odds'].mean()
        })

    t_df = pd.DataFrame(tuning_res)
    print("\n--- Tuning Comparison for Live Strategy ---")
    print(t_df[['ルール設定', '購入レース数', '購入割合', '的中率', '純損益', '回収率', 'avg_odds']].to_string(index=False))

    # 可視化3: チューニング比較バーチャート
    fig, ax1 = plt.subplots(figsize=(13, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(t_df))
    width = 0.35

    bars1 = ax1.bar(x - width/2, t_df['rr_val'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    bars2 = ax2.bar(x + width/2, t_df['購入レース数'], width, label='購入レース数', color='#1f77b4', alpha=0.85)

    ax1.set_xlabel('ルール設定', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax2.set_ylabel('購入レース数', fontsize=12, color='#1f77b4')
    ax1.set_xticks(x)
    ax1.set_xticklabels(t_df['ルール設定'], rotation=25)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.6, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 5, f"{int(yval)}件", ha='center', va='bottom', fontsize=8)

    plt.title('現行実運用ルール vs 改善チューニング案の性能比較', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart3_path = os.path.join(ARTIFACT_DIR, 'live_strategy_tuning.png')
    plt.savefig(chart3_path, dpi=150)
    plt.close()
    print(f"Saved: {chart3_path}")

    return selected_df, monthly_df, t_df

if __name__ == '__main__':
    run_live_strategy_simulation()
