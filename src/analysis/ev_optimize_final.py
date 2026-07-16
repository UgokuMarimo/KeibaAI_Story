# C:\KeibaAI\src\analysis\ev_optimize_final.py
import sqlite3
import pandas as pd
import numpy as np

db_path = "C:/KeibaAI/predictions.db"

def run_horses_limit_simulation(df_filtered, min_horses):
    # 出走頭数フィルターの適用
    df_target = df_filtered[df_filtered['出走頭数'] >= min_horses].copy()
    
    # --- 期待値最高1頭買い ---
    grouped = df_target.groupby('race_id')
    selected_single_list = []
    for race_id, group in grouped:
        best_horse = group.sort_values(by='win_ev', ascending=False).iloc[0]
        selected_single_list.append(best_horse)
        
    if selected_single_list:
        selected_single = pd.DataFrame(selected_single_list)
        total_single = len(selected_single)
        hits_single = selected_single['is_win'].sum()
        hit_rate_single = hits_single / total_single * 100
        invest_single = total_single * 100
        payout_single = selected_single['payout'].sum()
        rec_single = payout_single / invest_single * 100
        profit_single = payout_single - invest_single
    else:
        total_single, hits_single, hit_rate_single, invest_single, payout_single, rec_single, profit_single = 0, 0, 0.0, 0, 0.0, 0.0, 0.0

    return {
        'total': total_single,
        'hits': hits_single,
        'hit_rate': hit_rate_single,
        'recovery': rec_single,
        'profit': profit_single
    }

def main():
    # 1. データの読み込み (出走頭数は含まない)
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
        pay.tansho_payout
    FROM predictions p
    JOIN payouts pay ON p.race_id = pay.race_id
    ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("データが見つかりませんでした。")
        return

    # 2. 前処理
    # 出走頭数を race_id ごとのデータの件数からカウント
    df['出走頭数'] = df.groupby('race_id')['umaban'].transform('count')
    
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['win_ev'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 最強ベースフィルター (勝率10%以上、オッズ30倍以下、期待値 1.3 以上 3.0 未満)
    df_filtered = df[
        (df['norm_win_prob'] >= 0.1) & 
        (df['tansho_odds'] < 30.0) & 
        (df['win_ev'] >= 1.3) & 
        (df['win_ev'] < 3.0)
    ].copy()

    # 検証する最低頭数しきい値
    min_horses_list = [0, 8, 10, 12, 13, 14, 15]

    print("=== FINAL OPTIMIZATION (EV: 1.3-3.0, WinProb >= 10% & Odds < 30x, 1頭制限) ===")
    print("-" * 80)
    print("{:<15} | {:<10} | {:<8} | {:<10} | {:<10} | {:<12}".format(
        "最低頭数制限", "購入点数", "的中数", "的中率", "回収率", "純利益"
    ))
    print("-" * 80)

    for min_h in min_horses_list:
        res = run_horses_limit_simulation(df_filtered, min_h)
        label = "制限なし" if min_h == 0 else f"{min_h}頭以上"
        print("{:<15} | {:<10} | {:<8} | {:<9.1f}% | {:<9.1f}% | {:<+12,.0f}円".format(
            label, res['total'], res['hits'], res['hit_rate'], res['recovery'], res['profit']
        ))

if __name__ == '__main__':
    main()
