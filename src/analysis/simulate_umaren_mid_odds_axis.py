# C:\KeibaAI\scratch\simulate_umaren_mid_odds_axis.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# パス設定
db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/umaren_mid_odds_axis_simulation.png"

def is_umaren_hit(axis_umaban, partner_umaban, umaren_numbers_str):
    """
    馬連的中判定
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

def run_simulation(df, partner_mode="ev"):
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
        
        # 1. 軸馬の選定: 期待値1.1以上、オッズ4〜30倍、予測順位3位以内
        axis_candidates = group[
            (group['win_ev'] >= 1.1) & 
            (group['tansho_odds'] >= 4.0) & 
            (group['tansho_odds'] <= 30.0) & 
            (group['pred_rank'] <= 3)
        ]
        if axis_candidates.empty:
            continue
            
        # 複数いる場合は、最もノーマライズ勝率が高い馬を1頭だけ選ぶ
        axis_horse = axis_candidates.sort_values(by='norm_pred_win', ascending=False).iloc[0]
        axis_umaban = axis_horse['umaban']
        
        # 2. 相手馬の選定
        if partner_mode == "ev":
            # シナリオ1: 相手も期待値が高い馬 (Win EV >= 1.1, 単勝30倍以下)
            partners = group[
                (group['win_ev'] >= 1.1) & 
                (group['tansho_odds'] <= 30.0) & 
                (group['umaban'] != axis_umaban)
            ]
        elif partner_mode == "rank":
            # シナリオ2: 相手は予測上位の実力馬 (AI予測4位以内)
            partners = group[
                (group['pred_rank'] <= 4) & 
                (group['umaban'] != axis_umaban)
            ]
        else:
            partners = pd.DataFrame()
            
        if partners.empty:
            continue
            
        # 3. 投票実行
        bet_races += 1
        race_cost = len(partners) * 100
        race_return = 0
        
        umaren_numbers = axis_horse['umaren_numbers']
        umaren_payout = axis_horse['umaren_payout']
        if pd.isna(umaren_payout) or umaren_payout is None:
            umaren_payout = 0
            
        for _, partner in partners.iterrows():
            total_bets += 1
            partner_umaban = partner['umaban']
            
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

    # 3. 2つのシナリオでシミュレーションを実行
    print("\n--- シミュレーション実行中 ---")
    
    # シナリオ1: 相手も期待値が高い馬 (EV流し)
    stats_ev = run_simulation(df, partner_mode="ev")
    print(f"【シナリオ1：期待値流し】購入レース数={stats_ev['bet_races']} R, 購入点数={stats_ev['total_bets']} 点, 回収率={stats_ev['recovery_rate']:.2f}%, 純利益={stats_ev['final_profit']:+,.0f}円")
    
    # シナリオ2: 相手は予測上位の実力馬 (上位流し)
    stats_rank = run_simulation(df, partner_mode="rank")
    print(f"【シナリオ2：予測上位流し】購入レース数={stats_rank['bet_races']} R, 購入点数={stats_rank['total_bets']} 点, 回収率={stats_rank['recovery_rate']:.2f}%, 純利益={stats_rank['final_profit']:+,.0f}円")

    # 4. 可視化
    plt.figure(figsize=(12, 7))
    plt.rcParams['font.family'] = 'MS Gothic'
    plt.rcParams['axes.unicode_minus'] = False
    
    if not stats_ev['sim_df'].empty:
        plt.plot(stats_ev['sim_df']['cum_profit'].values, 
                 label=f"シナリオ1: 期待値流し (回収率: {stats_ev['recovery_rate']:.1f}%, 購入:{stats_ev['bet_races']}R)", 
                 color='#1f77b4', linewidth=2.2)
                 
    if not stats_rank['sim_df'].empty:
        plt.plot(stats_rank['sim_df']['cum_profit'].values, 
                 label=f"シナリオ2: 予測上位流し (回収率: {stats_rank['recovery_rate']:.1f}%, 購入:{stats_rank['bet_races']}R)", 
                 color='#ff7f0e', linewidth=2.2)

    plt.axhline(0, color='black', linestyle='--', alpha=0.5)
    plt.title("中人気期待値軸馬からの馬連流し 回収率シミュレーション", fontsize=14, fontweight='bold')
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
