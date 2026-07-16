# C:\KeibaAI\scratch\analyze_rentai_rate.py
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/rentai_rate_analysis.png"

def main():
    # 1. データの読み込み
    conn = sqlite3.connect(db_path)
    query = """
    SELECT 
        race_id,
        umaban,
        pred_win,
        pred_rank,
        tansho_odds,
        result_rank
    FROM predictions
    ORDER BY kaisai_date ASC, race_id ASC, umaban ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No data found.")
        return

    print(f"Loaded {len(df)} predictions from DB.")

    # 2. 前処理
    # 連対フラグ (2着以内)
    df['is_rentai'] = np.where(df['result_rank'].isin([1, 2]), 1, 0)

    # 予測勝率のノーマライズ (レース内の合計を1.0にする)
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_pred_win'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)

    # 単勝期待値の計算 (ノーマライズ版)
    df['win_ev'] = df['norm_pred_win'] * df['tansho_odds']

    # 3. 集計
    print("\n=== 1. レース内予測順位(pred_rank)ごとの連対率 ===")
    # 予測順位が1〜8位までの馬を対象
    rank_summary = df[df['pred_rank'] <= 8].groupby('pred_rank')['is_rentai'].agg(['count', 'mean']).reset_index()
    rank_summary['mean'] *= 100
    for idx, row in rank_summary.iterrows():
        print(f"予測順位 {int(row['pred_rank'])}位: サンプル数={int(row['count']):,}頭, 連対率={row['mean']:.2f}%")

    print("\n=== 2. 予測勝率(norm_pred_win)ごとの連対率 ===")
    # 予測勝率をビンに分割
    win_bins = [0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 1.0]
    win_labels = ['0-5%', '5-10%', '10-15%', '15-20%', '20-30%', '30-40%', '40%以上']
    df['win_bin'] = pd.cut(df['norm_pred_win'], bins=win_bins, labels=win_labels)
    win_summary = df.groupby('win_bin', observed=False)['is_rentai'].agg(['count', 'mean']).reset_index()
    win_summary['mean'] *= 100
    for idx, row in win_summary.iterrows():
        print(f"予測勝率 {row['win_bin']}: サンプル数={int(row['count']):,}頭, 連対率={row['mean']:.2f}%")

    print("\n=== 3. 期待値(win_ev)ごとの連対率 ===")
    # 期待値をビンに分割
    ev_bins = [0, 0.6, 0.8, 1.0, 1.2, 1.4, 2.0, 999.0]
    ev_labels = ['<0.6', '0.6-0.8', '0.8-1.0', '1.0-1.2', '1.2-1.4', '1.4-2.0', '2.0以上']
    df['ev_bin'] = pd.cut(df['win_ev'], bins=ev_bins, labels=ev_labels)
    ev_summary = df.groupby('ev_bin', observed=False)['is_rentai'].agg(['count', 'mean']).reset_index()
    ev_summary['mean'] *= 100
    for idx, row in ev_summary.iterrows():
        print(f"期待値 {row['ev_bin']}: サンプル数={int(row['count']):,}頭, 連対率={row['mean']:.2f}%")

    # 4. 可視化
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    plt.rcParams['font.family'] = 'MS Gothic'
    plt.rcParams['axes.unicode_minus'] = False

    # 予測順位グラフ
    axes[0].bar(rank_summary['pred_rank'], rank_summary['mean'], color='#1f77b4', alpha=0.8, edgecolor='black')
    axes[0].set_title('予測順位 vs 連対率', fontsize=12, fontweight='bold')
    axes[0].set_xlabel('予測順位 (pred_rank)')
    axes[0].set_ylabel('連対率 (%)')
    axes[0].grid(True, linestyle='--', alpha=0.5)
    for i, v in enumerate(rank_summary['mean']):
        axes[0].text(rank_summary['pred_rank'][i], v + 1, f"{v:.1f}%", ha='center', fontsize=9)

    # 予測勝率グラフ
    axes[1].bar(win_summary['win_bin'], win_summary['mean'], color='#2ca02c', alpha=0.8, edgecolor='black')
    axes[1].set_title('予測勝率 vs 連対率', fontsize=12, fontweight='bold')
    axes[1].set_xlabel('予測勝率 (ノーマライズ値)')
    axes[1].set_ylabel('連対率 (%)')
    axes[1].tick_params(axis='x', rotation=30)
    axes[1].grid(True, linestyle='--', alpha=0.5)
    for i, v in enumerate(win_summary['mean']):
        axes[1].text(i, v + 1, f"{v:.1f}%", ha='center', fontsize=9)

    # 期待値グラフ
    axes[2].bar(ev_summary['ev_bin'], ev_summary['mean'], color='#ff7f0e', alpha=0.8, edgecolor='black')
    axes[2].set_title('期待値 vs 連対率', fontsize=12, fontweight='bold')
    axes[2].set_xlabel('単勝期待値 (Win EV)')
    axes[2].set_ylabel('連対率 (%)')
    axes[2].tick_params(axis='x', rotation=30)
    axes[2].grid(True, linestyle='--', alpha=0.5)
    for i, v in enumerate(ev_summary['mean']):
        axes[2].text(i, v + 1, f"{v:.1f}%", ha='center', fontsize=9)

    plt.suptitle("馬連軸馬選定のための連対率分析 (2着以内確率)", fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()

    os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
    plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nAnalysis plot saved to {save_img_path}")

if __name__ == '__main__':
    main()
