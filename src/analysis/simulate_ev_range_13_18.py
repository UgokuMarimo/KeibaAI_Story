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

def run_ev_range_13_18_simulation(db_path='data/db/predictions.db'):
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

    # 固定条件: 勝率 >= 10% & オッズ <= 100
    base_df = df[(df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] <= 100.0)].copy()

    # 検証パターン設定
    patterns = [
        ('EV >= 1.3 (1.3以上すべて合算)', base_df[base_df['ev'] >= 1.3]),
        ('1.3 <= EV <= 1.8 (1.3〜1.8限定)', base_df[(base_df['ev'] >= 1.3) & (base_df['ev'] <= 1.8)]),
        ('EV >= 1.8 (1.8以上のみ)', base_df[base_df['ev'] >= 1.8])
    ]

    all_results = []

    for name, c_df in patterns:
        if len(c_df) == 0:
            continue

        # ------------------------------------------------
        # 買い方①: 単勝1点買い (候補内 EV最大1頭)
        # ------------------------------------------------
        c_df_single = c_df.copy()
        c_df_single['ev_rank'] = c_df_single.groupby('race_id')['ev'].rank(ascending=False, method='first')
        selected_single = c_df_single[c_df_single['ev_rank'] == 1].copy()

        races_single = len(selected_single)
        selected_single['is_hit'] = (selected_single['result_rank'] == 1).astype(int)
        selected_single['payout'] = selected_single['is_hit'] * selected_single['tansho_odds'] * 100
        hits_single = selected_single['is_hit'].sum()
        bet_single = races_single * 100
        pay_single = selected_single['payout'].sum()
        profit_single = pay_single - bet_single
        rr_single = (pay_single / bet_single * 100) if bet_single > 0 else 0
        hr_single = (hits_single / races_single * 100) if races_single > 0 else 0

        all_results.append({
            'EV条件パターン': name,
            '買い方': '単勝1点買い (最高EV1頭)',
            '購入レース数': races_single,
            '購入割合': f"{races_single/total_all_races*100:.1f}%",
            '総購入点数': races_single,
            '平均点数/レース': 1.0,
            '的中数': hits_single,
            '的中率': f"{hr_single:.2f}%",
            '総購入額': bet_single,
            '総払戻額': int(pay_single),
            '純損益': profit_single,
            '回収率': rr_single,
            '平均オッズ': selected_single['tansho_odds'].mean(),
            '平均EV': selected_single['ev'].mean()
        })

        # ------------------------------------------------
        # 買い方②: 多点買い (条件を満たす全頭)
        # ------------------------------------------------
        c_df_multi = c_df.copy()
        races_multi = c_df_multi['race_id'].nunique()
        total_bets_multi = len(c_df_multi)
        c_df_multi['is_hit'] = (c_df_multi['result_rank'] == 1).astype(int)
        c_df_multi['payout'] = c_df_multi['is_hit'] * c_df_multi['tansho_odds'] * 100
        
        hits_multi = c_df_multi['is_hit'].sum()
        bet_multi = total_bets_multi * 100
        pay_multi = c_df_multi['payout'].sum()
        profit_multi = pay_multi - bet_multi
        rr_multi = (pay_multi / bet_multi * 100) if bet_multi > 0 else 0
        hr_multi_pt = (hits_multi / total_bets_multi * 100) if total_bets_multi > 0 else 0
        avg_bets = total_bets_multi / races_multi if races_multi > 0 else 0

        all_results.append({
            'EV条件パターン': name,
            '買い方': '多点買い (条件全頭)',
            '購入レース数': races_multi,
            '購入割合': f"{races_multi/total_all_races*100:.1f}%",
            '総購入点数': total_bets_multi,
            '平均点数/レース': round(avg_bets, 2),
            '的中数': hits_multi,
            '的中率': f"{hr_multi_pt:.2f}%",
            '総購入額': bet_multi,
            '総払戻額': int(pay_multi),
            '純損益': profit_multi,
            '回収率': rr_multi,
            '平均オッズ': c_df_multi['tansho_odds'].mean(),
            '平均EV': c_df_multi['ev'].mean()
        })

    res_df = pd.DataFrame(all_results)
    print("\n==================================================")
    print("EV 1.3 - 1.8 Range & Combination Simulation Results")
    print("==================================================")
    print(res_df[['EV条件パターン', '買い方', '購入レース数', '購入割合', '総購入点数', '平均点数/レース', '的中率', '純損益', '回収率', '平均オッズ']].to_string(index=False))

    # 可視化: 比較グラフ生成
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 回収率比較
    single_res = res_df[res_df['買い方'] == '単勝1点買い (最高EV1頭)']
    multi_res = res_df[res_df['買い方'] == '多点買い (条件全頭)']
    
    labels = ['EV >= 1.3\n(1.3以上合算)', '1.3 <= EV <= 1.8\n(1.3〜1.8限定)', 'EV >= 1.8\n(1.8以上のみ)']
    x = np.arange(len(labels))
    width = 0.35

    rects1 = ax1.bar(x - width/2, single_res['回収率'], width, label='単勝1点買い (最高EV1頭)', color='#d62728', alpha=0.85)
    rects2 = ax1.bar(x + width/2, multi_res['回収率'], width, label='多点買い (条件全頭)', color='#1f77b4', alpha=0.85)

    ax1.set_ylabel('回収率 (%)', fontsize=12)
    ax1.set_title('EVパターン別 回収率 (%) 比較', fontsize=14, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.2)

    for bar in rects1:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.8, f"{h:.1f}%", ha='center', fontsize=9)
    for bar in rects2:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.8, f"{h:.1f}%", ha='center', fontsize=9)

    # 純損益比較
    rects3 = ax2.bar(x - width/2, single_res['純損益'], width, label='単勝1点買い (最高EV1頭)', color='#2ca02c', alpha=0.85)
    rects4 = ax2.bar(x + width/2, multi_res['純損益'], width, label='多点買い (条件全頭)', color='#ff7f0e', alpha=0.85)

    ax2.set_ylabel('純損益 (円)', fontsize=12)
    ax2.set_title('EVパターン別 純損益 (円) 比較', fontsize=14, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax2.legend(loc='lower right')
    ax2.grid(True, alpha=0.2)

    for bar in rects3:
        h = bar.get_height()
        va_val = 'bottom' if h >= 0 else 'top'
        offset = 500 if h >= 0 else -1500
        ax2.text(bar.get_x() + bar.get_width()/2., h + offset, f"{int(h):+,}円", ha='center', va=va_val, fontsize=8)
    for bar in rects4:
        h = bar.get_height()
        va_val = 'bottom' if h >= 0 else 'top'
        offset = 500 if h >= 0 else -1500
        ax2.text(bar.get_x() + bar.get_width()/2., h + offset, f"{int(h):+,}円", ha='center', va=va_val, fontsize=8)

    plt.tight_layout()
    chart_path = os.path.join(ARTIFACT_DIR, 'ev_range_13_18_comparison.png')
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart_path}")

    return res_df

if __name__ == '__main__':
    run_ev_range_13_18_simulation()
