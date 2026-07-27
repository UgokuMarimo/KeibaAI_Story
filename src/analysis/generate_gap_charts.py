import os
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl

# 日本語フォント設定
mpl.rcParams['font.family'] = ['Meiryo', 'Yu Gothic', 'MS Gothic', 'sans-serif']
mpl.rcParams['axes.unicode_minus'] = False

# 保存先設定
OUTPUT_DIR = r"C:\side_job\public\images\articles\003"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DB_PATH = r"C:\keibaAI\data\db\predictions.db"

def load_data():
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT race_id, umaban, horse_name, pred_win, pred_rank, tansho_odds, tansho_ninki, result_rank
    FROM predictions
    WHERE result_rank IS NOT NULL AND result_rank > 0
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 勝率のグループ毎正規化
    df['pred_win_prob'] = df.groupby('race_id')['pred_win'].transform(
        lambda x: (x / x.sum() * 100.0) if x.sum() > 0 else 0.0
    )

    # 1位と2位のギャップ計算
    race_gaps = []
    for race_id, r_df in df.groupby('race_id'):
        r_df_sorted = r_df.sort_values(by='pred_win_prob', ascending=False)
        if len(r_df_sorted) >= 2:
            p1 = r_df_sorted.iloc[0]['pred_win_prob']
            p2 = r_df_sorted.iloc[1]['pred_win_prob']
            gap = p1 - p2
        else:
            gap = 0.0

        r_df_top1 = r_df_sorted.iloc[0].copy()
        r_df_top1['gap'] = gap
        race_gaps.append(r_df_top1)

    df_top1 = pd.DataFrame(race_gaps)
    return df_top1


def plot_chart1_overall(df_top1):
    bins = [-1, 3, 6, 10, 15, 20, 100]
    labels = ['<3%', '3-6%', '6-10%', '10-15%', '15-20%', '20%+']
    df_top1['gap_cat'] = pd.cut(df_top1['gap'], bins=bins, labels=labels)

    stats = df_top1.groupby('gap_cat', observed=False).apply(lambda g: pd.Series({
        'win_rate': (g['result_rank'] == 1).mean() * 100.0,
        'place_rate': (g['result_rank'] <= 3).mean() * 100.0,
        'count': len(g)
    })).reset_index()

    fig, ax1 = plt.subplots(figsize=(9, 5), dpi=150)
    fig.patch.set_facecolor('#f8faf8')
    ax1.set_facecolor('#ffffff')

    colors = ['#2d6a4f' if i < 3 else '#1b4332' for i in range(len(stats))]
    bars = ax1.bar(stats['gap_cat'], stats['win_rate'], color=colors, alpha=0.85, width=0.55, label='1着 的中率 (%)', edgecolor='#1b4332')

    # 数値ラベル
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f'{height:.1f}%',
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3),  # 3 points vertical offset
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=10, fontweight='bold', color='#1b4332')

    # 複勝率の折れ線
    ax2 = ax1.twinx()
    line = ax2.plot(stats['gap_cat'], stats['place_rate'], color='#e63946', marker='o', linewidth=2.5, markersize=8, label='複勝率 (1~3着 %)')
    for i, txt in enumerate(stats['place_rate']):
        ax2.annotate(f'{txt:.1f}%', (stats['gap_cat'][i], txt), textcoords="offset points", xytext=(0,7), ha='center', fontsize=9, fontweight='bold', color='#e63946')

    ax1.set_title('勝率ギャップ（1位 - 2位）と実際の1着的中率・複勝率の推移', fontsize=13, fontweight='bold', pad=15, color='#1b4332')
    ax1.set_xlabel('予測1位と2位の勝率差 (勝率ギャップ)', fontsize=10, fontweight='bold', labelpad=10)
    ax1.set_ylabel('1着 的中率 (%)', fontsize=10, fontweight='bold', color='#1b4332')
    ax2.set_ylabel('複勝率 (%)', fontsize=10, fontweight='bold', color='#e63946')
    ax1.set_ylim(0, 45)
    ax2.set_ylim(30, 90)

    ax1.grid(axis='y', linestyle='--', alpha=0.3)

    # 凡例統合
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, 'chart1_overall_trend.png')
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[SUCCESS] Saved chart 1 to {out_path}")


def plot_chart2_favorite(df_top1):
    df_fav = df_top1[df_top1['tansho_ninki'] == 1].copy()

    bins = [-1, 3, 6, 10, 100]
    labels = ['< 3% (接戦)', '3% ～ 6%', '6% ～ 10% (黄金ゾーン)', '10%+ (圧倒一強)']
    df_fav['gap_cat'] = pd.cut(df_fav['gap'], bins=bins, labels=labels)

    stats = df_fav.groupby('gap_cat', observed=False).apply(lambda g: pd.Series({
        'win_rate': (g['result_rank'] == 1).mean() * 100.0,
        'place_rate': (g['result_rank'] <= 3).mean() * 100.0,
        'recovery': (g[g['result_rank'] == 1]['tansho_odds'].sum() / len(g) * 100.0) if len(g) > 0 else 0.0
    })).reset_index()

    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    fig.patch.set_facecolor('#f8faf8')
    ax.set_facecolor('#ffffff')

    x = np.arange(len(stats))
    width = 0.35

    # カラー指定 (6-10% を金/ハイライト)
    win_colors = ['#2d6a4f', '#2d6a4f', '#d4af37', '#1b4332']
    place_colors = ['#74c69d', '#74c69d', '#f3a683', '#52b788']

    rects1 = ax.bar(x - width/2, stats['win_rate'], width, label='1着 的中率 (%)', color=win_colors, edgecolor='#1b4332')
    rects2 = ax.bar(x + width/2, stats['place_rate'], width, label='複勝率 (1~3着 %)', color=place_colors, edgecolor='#1b4332', alpha=0.85)

    for rect in rects1:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#1b4332')

    for rect in rects2:
        height = rect.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold', color='#d9480f')

    ax.set_title('AI予測1位 ＝ 単勝1番人気（本命）時の勝率ギャップ別成績 (鉄板法則)', fontsize=13, fontweight='bold', pad=15, color='#1b4332')
    ax.set_xticks(x)
    ax.set_xticklabels(stats['gap_cat'], fontsize=10, fontweight='bold')
    ax.set_ylabel('確率は (%)', fontsize=10, fontweight='bold')
    ax.set_ylim(0, 95)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    ax.legend(loc='upper left', frameon=True, facecolor='white')

    # ハイライト注釈
    ax.annotate('★勝率53.1% / 複勝率78.1%！\n最高の鉄板軸馬ゾーン',
                xy=(2 - width/2, 53.1), xytext=(1.5, 72),
                arrowprops=dict(facecolor='#d4af37', shrink=0.08, width=2, headwidth=8),
                fontsize=10, fontweight='bold', color='#b45309',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#fffbe6', edgecolor='#d4af37', alpha=0.9))

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, 'chart2_favorite_ironclad.png')
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[SUCCESS] Saved chart 2 to {out_path}")


def plot_chart3_hole(df_top1):
    df_hole = df_top1[df_top1['tansho_ninki'] >= 2].copy()

    bins = [-1, 3, 6, 10, 100]
    labels = ['< 3% (接戦狙い目)', '3% ～ 6%', '6% ～ 10%', '10%+ (過大評価の罠)']
    df_hole['gap_cat'] = pd.cut(df_hole['gap'], bins=bins, labels=labels)

    stats = df_hole.groupby('gap_cat', observed=False).apply(lambda g: pd.Series({
        'win_rate': (g['result_rank'] == 1).mean() * 100.0,
        'recovery': (g[g['result_rank'] == 1]['tansho_odds'].sum() / len(g) * 100.0) if len(g) > 0 else 0.0
    })).reset_index()

    fig, ax1 = plt.subplots(figsize=(9, 5), dpi=150)
    fig.patch.set_facecolor('#f8faf8')
    ax1.set_facecolor('#ffffff')

    x = np.arange(len(stats))
    width = 0.4

    rects1 = ax1.bar(x, stats['recovery'], width, color=['#2b8a3e', '#74b816', '#f59f00', '#e03131'], edgecolor='#1b4332', alpha=0.85, label='単勝回収率 (%)')

    for rect in rects1:
        height = rect.get_height()
        ax1.annotate(f'{height:.1f}%',
                     xy=(rect.get_x() + rect.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points",
                     ha='center', va='bottom', fontsize=10, fontweight='bold', color='#1b4332')

    ax1.set_title('AI予測1位 ＝ 単勝2番人気以下（穴馬）時の勝率ギャップ別回収率 (罠と狙い目)', fontsize=13, fontweight='bold', pad=15, color='#1b4332')
    ax1.set_xticks(x)
    ax1.set_xticklabels(stats['gap_cat'], fontsize=10, fontweight='bold')
    ax1.set_ylabel('単勝回収率 (%)', fontsize=10, fontweight='bold', color='#2b8a3e')
    ax1.axhline(100, color='#e63946', linestyle='--', linewidth=1.5, label='回収率 100%ライン')
    ax1.set_ylim(0, 105)
    ax1.grid(axis='y', linestyle='--', alpha=0.3)
    ax1.legend(loc='upper right', frameon=True, facecolor='white')

    # 注釈
    ax1.annotate('接戦（ギャップ<3%）の穴馬が\n最高回収率 80.9%！',
                xy=(0, 80.9), xytext=(0.4, 90),
                arrowprops=dict(facecolor='#2b8a3e', shrink=0.08, width=2, headwidth=8),
                fontsize=9, fontweight='bold', color='#2b8a3e',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#ebfbee', edgecolor='#2b8a3e', alpha=0.9))

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, 'chart3_hole_trap_and_sweetspot.png')
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"[SUCCESS] Saved chart 3 to {out_path}")


if __name__ == '__main__':
    print("Generating gap analysis charts...")
    df_top1 = load_data()
    plot_chart1_overall(df_top1)
    plot_chart2_favorite(df_top1)
    plot_chart3_hole(df_top1)
    print("All charts generated successfully!")
