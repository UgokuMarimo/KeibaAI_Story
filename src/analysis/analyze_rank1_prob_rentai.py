# C:\KeibaAI\scratch\analyze_rank1_prob_rentai.py
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/rank1_prob_rentai_analysis.png"

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

    # 2. 前処理
    # 連対フラグ (2着以内)
    df['is_rentai'] = np.where(df['result_rank'].isin([1, 2]), 1, 0)

    # 予測勝率のノーマライズ (レース内の合計を1.0にする)
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_pred_win'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)

    # 予測1位の馬のみを抽出
    rank1_df = df[df['pred_rank'] == 1].copy()
    total_rank1 = len(rank1_df)

    print(f"Total Rank 1 horses: {total_rank1} records.")

    # 3. 予測勝率のしきい値ごとの集計
    thresholds = [0.0, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.30]
    
    results = []
    print("\n--- 予測1位の勝率しきい値別 連対率 ---")
    for th in thresholds:
        filtered = rank1_df[rank1_df['norm_pred_win'] >= th]
        count = len(filtered)
        if count > 0:
            rentai_rate = filtered['is_rentai'].mean() * 100
            win_rate = (filtered['result_rank'] == 1).mean() * 100
        else:
            rentai_rate = 0.0
            win_rate = 0.0
            
        results.append({
            'threshold': th,
            'threshold_pct': f"{th*100:.0f}%",
            'count': count,
            'win_rate': win_rate,
            'rentai_rate': rentai_rate
        })
        print(f"勝率 >= {th*100:2.0f}%: 該当数={count:3d}頭, 勝率={win_rate:5.1f}%, 連対率={rentai_rate:5.1f}%")

    res_df = pd.DataFrame(results)

    # 4. 可視化
    plt.figure(figsize=(10, 6))
    plt.rcParams['font.family'] = 'MS Gothic'
    plt.rcParams['axes.unicode_minus'] = False

    # 折れ線グラフで勝率と連対率をプロット
    plt.plot(res_df['threshold'] * 100, res_df['rentai_rate'], marker='o', color='#1f77b4', linewidth=2.5, label='連対率 (2着以内)')
    plt.plot(res_df['threshold'] * 100, res_df['win_rate'], marker='s', color='#ff7f0e', linewidth=2, linestyle='--', label='勝率 (1着)')
    
    # 棒グラフで該当頭数をプロット (右軸)
    ax2 = plt.gca().twinx()
    ax2.bar(res_df['threshold'] * 100, res_df['count'], alpha=0.15, color='gray', width=1.5, label='該当頭数')
    ax2.set_ylabel('該当頭数', color='gray')
    ax2.tick_params(axis='y', labelcolor='gray')

    # 設定
    plt.title("予測1位の予測勝率(ノーマライズ)しきい値別 勝率・連対率", fontsize=14, fontweight='bold')
    plt.gca().set_xlabel('勝率しきい値 (%)')
    plt.gca().set_ylabel('確率 (%)')
    plt.grid(True, linestyle='--', alpha=0.5)
    
    # 凡例を合体
    lines, labels = plt.gca().get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    plt.legend(lines + lines2, labels + labels2, loc='upper right')

    # 各点にラベル付け
    for idx, row in res_df.iterrows():
        plt.gca().text(row['threshold']*100, row['rentai_rate'] + 1, f"{row['rentai_rate']:.1f}%", ha='center', va='bottom', fontsize=9, color='#1f77b4')
        plt.gca().text(row['threshold']*100, row['win_rate'] - 2.5, f"{row['win_rate']:.1f}%", ha='center', va='top', fontsize=9, color='#ff7f0e')

    os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
    plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nAnalysis plot saved to {save_img_path}")

if __name__ == '__main__':
    main()
