# C:\KeibaAI\scratch\simulate_umaren_axis.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# パス設定
db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/umaren_axis_simulation.png"

def is_umaren_hit(axis_umaban, partner_umaban, umaren_numbers_str):
    """
    馬連が的中しているかを判定するロバストな関数
    """
    if not umaren_numbers_str or pd.isna(umaren_numbers_str):
        return False
    
    parts = [p.strip() for p in str(umaren_numbers_str).split(',')]
    for part in parts:
        nums = [n.strip() for n in part.split('-')]
        if len(nums) == 2:
            try:
                hit_set = {int(nums[0]), int(nums[1])}
                buy_set = {int(axis_umaban), int(partner_umaban)}
                if hit_set == buy_set:
                    return True
            except ValueError:
                continue
    return False

def run_simulation_for_threshold(df, axis_prob_min, axis_ev_min, partner_ev_threshold, partner_odds_max):
    # レース単位でグループ化
    grouped = df.groupby('race_id')
    
    simulation_records = []
    
    total_races = 0
    bet_races = 0
    total_bets = 0
    total_hits = 0
    total_cost = 0
    total_return = 0

    for race_id, group in grouped:
        total_races += 1
        
        # 軸馬の選定: 予測1位かつ勝率しきい値以上、かつ軸馬の期待値が一定以上
        axis_candidates = group[
            (group['pred_rank'] == 1) & 
            (group['norm_pred_win'] >= axis_prob_min) &
            (group['win_ev'] >= axis_ev_min)
        ]
        if axis_candidates.empty:
            continue
            
        axis_horse = axis_candidates.iloc[0]
        axis_umaban = axis_horse['umaban']
        
        # 相手馬の選定: 単勝期待値しきい値以上、かつ単勝オッズ制限以下、かつ軸馬以外
        partners = group[
            (group['win_ev'] >= partner_ev_threshold) & 
            (group['tansho_odds'] <= partner_odds_max) & 
            (group['umaban'] != axis_umaban)
        ]
        
        if partners.empty:
            continue
            
        # 投票実行
        bet_races += 1
        race_cost = len(partners) * 100
        race_return = 0
        
        # 的中馬連文字列
        umaren_numbers = axis_horse['umaren_numbers']
        umaren_payout = axis_horse['umaren_payout']
        if pd.isna(umaren_payout) or umaren_payout is None:
            umaren_payout = 0
            
        for _, partner in partners.iterrows():
            total_bets += 1
            partner_umaban = partner['umaban']
            
            # 的中判定
            if is_umaren_hit(axis_umaban, partner_umaban, umaren_numbers):
                race_return += umaren_payout
                total_hits += 1
                
        total_cost += race_cost
        total_return += race_return
        net_profit = race_return - race_cost
        
        simulation_records.append({
            'race_id': race_id,
            'kaisai_date': axis_horse['kaisai_date'],
            'net_profit': net_profit
        })

    sim_df = pd.DataFrame(simulation_records)
    if not sim_df.empty:
        sim_df['cum_profit'] = sim_df['net_profit'].cumsum()
    
    stats = {
        'total_races': total_races,
        'bet_races': bet_races,
        'total_bets': total_bets,
        'total_hits': total_hits,
        'total_cost': total_cost,
        'total_return': total_return,
        'recovery_rate': (total_return / total_cost * 100) if total_cost > 0 else 0,
        'hit_rate': (total_hits / total_bets * 100) if total_bets > 0 else 0,
        'race_hit_rate': (sim_df['net_profit'] > -sim_df['net_profit'].clip(upper=0)).mean() * 100 if not sim_df.empty else 0,
        'final_profit': total_return - total_cost,
        'sim_df': sim_df
    }
    return stats

def main():
    # 1. データの読み込み
    conn = sqlite3.connect(db_path)
    query = """
    SELECT 
        p.race_id,
        p.umaban,
        p.horse_name,
        p.kaisai_date,
        p.pred_win,
        p.pred_rank,
        p.tansho_odds,
        p.result_rank,
        pay.umaren_payout,
        pay.umaren_numbers
    FROM predictions p
    JOIN payouts pay ON p.race_id = pay.race_id
    ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No data found for simulation.")
        return

    print(f"Loaded {len(df)} predictions from DB.")

    # 2. 前処理
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_pred_win'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['win_ev'] = df['norm_pred_win'] * df['tansho_odds']

    # 3. 軸馬の勝率しきい値は15%で固定し、軸馬の期待値(EV)制限を比較
    # パターン1: 軸勝率>=15%, 軸期待値>=0.0 (制限なし)
    # パターン2: 軸勝率>=15%, 軸期待値>=1.0
    # パターン3: 軸勝率>=15%, 軸期待値>=1.1
    scenarios = [
        {'label': '軸EV制限なし', 'prob_min': 0.15, 'ev_min': 0.0},
        {'label': '軸EV >= 1.0', 'prob_min': 0.15, 'ev_min': 1.0},
        {'label': '軸EV >= 1.1', 'prob_min': 0.15, 'ev_min': 1.1}
    ]
    
    results = {}
    print("\n--- シミュレーション実行中 (軸馬期待値フィルターの検証) ---")
    for sc in scenarios:
        stats = run_simulation_for_threshold(df, sc['prob_min'], sc['ev_min'], 1.1, 30.0)
        results[sc['label']] = stats
        print(f"【{sc['label']}】購入レース数={stats['bet_races']} R, 購入点数={stats['total_bets']} 点, 回収率={stats['recovery_rate']:.2f}%, 純利益={stats['final_profit']:+,.0f}円")

    # 4. 可視化
    plt.figure(figsize=(12, 7))
    plt.rcParams['font.family'] = 'MS Gothic'
    plt.rcParams['axes.unicode_minus'] = False
    
    colors = {'軸EV制限なし': '#1f77b4', '軸EV >= 1.0': '#ff7f0e', '軸EV >= 1.1': '#2ca02c'}
    
    for label, stats in results.items():
        sim_df = stats['sim_df']
        if not sim_df.empty:
            plt.plot(sim_df['cum_profit'].values, 
                     label=f"{label} (回収率: {stats['recovery_rate']:.1f}%, 購入:{stats['bet_races']}R)", 
                     color=colors[label], linewidth=2.2)

    plt.axhline(0, color='black', linestyle='--', alpha=0.5)
    plt.title("馬連一頭軸流し 軸馬期待値しきい値別 回収率シミュレーション (軸勝率>=15%)", fontsize=14, fontweight='bold')
    plt.xlabel("購入レース数 (累計)", fontsize=12)
    plt.ylabel("累積純損益 (円, 1点100円購入時)", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='upper left', fontsize=11)

    os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
    plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nSimulation plot saved to {save_img_path}")

if __name__ == '__main__':
    main()
