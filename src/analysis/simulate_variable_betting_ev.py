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

def get_variable_bet_amount(ev):
    if 1.2 <= ev < 1.4:
        return 100
    elif 1.4 <= ev < 1.6:
        return 200
    elif 1.6 <= ev < 1.8:
        return 300
    elif 1.8 <= ev <= 2.0:
        return 400
    else:
        return 0

def run_variable_betting_simulation(db_path='data/db/predictions.db'):
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
    # 条件: 勝率>=10%, オッズ2.0-30.0, 1.2 <= EV <= 2.0
    # ----------------------------------------------------
    cond = (df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] >= 2.0) & (df['tansho_odds'] <= 30.0) & (df['ev'] >= 1.2) & (df['ev'] <= 2.0)
    cand_df = df[cond].copy()

    # 各レースで最高EVの1頭を選択
    cand_df['ev_rank'] = cand_df.groupby('race_id')['ev'].rank(ascending=False, method='first')
    selected_df = cand_df[cand_df['ev_rank'] == 1].copy().sort_values(['kaisai_date', 'race_id'])

    # 可変賭け金 (傾斜配分) の算出
    selected_df['bet_var'] = selected_df['ev'].apply(get_variable_bet_amount)
    selected_df['bet_fixed'] = 100

    selected_df['is_hit'] = (selected_df['result_rank'] == 1).astype(int)
    selected_df['payout_var'] = selected_df['is_hit'] * selected_df['tansho_odds'] * selected_df['bet_var']
    selected_df['payout_fixed'] = selected_df['is_hit'] * selected_df['tansho_odds'] * selected_df['bet_fixed']

    selected_df['profit_var'] = selected_df['payout_var'] - selected_df['bet_var']
    selected_df['profit_fixed'] = selected_df['payout_fixed'] - selected_df['bet_fixed']

    selected_df['cum_profit_var'] = selected_df['profit_var'].cumsum()
    selected_df['cum_profit_fixed'] = selected_df['profit_fixed'].cumsum()

    # 全体数値集計
    races_bought = len(selected_df)
    races_bought_pct = (races_bought / total_all_races * 100)
    hits_cnt = selected_df['is_hit'].sum()
    hit_rate = (hits_cnt / races_bought * 100) if races_bought > 0 else 0

    # 傾斜配分
    total_bet_var = selected_df['bet_var'].sum()
    total_payout_var = selected_df['payout_var'].sum()
    net_profit_var = total_payout_var - total_bet_var
    recovery_rate_var = (total_payout_var / total_bet_var * 100) if total_bet_var > 0 else 0

    # 定額100円
    total_bet_fixed = selected_df['bet_fixed'].sum()
    total_payout_fixed = selected_df['payout_fixed'].sum()
    net_profit_fixed = total_payout_fixed - total_bet_fixed
    recovery_rate_fixed = (total_payout_fixed / total_bet_fixed * 100) if total_bet_fixed > 0 else 0

    print("\n==================================================")
    print("Variable Betting (EV 1.2-2.0, Odds 2-30) Results")
    print("==================================================")
    print(f"Bought Races       : {races_bought:,} races ({races_bought_pct:.1f}%)")
    print(f"Hit Races          : {hits_cnt:,} races (Hit Rate: {hit_rate:.2f}%)")
    print(f"--- 傾斜配分 (可変賭け金 100-400円) ---")
    print(f"Total Investment   : {total_bet_var:,} yen")
    print(f"Total Payout       : {int(total_payout_var):,} yen")
    print(f"Net Profit         : {int(net_profit_var):+,} yen")
    print(f"Recovery Rate      : {recovery_rate_var:.2f}%")
    print(f"--- 定額買い (均一100円) ---")
    print(f"Total Investment   : {total_bet_fixed:,} yen")
    print(f"Total Payout       : {int(total_payout_fixed):,} yen")
    print(f"Net Profit         : {int(net_profit_fixed):+,} yen")
    print(f"Recovery Rate      : {recovery_rate_fixed:.2f}%")
    print("==================================================")

    # ----------------------------------------------------
    # 2. EV帯別のブレイクダウン分析
    # ----------------------------------------------------
    bins_ev = [1.2, 1.4, 1.6, 1.8, 2.001]
    labels_ev = ['1.2〜1.39 (100円)', '1.4〜1.59 (200円)', '1.6〜1.79 (300円)', '1.8〜2.00 (400円)']
    selected_df['ev_band'] = pd.cut(selected_df['ev'], bins=bins_ev, labels=labels_ev, right=False)

    ev_band_df = selected_df.groupby('ev_band', observed=False).agg(
        購入数=('is_hit', 'count'),
        的中数=('is_hit', 'sum'),
        的中率=('is_hit', lambda x: x.mean() * 100 if len(x)>0 else 0),
        傾斜購入額=('bet_var', 'sum'),
        傾斜払戻額=('payout_var', 'sum'),
        傾斜損益=('profit_var', 'sum'),
        傾斜回収率=('payout_var', lambda x: x.sum() / selected_df.loc[x.index, 'bet_var'].sum() * 100 if len(x)>0 and selected_df.loc[x.index, 'bet_var'].sum()>0 else 0),
        定額購入額=('bet_fixed', 'sum'),
        定額払戻額=('payout_fixed', 'sum'),
        定額損益=('profit_fixed', 'sum'),
        定額回収率=('payout_fixed', lambda x: x.sum() / selected_df.loc[x.index, 'bet_fixed'].sum() * 100 if len(x)>0 and selected_df.loc[x.index, 'bet_fixed'].sum()>0 else 0),
        平均オッズ=('tansho_odds', 'mean')
    ).reset_index()

    print("\n--- EV Band Breakdown ---")
    print(ev_band_df[['ev_band', '購入数', '的中数', '的中率', '傾斜購入額', '傾斜払戻額', '傾斜損益', '傾斜回収率', '定額回収率', '平均オッズ']].to_string(index=False))

    # ----------------------------------------------------
    # 3. 可視化1: 通算累積損益推移 (傾斜配分 vs 定額買い)
    # ----------------------------------------------------
    selected_df['race_idx'] = np.arange(1, len(selected_df) + 1)
    
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(selected_df['race_idx'], selected_df['cum_profit_var'], color='#2ca02c', linewidth=2.5, label='傾斜配分(可変賭け金 100-400円)')
    ax.plot(selected_df['race_idx'], selected_df['cum_profit_fixed'], color='#1f77b4', linewidth=2, linestyle='--', label='定額買い(均一100円)')

    ax.axhline(0, color='gray', linestyle='--', linewidth=1)
    ax.set_title('期待値1.2-2.0 傾斜配分(可変賭け金) vs 定額買い 累積純損益推移', fontsize=14, fontweight='bold')
    ax.set_xlabel('購入レース数', fontsize=12)
    ax.set_ylabel('累積純損益 (円)', fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', fontsize=11)

    plt.tight_layout()
    chart1_path = os.path.join(ARTIFACT_DIR, 'variable_betting_cumulative_profit.png')
    plt.savefig(chart1_path, dpi=150)
    plt.close()
    print(f"\nSaved: {chart1_path}")

    # ----------------------------------------------------
    # 4. 可視化2: EV帯別の回収率 & 購入金額ブレイクダウン
    # ----------------------------------------------------
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()

    x = np.arange(len(ev_band_df))
    width = 0.35

    bars1 = ax1.bar(x - width/2, ev_band_df['傾斜回収率'], width, label='傾斜配分 回収率 (%)', color='#2ca02c', alpha=0.85)
    bars2 = ax2.bar(x + width/2, ev_band_df['購入数'], width, label='購入レース数', color='#1f77b4', alpha=0.85)

    ax1.set_xlabel('EV帯（設定賭け金）', fontsize=12)
    ax1.set_ylabel('回収率 (%)', fontsize=12, color='#2ca02c')
    ax2.set_ylabel('購入レース数', fontsize=12, color='#1f77b4')
    ax1.set_xticks(x)
    ax1.set_xticklabels(ev_band_df['ev_band'], rotation=15)
    ax1.axhline(100, color='red', linestyle='--', linewidth=1.5, label='回収率100%ライン')

    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.6, f"{yval:.1f}%", ha='center', va='bottom', fontsize=9)

    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 2, f"{int(yval)}件", ha='center', va='bottom', fontsize=9)

    plt.title('EV帯別の回収率 & 購入レース数 ブレイクダウン', fontsize=14, fontweight='bold')
    plt.tight_layout()
    chart2_path = os.path.join(ARTIFACT_DIR, 'variable_betting_breakdown.png')
    plt.savefig(chart2_path, dpi=150)
    plt.close()
    print(f"Saved: {chart2_path}")

    # ----------------------------------------------------
    # 5. オッズ上限比較 (オッズ30 vs 50 vs 100)
    # ----------------------------------------------------
    odds_limits = [30.0, 50.0, 100.0]
    odds_comp = []

    for omax in odds_limits:
        sub_c = df[(df['norm_win_prob'] >= 0.10) & (df['tansho_odds'] >= 2.0) & (df['tansho_odds'] <= omax) & (df['ev'] >= 1.2) & (df['ev'] <= 2.0)].copy()
        if len(sub_c) == 0: continue
        sub_c['ev_rank'] = sub_c.groupby('race_id')['ev'].rank(ascending=False, method='first')
        sel = sub_c[sub_c['ev_rank'] == 1].copy()
        
        sel['bet_var'] = sel['ev'].apply(get_variable_bet_amount)
        sel['is_hit'] = (sel['result_rank'] == 1).astype(int)
        sel['payout_var'] = sel['is_hit'] * sel['tansho_odds'] * sel['bet_var']

        r_cnt = len(sel)
        h_cnt = sel['is_hit'].sum()
        b_var = sel['bet_var'].sum()
        p_var = sel['payout_var'].sum()
        prof_v = p_var - b_var
        rr_v = p_var / b_var * 100

        b_fix = r_cnt * 100
        p_fix = (sel['is_hit'] * sel['tansho_odds'] * 100).sum()
        prof_f = p_fix - b_fix
        rr_f = p_fix / b_fix * 100

        odds_comp.append({
            'オッズ条件': f"オッズ 2.0〜{omax:.0f}倍",
            '購入レース数': r_cnt,
            '的中数': h_cnt,
            '的中率': f"{h_cnt/r_cnt*100:.2f}%",
            '傾斜購入額': f"{b_var:,}円",
            '傾斜払戻額': f"{int(p_var):,}円",
            '傾斜純損益': f"{int(prof_v):+,}円",
            '傾斜回収率': f"{rr_v:.2f}%",
            '定額回収率': f"{rr_f:.2f}%"
        })

    odds_comp_df = pd.DataFrame(odds_comp)
    print("\n--- Odds Limit Comparison with Variable Betting ---")
    print(odds_comp_df.to_string(index=False))

    return selected_df, ev_band_df, odds_comp_df

if __name__ == '__main__':
    run_variable_betting_simulation()
