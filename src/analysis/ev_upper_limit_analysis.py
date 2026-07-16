# C:\KeibaAI\src\analysis\ev_upper_limit_analysis.py
import sqlite3
import pandas as pd
import numpy as np

db_path = "C:/KeibaAI/predictions.db"

def run_limit_simulation(df_filtered, ev_lower, ev_upper=None):
    # 上限フィルター適用
    if ev_upper is not None:
        df_target = df_filtered[(df_filtered['win_ev'] >= ev_lower) & (df_filtered['win_ev'] < ev_upper)].copy()
    else:
        df_target = df_filtered[df_filtered['win_ev'] >= ev_lower].copy()
        
    # --- 【A】全頭買い ---
    total_all = len(df_target)
    if total_all > 0:
        hits_all = df_target['is_win'].sum()
        hit_rate_all = hits_all / total_all * 100
        invest_all = total_all * 100
        payout_all = df_target['payout'].sum()
        rec_all = payout_all / invest_all * 100
        profit_all = payout_all - invest_all
    else:
        hits_all, hit_rate_all, invest_all, payout_all, rec_all, profit_all = 0, 0.0, 0, 0.0, 0.0, 0.0

    # --- 【B】最高EV1頭買い ---
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
        'all': {'total': total_all, 'hits': hits_all, 'hit_rate': hit_rate_all, 'recovery': rec_all, 'profit': profit_all},
        'single': {'total': total_single, 'hits': hits_single, 'hit_rate': hit_rate_single, 'recovery': rec_single, 'profit': profit_single}
    }

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
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['win_ev'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 基本フィルター (勝率10%以上、オッズ30倍以下)
    df_filtered = df[(df['norm_win_prob'] >= 0.1) & (df['tansho_odds'] < 30.0)].copy()

    # 期待値下限
    ev_lower = 1.3
    # 期待値上限の検証パターン
    upper_limits = [None, 3.0, 2.5, 2.0, 1.8, 1.6, 1.5]

    print("=== EV UPPER LIMIT SIMULATION (EV Lower >= 1.3, WinProb >= 10% & Odds < 30x) ===")
    print("-" * 85)
    print("{:<10} | {:<32} | {:<32}".format("EV上限", "【A】全頭買い", "【B】期待値最高1頭のみ買い"))
    print("-" * 85)

    for lim in upper_limits:
        res = run_limit_simulation(df_filtered, ev_lower, lim)
        lim_str = "上限なし" if lim is None else f"EV < {lim:.1f}"
        
        all_str = f"{res['all']['total']}点/{res['all']['hit_rate']:.1f}%/{res['all']['recovery']:.1f}% ({res['all']['profit']:+,.0f}円)"
        single_str = f"{res['single']['total']}点/{res['single']['hit_rate']:.1f}%/{res['single']['recovery']:.1f}% ({res['single']['profit']:+,.0f}円)"
        
        print("{:<10} | {:<32} | {:<32}".format(
            lim_str, all_str, single_str
        ))

if __name__ == '__main__':
    main()
