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

def run_simulation(db_path='data/db/predictions.db'):
    if not os.path.isabs(db_path):
        db_path = os.path.join(PROJECT_ROOT, db_path)

    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, tansho_ninki, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND pred_win IS NOT NULL
    ORDER BY kaisai_date ASC, race_id ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # レースごとの正規化勝率
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum

    # レース内での予測勝率順位
    # 同率の場合は馬番の若い順
    df['pred_rank'] = df.groupby('race_id')['pred_win'].rank(ascending=False, method='first')

    # 各レースの予測勝率1位馬を抽出
    top1_df = df[df['pred_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

    # シミュレーション結果フラグ＆払戻金計算 (1点100円ベタ買い)
    top1_df['is_hit'] = (top1_df['result_rank'] == 1).astype(int)
    top1_df['payout'] = top1_df['is_hit'] * top1_df['tansho_odds'] * 100
    top1_df['bet_amount'] = 100
    top1_df['profit'] = top1_df['payout'] - top1_df['bet_amount']
    top1_df['cum_profit'] = top1_df['profit'].cumsum()
    top1_df['cum_bet'] = top1_df['bet_amount'].cumsum()
    top1_df['cum_payout'] = top1_df['payout'].cumsum()
    top1_df['cum_hit_rate'] = top1_df['is_hit'].cumsum() / (np.arange(len(top1_df)) + 1) * 100
    top1_df['cum_recovery_rate'] = top1_df['cum_payout'] / top1_df['cum_bet'] * 100

    # 1. 基本成績サマリー
    total_races = len(top1_df)
    hit_races = top1_df['is_hit'].sum()
    hit_rate = (hit_races / total_races) * 100
    total_bet = top1_df['bet_amount'].sum()
    total_payout = top1_df['payout'].sum()
    total_profit = total_payout - total_bet
    recovery_rate = (total_payout / total_bet) * 100
    avg_odds = top1_df['tansho_odds'].mean()

    summary_text = (
        f"==================================================\n"
        f"Keiba AI Top Win Bet Simulation Results\n"
        f"==================================================\n"
        f"Total Races      : {total_races:,} races\n"
        f"Hit Races        : {hit_races:,} races\n"
        f"Hit Rate         : {hit_rate:.2f}%\n"
        f"Total Investment : {total_bet:,} yen\n"
        f"Total Payout     : {int(total_payout):,} yen\n"
        f"Net Profit       : {int(total_profit):+,} yen\n"
        f"Recovery Rate    : {recovery_rate:.2f}%\n"
        f"Average Odds     : {avg_odds:.2f} x\n"
        f"==================================================\n"
    )
    print(summary_text)

    # 2. 可視化1: 累積収支および的中率・回収率の時系列推移
    top1_df['race_idx'] = np.arange(1, len(top1_df) + 1)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    # 上段: 累積純損益推移
    ax1.plot(top1_df['race_idx'], top1_df['cum_profit'], color='#1f77b4', linewidth=2, label='累積純損益 (円)')
    ax1.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax1.set_title('勝率1位馬 単勝ベタ買い 累積純損益推移', fontsize=14, fontweight='bold')
    ax1.set_ylabel('累積純損益 (円)', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')

    # 下段: 累積的中率・回収率推移
    ax2.plot(top1_df['race_idx'], top1_df['cum_recovery_rate'], color='#d62728', linewidth=2, label='累積回収率 (%)')
    ax2.plot(top1_df['race_idx'], top1_df['cum_hit_rate'], color='#2ca02c', linewidth=2, label='累積的中率 (%)')
    ax2.axhline(100, color='red', linestyle=':', linewidth=1.5, label='回収率 100%ライン')
    ax2.set_title('累積的中率・回収率の推移', fontsize=14, fontweight='bold')
    ax2.set_xlabel('通算レース数', fontsize=12)
    ax2.set_ylabel('パーセンテージ (%)', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'cumulative_performance.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"Saved: {chart1_path}")

    # 3. 月別成績集計 & 可視化
    top1_df['month'] = pd.to_datetime(top1_df['kaisai_date']).dt.to_period('M').astype(str)
    monthly_df = top1_df.groupby('month').agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100),
        bet=('bet_amount', 'sum'),
        payout=('payout', 'sum'),
        profit=('profit', 'sum'),
        recovery_rate=('payout', lambda x: x.sum() / (len(x) * 100) * 100)
    ).reset_index()

    print("\n--- Monthly Performance ---")
    print(monthly_df.to_string(index=False))

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

    # 数値ラベル追加
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=9)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{yval:.1f}%", ha='center', va='bottom', fontsize=9)

    plt.title('月別 的中率 & 回収率 推移', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'monthly_performance.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    # 4. 単勝オッズ帯別 & 予測勝率帯別の分析
    # オッズ帯
    bins_odds = [0, 2.0, 3.0, 5.0, 10.0, 100.0]
    labels_odds = ['1.0〜1.9倍', '2.0〜2.9倍', '3.0〜4.9倍', '5.0〜9.9倍', '10.0倍以上']
    top1_df['odds_band'] = pd.cut(top1_df['tansho_odds'], bins=bins_odds, labels=labels_odds)

    odds_df = top1_df.groupby('odds_band', observed=False).agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100 if len(x)>0 else 0),
        recovery_rate=('payout', lambda x: x.sum() / (len(x)*100) * 100 if len(x)>0 else 0)
    ).reset_index()

    print("\n--- Odds Band Performance ---")
    print(odds_df.to_string(index=False))

    # 予測勝率帯 (norm_win_prob)
    bins_prob = [0, 0.20, 0.25, 0.30, 0.40, 1.00]
    labels_prob = ['勝率<20%', '勝率20〜25%', '勝率25〜30%', '勝率30〜40%', '勝率40%+']
    top1_df['prob_band'] = pd.cut(top1_df['norm_win_prob'], bins=bins_prob, labels=labels_prob)

    prob_df = top1_df.groupby('prob_band', observed=False).agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100 if len(x)>0 else 0),
        recovery_rate=('payout', lambda x: x.sum() / (len(x)*100) * 100 if len(x)>0 else 0)
    ).reset_index()

    print("\n--- Predicted Win Prob Band Performance ---")
    print(prob_df.to_string(index=False))

    # 人気（単勝1番人気か否か）
    top1_df['ninki_type'] = np.where(top1_df['tansho_ninki'] == 1, '1st Ninki', '2nd Ninki or lower')
    ninki_df = top1_df.groupby('ninki_type').agg(
        races=('is_hit', 'count'),
        hits=('is_hit', 'sum'),
        hit_rate=('is_hit', lambda x: x.mean() * 100),
        recovery_rate=('payout', lambda x: x.sum() / (len(x)*100) * 100)
    ).reset_index()

    print("\n--- Ninki Type Performance ---")
    print(ninki_df.to_string(index=False))

    # 可視化3: オッズ帯別 & 予測勝率帯別の分析グラフ
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # オッズ帯
    x1 = np.arange(len(odds_df))
    width = 0.35
    b1 = ax1.bar(x1 - width/2, odds_df['hit_rate'], width, label='的中率 (%)', color='#2ca02c', alpha=0.85)
    b2 = ax1.bar(x1 + width/2, odds_df['recovery_rate'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    ax1.set_xticks(x1)
    ax1.set_xticklabels(odds_df['odds_band'], rotation=30)
    ax1.set_title('単勝オッズ帯別 的中率 & 回収率', fontsize=13, fontweight='bold')
    ax1.set_ylabel('パーセンテージ (%)', fontsize=11)
    ax1.axhline(100, color='red', linestyle='--', alpha=0.7)
    ax1.legend()
    ax1.grid(True, alpha=0.2)

    for b in b1:
        h = b.get_height()
        if h > 0: ax1.text(b.get_x()+b.get_width()/2, h+0.5, f"{h:.1f}%", ha='center', fontsize=8)
    for b in b2:
        h = b.get_height()
        if h > 0: ax1.text(b.get_x()+b.get_width()/2, h+0.5, f"{h:.1f}%", ha='center', fontsize=8)

    # 勝率帯
    x2 = np.arange(len(prob_df))
    b3 = ax2.bar(x2 - width/2, prob_df['hit_rate'], width, label='的中率 (%)', color='#2ca02c', alpha=0.85)
    b4 = ax2.bar(x2 + width/2, prob_df['recovery_rate'], width, label='回収率 (%)', color='#d62728', alpha=0.85)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(prob_df['prob_band'], rotation=30)
    ax2.set_title('AI予測勝率帯別 的中率 & 回収率', fontsize=13, fontweight='bold')
    ax2.set_ylabel('パーセンテージ (%)', fontsize=11)
    ax2.axhline(100, color='red', linestyle='--', alpha=0.7)
    ax2.legend()
    ax2.grid(True, alpha=0.2)

    for b in b3:
        h = b.get_height()
        if h > 0: ax2.text(b.get_x()+b.get_width()/2, h+0.5, f"{h:.1f}%", ha='center', fontsize=8)
    for b in b4:
        h = b.get_height()
        if h > 0: ax2.text(b.get_x()+b.get_width()/2, h+0.5, f"{h:.1f}%", ha='center', fontsize=8)

    plt.tight_layout()
    chart3_path = os.path.join(ARTIFACT_DIR, 'breakdown_performance.png')
    plt.savefig(chart3_path, dpi=150)
    plt.close()
    print(f"Saved: {chart3_path}")

    return top1_df

if __name__ == '__main__':
    run_simulation()
