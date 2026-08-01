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

def run_single_bet_ev_sweep_simulation(db_path='data/db/predictions.db'):
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

    # レースごとの正規化勝率 & 勝率順位
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum
    df['win_rank'] = df.groupby('race_id')['pred_win'].rank(ascending=False, method='first')

    # 期待値 (EV) 計算
    df['ev'] = df['norm_win_prob'] * df['tansho_odds']

    # スイープするEV閾値のリスト
    ev_thresholds = [0.0, 0.8, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.2, 2.5]
    results_a = []
    results_b = []

    # ----------------------------------------------------
    # 戦術 A: 候補内 EV最大馬 1点買い (勝率>=10%, オッズ<=50, EV>=th)
    # ----------------------------------------------------
    base_a = df[(df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] <= 50.0)].copy()

    for th in ev_thresholds:
        cand_df = base_a[base_a['ev'] >= th].copy()
        r_bought = cand_df['race_id'].nunique()
        if r_bought == 0:
            continue
        
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

        label_str = f"EV >= {th:.1f}" if th > 0 else "制限なし"
        results_a.append({
            'strategy': '戦術A (候補内EV最大馬 1点)',
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
            'avg_prob': avg_prob
        })

    # ----------------------------------------------------
    # 戦術 B: AI予測勝率1位馬 限定買い (勝率>=10%, オッズ<=50, EV>=th)
    # ----------------------------------------------------
    base_b = df[df['win_rank'] == 1].copy()
    base_b_filtered = base_b[(base_b['norm_win_prob'] >= 0.10) & (base_b['tansho_odds'] <= 50.0)].copy()

    for th in ev_thresholds:
        selected = base_b_filtered[base_b_filtered['ev'] >= th].copy()
        r_bought = len(selected)
        if r_bought == 0:
            continue

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

        label_str = f"EV >= {th:.1f}" if th > 0 else "制限なし"
        results_b.append({
            'strategy': '戦術B (勝率1位馬 限定買い)',
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
            'avg_prob': avg_prob
        })

    df_a = pd.DataFrame(results_a)
    df_b = pd.DataFrame(results_b)

    print("\n==================================================")
    print("Strategy A: Candidate EV Max 1-Bet Sweep Summary")
    print("==================================================")
    print(df_a[['label', 'races', 'races_pct', 'hits', 'hit_rate', 'profit', 'recovery_rate', 'avg_odds', 'avg_prob']].to_string(index=False))

    print("\n==================================================")
    print("Strategy B: Win Prob #1 Horse Only 1-Bet Sweep Summary")
    print("==================================================")
    print(df_b[['label', 'races', 'races_pct', 'hits', 'hit_rate', 'profit', 'recovery_rate', 'avg_odds', 'avg_prob']].to_string(index=False))

    # 可視化: 2つの戦術の比較グラフ (回収率 & 購入レース数)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 回収率比較
    ax1.plot(df_a['label'], df_a['recovery_rate'], marker='o', linewidth=2.5, color='#d62728', label='戦術A (EV最大馬 1点買い)')
    ax1.plot(df_b['label'], df_b['recovery_rate'], marker='s', linewidth=2.5, color='#1f77b4', label='戦術B (勝率1位馬 限定買い)')
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')
    ax1.axhline(80, color='gray', linestyle=':', label='JRA控除率ライン(80%)')
    ax1.set_title('戦術別 EV閾値と回収率 (%) の推移比較', fontsize=13, fontweight='bold')
    ax1.set_xlabel('EV閾値条件', fontsize=11)
    ax1.set_ylabel('回収率 (%)', fontsize=11)
    ax1.set_xticklabels(df_a['label'], rotation=35)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)

    # 購入レース数比較
    ax2.plot(df_a['label'], df_a['races'], marker='o', linewidth=2.5, color='#d62728', label='戦術A (EV最大馬 1点買い)')
    ax2.plot(df_b['label'], df_b['races'], marker='s', linewidth=2.5, color='#1f77b4', label='戦術B (勝率1位馬 限定買い)')
    ax2.set_title('戦術別 EV閾値と購入レース数の推移比較', fontsize=13, fontweight='bold')
    ax2.set_xlabel('EV閾値条件', fontsize=11)
    ax2.set_ylabel('購入レース数 (全1,075レース中)', fontsize=11)
    ax2.set_xticklabels(df_a['label'], rotation=35)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10)

    plt.tight_layout()
    chart_path = os.path.join(ARTIFACT_DIR, 'ev_sweep_single_comparison.png')
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart_path}")

    return df_a, df_b

if __name__ == '__main__':
    run_single_bet_ev_sweep_simulation()
