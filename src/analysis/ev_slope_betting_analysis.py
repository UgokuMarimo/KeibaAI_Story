# C:\KeibaAI\src\analysis\ev_slope_betting_analysis.py
import sqlite3
import pandas as pd
import numpy as np

db_path = "C:/KeibaAI/predictions.db"

def get_bet_amount(ev, pattern):
    if pattern == 'equal':
        return 100
    elif pattern == 'pattern_a': # 3段階
        if ev < 1.8: return 100
        elif ev < 2.4: return 300
        else: return 500
    elif pattern == 'pattern_b': # 4段階
        if ev < 1.7: return 100
        elif ev < 2.1: return 200
        elif ev < 2.5: return 300
        else: return 500
    elif pattern == 'pattern_c': # 5段階
        if ev < 1.5: return 100
        elif ev < 1.8: return 200
        elif ev < 2.1: return 300
        elif ev < 2.5: return 400
        else: return 500
    return 100

def run_simulation(df_filtered, is_single, pattern):
    df_target = df_filtered.copy()
    
    if is_single:
        # 1レースあたり期待値最高1頭のみ選出
        grouped = df_target.groupby('race_id')
        selected_list = []
        for race_id, group in grouped:
            best_horse = group.sort_values(by='win_ev', ascending=False).iloc[0]
            selected_list.append(best_horse)
        if selected_list:
            df_bet = pd.DataFrame(selected_list)
        else:
            df_bet = pd.DataFrame()
    else:
        # 条件馬全頭購入
        df_bet = df_target

    if df_bet.empty:
        return 0, 0, 0.0, 0, 0.0, 0.0, 0.0

    # 傾斜金額を算出
    df_bet['bet_amount'] = df_bet['win_ev'].apply(lambda x: get_bet_amount(x, pattern))
    
    # 投資額
    total_invest = df_bet['bet_amount'].sum()
    
    # 払戻金（的中馬のみ、bet_amount の比率で乗算）
    df_bet['actual_payout'] = np.where(
        df_bet['is_win'] == 1,
        df_bet['payout'] * (df_bet['bet_amount'] / 100.0),
        0.0
    )
    total_payout = df_bet['actual_payout'].sum()
    
    # 各種指標
    total_bets = len(df_bet)
    hits = df_bet['is_win'].sum()
    hit_rate = hits / total_bets * 100
    rec_rate = total_payout / total_invest * 100
    profit = total_payout - total_invest
    
    return total_bets, hits, hit_rate, total_invest, total_payout, rec_rate, profit

def main():
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

    # 前処理
    df['出走頭数'] = df.groupby('race_id')['umaban'].transform('count')
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['win_ev'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 黄金ルールフィルター (勝率10%以上、オッズ30倍以下、期待値 1.3 以上 3.0 未満、出走頭数10頭以上)
    df_filtered = df[
        (df['出走頭数'] >= 10) &
        (df['norm_win_prob'] >= 0.1) & 
        (df['tansho_odds'] < 30.0) & 
        (df['win_ev'] >= 1.3) & 
        (df['win_ev'] < 3.0)
    ].copy()

    patterns = ['equal', 'pattern_a', 'pattern_b', 'pattern_c']
    pattern_names = {
        'equal': '【均等買い】一律100円',
        'pattern_a': '【傾斜A (3段階)】1.3~1.8:100 / 1.8~2.4:300 / 2.4~3.0:500',
        'pattern_b': '【傾斜B (4段階)】1.3~1.7:100 / 1.7~2.1:200 / 2.1~2.5:300 / 2.5~3.0:500',
        'pattern_c': '【傾斜C (5段階)】1.3~1.5:100 / 1.5~1.8:200 / 1.8~2.1:300 / 2.1~2.5:400 / 2.5~3.0:500'
    }

    print("=== 傾斜ベッティング シミュレーション結果 ===")
    print("-" * 100)
    print(" 1. 【条件馬 全頭購入】")
    print("-" * 100)
    for p in patterns:
        tb, h, hr, ti, tp, rr, pr = run_simulation(df_filtered, is_single=False, pattern=p)
        print(f"{pattern_names[p]:<60} | 購入:{tb}頭 | 的中:{h}頭 ({hr:.1f}%) | 投資:{ti:,}円 | 払戻:{tp:,.0f}円 | 回収:{rr:.1f}% | 利益:{pr:+,.0f}円")
        
    print("\n" + "-" * 100)
    print(" 2. 【1レース1頭制限】")
    print("-" * 100)
    for p in patterns:
        tb, h, hr, ti, tp, rr, pr = run_simulation(df_filtered, is_single=True, pattern=p)
        print(f"{pattern_names[p]:<60} | 購入:{tb}頭 | 的中:{h}頭 ({hr:.1f}%) | 投資:{ti:,}円 | 払戻:{tp:,.0f}円 | 回収:{rr:.1f}% | 利益:{pr:+,.0f}円")

if __name__ == '__main__':
    main()
