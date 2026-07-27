import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# 日本語フォント設定
plt.rcParams['font.family'] = 'MS Gothic'
plt.rcParams['axes.unicode_minus'] = False

def create_gap_plots():
    db_path = 'data/db/predictions.db'
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT race_id, umaban, horse_name, kaisai_date, pred_win, tansho_odds, tansho_ninki, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND pred_win IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 正規化
    race_sum = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / race_sum
    df['pred_rank'] = df.groupby('race_id')['norm_win_prob'].rank(ascending=False, method='min')
    
    races_1st = df[df['pred_rank'] == 1].drop_duplicates(subset=['race_id'], keep='first')
    races_2nd = df[df['pred_rank'] == 2].drop_duplicates(subset=['race_id'], keep='first')
    
    merged = pd.merge(
        races_1st, 
        races_2nd[['race_id', 'norm_win_prob', 'result_rank', 'tansho_odds', 'horse_name', 'tansho_ninki']], 
        on='race_id', 
        suffixes=('_1st', '_2nd')
    )
    
    merged['prob_gap'] = merged['norm_win_prob_1st'] - merged['norm_win_prob_2nd']
    merged['prob_ratio'] = merged['norm_win_prob_1st'] / merged['norm_win_prob_2nd']
    merged['is_win_1st'] = (merged['result_rank_1st'] == 1).astype(int)
    merged['is_top3_1st'] = (merged['result_rank_1st'] <= 3).astype(int)
    merged['payout_1st'] = merged['is_win_1st'] * merged['tansho_odds_1st'] * 100
    merged['is_1st_favorite'] = (merged['tansho_ninki_1st'] == 1)
    
    gap_bins = [-0.001, 0.03, 0.06, 0.10, 0.15, 0.20, 1.00]
    gap_labels = ['< 3%\n(混戦)', '3% - 6%', '6% - 10%', '10% - 15%', '15% - 20%', '20%+\n(抜けて強い)']
    merged['gap_band'] = pd.cut(merged['prob_gap'], bins=gap_bins, labels=gap_labels)

    # 出力先ディレクトリ
    artifact_dir = r"C:\Users\nao70\.gemini\antigravity-ide\brain\ead3888b-beba-4c3b-a5af-c1f77a92d20c"
    os.makedirs(artifact_dir, exist_ok=True)
    
    # -------------------------------------------------------------
    # グラフ 1: 勝率ギャップ別の実際の勝率 & 単勝回収率
    # -------------------------------------------------------------
    summary_list = []
    for label in gap_labels:
        g = merged[merged['gap_band'] == label]
        n = len(g)
        if n > 0:
            summary_list.append({
                'gap_band': label,
                'races': n,
                'actual_win_rate': g['is_win_1st'].sum() / n * 100,
                'actual_top3_rate': g['is_top3_1st'].sum() / n * 100,
                'recovery_rate': g['payout_1st'].sum() / (n * 100) * 100
            })
    summary = pd.DataFrame(summary_list)

    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=130)

    color1 = '#2b5c8f' # ダークブルー
    color2 = '#e65100' # オレンジ
    color3 = '#2e7d32' # グリーン

    x = np.arange(len(summary))
    width = 0.35

    rects1 = ax1.bar(x - width/2, summary['actual_win_rate'], width, label='1着的中率 (%)', color=color1, alpha=0.9)
    rects2 = ax1.bar(x + width/2, summary['actual_top3_rate'], width, label='複勝圏内率 (1-3着 %)', color=color3, alpha=0.85)

    ax1.set_ylabel('的中率 / 複勝率 (%)', fontsize=12, fontweight='bold')
    ax1.set_title('予測勝率1位 vs 2位のギャップ別 的中率・複勝率推移', fontsize=14, pad=15, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(summary['gap_band'], fontsize=10)
    ax1.set_ylim(0, 85)
    ax1.grid(axis='y', linestyle='--', alpha=0.4)

    # 数値ラベル
    for rect in rects1:
        height = rect.get_height()
        ax1.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color=color1)

    for rect in rects2:
        height = rect.get_height()
        ax1.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color=color3)

    # 回収率（右軸）
    ax2 = ax1.twinx()
    ax2.plot(x, summary['recovery_rate'], color=color2, marker='o', linewidth=2.5, markersize=8, label='単勝回収率 (%)')
    ax2.set_ylabel('単勝回収率 (%)', color=color2, fontsize=12, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=color2)
    ax2.set_ylim(0, 110)
    ax2.axhline(100, color='#c62828', linestyle=':', linewidth=1.5, alpha=0.8, label='回収率100%基準線')

    for i, txt in enumerate(summary['recovery_rate']):
        ax2.annotate(f'{txt:.1f}%', (x[i], summary['recovery_rate'][i]), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=9, fontweight='bold', color=color2)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', framealpha=0.95, fontsize=10)

    plt.tight_layout()
    chart1_path = os.path.join(artifact_dir, 'gap_win_rate_chart.png')
    plt.savefig(chart1_path)
    plt.close()
    print(f"Saved: {chart1_path}")

    # -------------------------------------------------------------
    # グラフ 2: AI 1位が「1番人気(本命)」 vs 「2番人気以下(穴馬)」の比較
    # -------------------------------------------------------------
    gap_bins_simple = [-0.001, 0.03, 0.06, 0.10, 1.00]
    gap_labels_simple = ['< 3%\n(接戦)', '3% - 6%', '6% - 10%\n(抜けて強い)', '10%+ \n(圧倒的1強)']
    merged['gap_simple'] = pd.cut(merged['prob_gap'], bins=gap_bins_simple, labels=gap_labels_simple)

    fav_res = []
    non_fav_res = []

    for label in gap_labels_simple:
        g_fav = merged[(merged['is_1st_favorite'] == True) & (merged['gap_simple'] == label)]
        g_non = merged[(merged['is_1st_favorite'] == False) & (merged['gap_simple'] == label)]
        
        fav_res.append(g_fav['is_win_1st'].sum() / len(g_fav) * 100 if len(g_fav) > 0 else 0)
        non_fav_res.append(g_non['is_win_1st'].sum() / len(g_non) * 100 if len(g_non) > 0 else 0)

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=130)
    x = np.arange(len(gap_labels_simple))
    width = 0.35

    rects_fav = ax.bar(x - width/2, fav_res, width, label='AI1位 ＝ 1番人気 (本命馬)', color='#c62828', alpha=0.88)
    rects_non = ax.bar(x + width/2, non_fav_res, width, label='AI1位 ＝ 2番人気以下 (穴馬)', color='#1565c0', alpha=0.88)

    ax.set_ylabel('実際の1着率 (%)', fontsize=12, fontweight='bold')
    ax.set_title('AI予測1位の「人気帯」別：ギャップと実際の1着率の関係', fontsize=14, pad=15, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(gap_labels_simple, fontsize=10)
    ax.set_ylim(0, 65)
    ax.grid(axis='y', linestyle='--', alpha=0.4)

    for rect in rects_fav:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold', color='#b71c1c')

    for rect in rects_non:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold', color='#0d47a1')

    ax.legend(loc='upper right', framealpha=0.95, fontsize=10)

    plt.tight_layout()
    chart2_path = os.path.join(artifact_dir, 'favorite_vs_ana_chart.png')
    plt.savefig(chart2_path)
    plt.close()
    print(f"Saved: {chart2_path}")

if __name__ == '__main__':
    create_gap_plots()
