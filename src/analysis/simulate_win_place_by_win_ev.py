# C:\KeibaAI\scratch\simulate_win_place_by_win_ev.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# パス設定
db_path = "C:/KeibaAI/predictions.db"
save_img_path = "C:/KeibaAI/data/odds_history/win_place_by_win_ev_simulation.png"

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
        p.tansho_odds,
        p.result_rank,
        pay.tansho_payout,
        pay.fukusho_payouts
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

    # 2. レースごとの予測勝率（pred_win）のノーマライズ（合計が1.0になるように調整）
    # レースごとの pred_win の合計を計算
    race_prob_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_pred_win'] = df['pred_win'] / np.where(race_prob_sums > 0, race_prob_sums, 1.0)

    # ノーマライズした期待値（Norm Win EV）の計算
    df['win_ev'] = df['norm_pred_win'] * df['tansho_odds']

    # 3. 実際の単勝・複勝払戻金の整理
    # 単勝払戻金：1着なら tansho_payout、それ以外は 0
    df['win_payout'] = np.where(df['result_rank'] == 1, df['tansho_payout'], 0.0)
    df['win_payout'] = np.where((df['result_rank'] == 1) & (df['win_payout'] <= 0), df['tansho_odds'] * 100, df['win_payout'])

    # 複勝払戻金の取得
    def get_fukusho_payout(row):
        try:
            payouts_dict = json.loads(row['fukusho_payouts'])
            umaban_str = str(row['umaban'])
            if umaban_str in payouts_dict:
                return float(payouts_dict[umaban_str])
            else:
                return 0.0
        except Exception:
            if row['result_rank'] in [1, 2, 3]:
                return max(110.0, (0.08 * row['tansho_odds'] + 1.0) * 100)
            return 0.0

    df['place_payout'] = df.apply(get_fukusho_payout, axis=1)

    # 4. フィルター適用：単勝30倍以下
    df_filtered = df[df['tansho_odds'] <= 30.0].copy().reset_index(drop=True)
    print(f"Filtered to {len(df_filtered)} predictions (Tansho Odds <= 30.0).")

    # しきい値
    thresholds = [1.0, 1.1, 1.2, 1.3]

    # プロット用の設定
    plt.figure(figsize=(12, 8))
    plt.rcParams['font.family'] = 'MS Gothic'
    plt.rcParams['axes.unicode_minus'] = False

    # 色の定義（単勝は暖色系、複勝は寒色系）
    colors_win = {1.0: '#ff7f0e', 1.1: '#d62728', 1.2: '#9467bd', 1.3: '#d62728'} # 色調のバリエーション
    colors_place = {1.0: '#1f77b4', 1.1: '#2ca02c', 1.2: '#17becf', 1.3: '#2ca02c'}
    
    # より鮮明な色の組み合わせに変更
    color_map = {
        1.0: {'win': '#ff9896', 'place': '#aec7e8'},  # 薄めの赤・青
        1.1: {'win': '#ff7f0e', 'place': '#1f77b4'},  # オレンジ・青
        1.2: {'win': '#d62728', 'place': '#2ca02c'},  # 赤・緑
        1.3: {'win': '#9467bd', 'place': '#98df8a'}   # 紫・薄緑
    }

    print("\n--- シミュレーション結果 (単勝30倍以下・勝率ノーマライズ適用後) ---")

    # 単勝ベタ買い (比較用)
    df_filtered['win_profit_all'] = df_filtered['win_payout'] - 100
    cum_win_all = df_filtered['win_profit_all'].cumsum()
    plt.plot(cum_win_all, label='単勝 ベタ買い (回収率: {:.1f}%)'.format((df_filtered['win_payout'].sum() / (len(df_filtered) * 100)) * 100), color='#7f7f7f', alpha=0.6, linestyle='--')
    win_all_rec = (df_filtered['win_payout'].sum() / (len(df_filtered) * 100)) * 100
    win_all_hit = (df_filtered['win_payout'] > 0).mean() * 100
    print(f"【単勝ベタ買い】購入点数={len(df_filtered):,}点, 的中率={win_all_hit:.1f}%, 回収率={win_all_rec:.2f}%")

    # 複勝ベタ買い (比較用)
    df_filtered['place_profit_all'] = df_filtered['place_payout'] - 100
    cum_place_all = df_filtered['place_profit_all'].cumsum()
    plt.plot(cum_place_all, label='複勝 ベタ買い (回収率: {:.1f}%)'.format((df_filtered['place_payout'].sum() / (len(df_filtered) * 100)) * 100), color='#bcbd22', alpha=0.4, linestyle=':')
    place_all_rec = (df_filtered['place_payout'].sum() / (len(df_filtered) * 100)) * 100
    place_all_hit = (df_filtered['place_payout'] > 0).mean() * 100
    print(f"【複勝ベタ買い】購入点数={len(df_filtered):,}点, 的中率={place_all_hit:.1f}%, 回収率={place_all_rec:.2f}%")

    for th in thresholds:
        selected = df_filtered[df_filtered['win_ev'] >= th].copy()
        
        if selected.empty:
            print(f"しきい値 Win EV >= {th:.1f}: 対象馬なし")
            continue

        total_bets = len(selected)
        
        # --- 単勝シミュレーション ---
        selected['win_profit'] = selected['win_payout'] - 100
        cum_win = selected['win_profit'].cumsum().reset_index(drop=True)
        win_hit_rate = (selected['win_payout'] > 0).mean() * 100
        win_rec_rate = (selected['win_payout'].sum() / (total_bets * 100)) * 100
        win_profit_sum = selected['win_profit'].sum()

        # --- 複勝シミュレーション ---
        selected['place_profit'] = selected['place_payout'] - 100
        cum_place = selected['place_profit'].cumsum().reset_index(drop=True)
        place_hit_rate = (selected['place_payout'] > 0).mean() * 100
        place_rec_rate = (selected['place_payout'].sum() / (total_bets * 100)) * 100
        place_profit_sum = selected['place_profit'].sum()

        print(f"\n[しきい値 Win EV >= {th:.1f}] 購入点数={total_bets:,}点")
        print(f"  単勝 -> 的中率={win_hit_rate:.1f}%, 回収率={win_rec_rate:.2f}%, 純利益={win_profit_sum:+,.0f}円")
        print(f"  複勝 -> 的中率={place_hit_rate:.1f}%, 回収率={place_rec_rate:.2f}%, 純利益={place_profit_sum:+,.0f}円")

        # プロット
        plt.plot(cum_win, label=f"単勝 EV >= {th:.1f} (回収率: {win_rec_rate:.1f}%)", color=color_map[th]['win'], linewidth=2.5)
        plt.plot(cum_place, label=f"複勝 EV >= {th:.1f} (回収率: {place_rec_rate:.1f}%)", color=color_map[th]['place'], linewidth=2.0, linestyle='-.')

    plt.title("単勝期待値（Win EV / 正規化済）基準の単勝・複勝回収率シミュレーション (単勝30倍以下)", fontsize=14, fontweight='bold')
    plt.xlabel("購入レース数 (累計)", fontsize=12)
    plt.ylabel("累積純損益 (円, 1点100円購入時)", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.axhline(0, color='black', linestyle='-', alpha=0.5)
    plt.legend(loc='upper left', fontsize=10, ncol=2)

    os.makedirs(os.path.dirname(save_img_path), exist_ok=True)
    plt.savefig(save_img_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\nSimulation plot saved to {save_img_path}")

if __name__ == "__main__":
    main()
