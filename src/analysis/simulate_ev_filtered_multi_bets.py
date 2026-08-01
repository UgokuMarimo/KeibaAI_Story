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

def run_ev_filtered_multi_simulation(db_path='data/db/predictions.db'):
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

    # フラグ設定
    df['is_hit'] = (df['result_rank'] == 1).astype(int)
    df['payout'] = df['is_hit'] * df['tansho_odds'] * 100
    df['bet'] = 100

    # ----------------------------------------------------
    # 1. 主目的: EV >= 1.0 かつ tansho_odds <= 100.0
    # ----------------------------------------------------
    sub100_df = df[(df['ev'] >= 1.0) & (df['tansho_odds'] <= 100.0)].copy().sort_values(['kaisai_date', 'race_id'])
    
    races_bought = sub100_df['race_id'].nunique()
    total_bets_cnt = len(sub100_df)
    
    total_bet_amt = total_bets_cnt * 100
    total_payout_amt = sub100_df['payout'].sum()
    net_profit = total_payout_amt - total_bet_amt
    recovery_rate = (total_payout_amt / total_bet_amt * 100) if total_bet_amt > 0 else 0

    hit_bets_cnt = sub100_df['is_hit'].sum()
    point_hit_rate = (hit_bets_cnt / total_bets_cnt * 100) if total_bets_cnt > 0 else 0
    
    race_hits = sub100_df.groupby('race_id')['is_hit'].max().sum()
    race_hit_rate = (race_hits / races_bought * 100) if races_bought > 0 else 0
    avg_bets_per_race = total_bets_cnt / races_bought if races_bought > 0 else 0
    avg_odds = sub100_df['tansho_odds'].mean()
    avg_ev = sub100_df['ev'].mean()

    summary_text = (
        f"==================================================\n"
        f"Keiba AI EV >= 1.0 & Odds <= 100 Multi-Bet Results\n"
        f"==================================================\n"
        f"Total All Races    : {total_all_races:,} races\n"
        f"Bought Races       : {races_bought:,} races ({races_bought/total_all_races*100:.1f}%)\n"
        f"Total Bets Count   : {total_bets_cnt:,} bets (Avg {avg_bets_per_race:.2f} bets/race)\n"
        f"Hit Bets Count     : {hit_bets_cnt:,} bets\n"
        f"Hit Race Count     : {race_hits:,} races\n"
        f"Point Hit Rate     : {point_hit_rate:.2f}%\n"
        f"Race Hit Rate      : {race_hit_rate:.2f}%\n"
        f"Total Investment   : {total_bet_amt:,} yen\n"
        f"Total Payout       : {int(total_payout_amt):,} yen\n"
        f"Net Profit         : {int(net_profit):+,} yen\n"
        f"Recovery Rate      : {recovery_rate:.2f}%\n"
        f"Average Odds       : {avg_odds:.2f} x\n"
        f"Average EV         : {avg_ev:.2f}\n"
        f"==================================================\n"
    )
    print(summary_text)

    # 2. 可視化1: 累積損益推移 (レース順)
    race_summary = sub100_df.groupby(['kaisai_date', 'race_id']).agg(
        bets_count=('bet', 'count'),
        bet_amount=('bet', 'sum'),
        payout_amount=('payout', 'sum'),
        hit_count=('is_hit', 'sum')
    ).reset_index().sort_values(['kaisai_date', 'race_id'])

    race_summary['profit'] = race_summary['payout_amount'] - race_summary['bet_amount']
    race_summary['cum_profit'] = race_summary['profit'].cumsum()
    race_summary['cum_bet'] = race_summary['bet_amount'].cumsum()
    race_summary['cum_payout'] = race_summary['payout_amount'].cumsum()
    race_summary['cum_recovery'] = race_summary['cum_payout'] / race_summary['cum_bet'] * 100
    race_summary['race_idx'] = np.arange(1, len(race_summary) + 1)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    ax1.plot(race_summary['race_idx'], race_summary['cum_profit'], color='#17becf', linewidth=2, label='累積純損益 (円)')
    ax1.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax1.set_title('EV >= 1.0 かつ 単勝オッズ <= 100 多点買い 累積純損益推移', fontsize=14, fontweight='bold')
    ax1.set_ylabel('累積純損益 (円)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')

    ax2.plot(race_summary['race_idx'], race_summary['cum_recovery'], color='#d62728', linewidth=2, label='累積回収率 (%)')
    ax2.axhline(100, color='red', linestyle=':', linewidth=1.5, label='回収率 100%ライン')
    ax2.set_title('EV >= 1.0 かつ 単勝オッズ <= 100 多点買い 累積回収率推移', fontsize=14, fontweight='bold')
    ax2.set_xlabel('購入レース数', fontsize=12)
    ax2.set_ylabel('回収率 (%)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'ev_odds100_cumulative_profit.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"Saved: {chart1_path}")

    # 3. オッズ上限（感度分析）の比較 (EV >= 1.0 固定)
    odds_limits = [9999.0, 100.0, 50.0, 30.0, 20.0, 10.0, 5.0]
    odds_res = []

    for limit in odds_limits:
        m_df = df[(df['ev'] >= 1.0) & (df['tansho_odds'] <= limit)]
        r_bought = m_df['race_id'].nunique()
        b_cnt = len(m_df)
        if b_cnt == 0:
            continue
        h_cnt = m_df['is_hit'].sum()
        r_hits = m_df.groupby('race_id')['is_hit'].max().sum() if r_bought > 0 else 0
        
        b_amt = b_cnt * 100
        p_amt = m_df['payout'].sum()
        prof = p_amt - b_amt
        rr = (p_amt / b_amt * 100)
        
        pt_hr = (h_cnt / b_cnt * 100)
        rc_hr = (r_hits / r_bought * 100) if r_bought > 0 else 0
        avg_bets = b_cnt / r_bought if r_bought > 0 else 0
        avg_o = m_df['tansho_odds'].mean()

        label_str = f"オッズ <= {limit:.0f}" if limit < 1000 else "上限なし"
        odds_res.append({
            'オッズ条件': label_str,
            'limit': limit,
            '購入レース数': r_bought,
            '総購入点数': b_cnt,
            '平均点数/レース': avg_bets,
            '点的中率': pt_hr,
            'レース的中率': rc_hr,
            '総購入額': b_amt,
            '総払戻額': int(p_amt),
            '純損益': prof,
            '回収率': rr,
            '平均オッズ': avg_o
        })

    odds_df = pd.DataFrame(odds_res)
    print("\n--- Odds Limit Sensitivity Analysis (EV >= 1.0) ---")
    print(odds_df[['オッズ条件', '購入レース数', '総購入点数', '平均点数/レース', '点的中率', 'レース的中率', '純損益', '回収率', '平均オッズ']].to_string(index=False))

    # 4. 可視化2: オッズ上限別の回収率 & 平均購入点数バーチャート
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(odds_df))
    width = 0.35

    bars1 = ax1.bar(x - width/2, odds_df['回収率'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    bars2 = ax2.bar(x + width/2, odds_df['平均点数/レース'], width, label='平均購入点数 / レース', color='#17becf', alpha=0.85)

    ax1.set_xlabel('オッズ上限 (EV >= 1.0 固定)', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#d62728')
    ax2.set_ylabel('平均購入点数 (点/レース)', fontsize=12, color='#17becf')
    ax1.set_xticks(x)
    ax1.set_xticklabels(odds_df['オッズ条件'], rotation=15)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=8)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.05, f"{yval:.2f}点", ha='center', va='bottom', fontsize=8)

    plt.title('EV >= 1.0 条件における オッズ上限別の回収率 & 平均購入点数 比較', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'ev_odds_limit_comparison.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    return sub100_df, odds_df

if __name__ == '__main__':
    run_ev_filtered_multi_simulation()
