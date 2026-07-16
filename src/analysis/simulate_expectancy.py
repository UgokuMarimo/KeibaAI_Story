import sqlite3
import pandas as pd
import numpy as np

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    conn = sqlite3.connect('predictions.db')
    
    # 必要なデータをpredictionsから取得
    # 結果が確定しており、オッズが存在するレコード
    query = """
    SELECT race_id, umaban, pred_win, tansho_odds, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0 AND tansho_odds IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("データが存在しません。")
        return
        
    print(f"ロードされた総レコード数: {len(df)} 件")
    
    # レースごとにpred_winを正規化して、真の勝率(win_prob_normalized)を算出する
    # 各レースのpred_winの総和を計算
    sum_pred = df.groupby('race_id')['pred_win'].transform('sum')
    df['win_prob'] = df['pred_win'] / sum_pred
    
    # 期待値の計算 (勝率 * オッズ)
    df['expected_value'] = df['win_prob'] * df['tansho_odds']
    
    # 1着判定
    df['is_winner'] = (df['result_rank'] == 1).astype(int)
    
    # 的中した時の払い戻し (オッズ * 100円)
    df['payout'] = df['is_winner'] * df['tansho_odds'] * 100
    
    # グリッドサーチの設定
    # 最低勝率閾値: 5% から 25% まで 1% 刻み
    prob_thresholds = np.arange(0.05, 0.26, 0.01)
    # 最低期待値閾値: 1.0 から 2.0 まで 0.05 刻み
    ev_thresholds = np.arange(1.0, 2.05, 0.05)
    
    results = []
    
    for p_min in prob_thresholds:
        for ev_min in ev_thresholds:
            # 条件に合致する馬を抽出（条件を満たす馬すべてを購入）
            selected = df[(df['win_prob'] >= p_min) & (df['expected_value'] >= ev_min)]
            
            total_bets = len(selected)
            if total_bets == 0:
                continue
                
            hits = selected['is_winner'].sum()
            hit_rate = hits / total_bets
            
            total_investment = total_bets * 100
            total_payout = selected['payout'].sum()
            recovery_rate = total_payout / total_investment
            
            # ユニークなレース数
            unique_races = selected['race_id'].nunique()
            
            results.append({
                'p_min': p_min,
                'ev_min': ev_min,
                'total_bets': total_bets,
                'hits': hits,
                'hit_rate': hit_rate,
                'recovery_rate': recovery_rate,
                'unique_races': unique_races
            })
            
    res_df = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("🏆 【単勝期待値シミュレーション】最適な設定の探索 (全合致馬購入ルール)")
    print("="*80)
    
    # 試行回数（購入馬数）が一定以上（例: 100回以上、データ全体の約3%以上）の中で、回収率が高い順にソート
    min_bets = 100
    filtered_res = res_df[res_df['total_bets'] >= min_bets]
    
    if filtered_res.empty:
        print(f"購入回数が {min_bets} 回以上の条件が見つかりませんでした。制限を緩和します。")
        filtered_res = res_df[res_df['total_bets'] >= 20]
        
    top_recovery = filtered_res.sort_values(by='recovery_rate', ascending=False).head(10)
    
    print(f"\n📈 回収率トップ10の条件（購入馬数 {min_bets}回以上）:")
    for idx, row in top_recovery.iterrows():
        print(f"順位: 最低勝率 {row['p_min']:.0%} | 最低期待値 {row['ev_min']:.2f} "
              f"➔ 回収率: {row['recovery_rate']:.2%} | 的中率: {row['hit_rate']:.2%} "
              f"(購入数: {int(row['total_bets'])}回 / 的中: {int(row['hits'])}回 / 対象レース: {int(row['unique_races'])}レース)")
        
    # 現在の設定 (勝率 9%以上、期待値 1.2以上) の結果を表示
    current_setting = res_df[(np.isclose(res_df['p_min'], 0.09)) & (np.isclose(res_df['ev_min'], 1.2))]
    if not current_setting.empty:
        row = current_setting.iloc[0]
        print("\n" + "-"*80)
        print("📌 【現在の設定（最低勝率 9% 以上、最低期待値 1.2 以上）の実績】")
        print(f"  - 回収率: {row['recovery_rate']:.2%}")
        print(f"  - 的中率: {row['hit_rate']:.2%}")
        print(f"  - 購入数: {int(row['total_bets'])}回 (的中: {int(row['hits'])}回 / 対象レース: {int(row['unique_races'])}レース)")
        print("-"*80)
        
    # 別の購入ルール: 「各レースで期待値が最も高く、かつ閾値を満たす1頭のみを購入」
    results_best_only = []
    
    # レースごとに期待値最大の馬を特定しておく
    idx_max_ev = df.groupby('race_id')['expected_value'].idxmax()
    df_best_only = df.loc[idx_max_ev]
    
    for p_min in prob_thresholds:
        for ev_min in ev_thresholds:
            # 期待値最大の馬のうち、閾値を満たすものを購入
            selected = df_best_only[(df_best_only['win_prob'] >= p_min) & (df_best_only['expected_value'] >= ev_min)]
            
            total_bets = len(selected)
            if total_bets == 0:
                continue
                
            hits = selected['is_winner'].sum()
            hit_rate = hits / total_bets
            
            total_investment = total_bets * 100
            total_payout = selected['payout'].sum()
            recovery_rate = total_payout / total_investment
            
            results_best_only.append({
                'p_min': p_min,
                'ev_min': ev_min,
                'total_bets': total_bets,
                'hits': hits,
                'hit_rate': hit_rate,
                'recovery_rate': recovery_rate,
                'unique_races': total_bets  # 1レース最大1頭なので、購入回数＝ユニークレース数
            })
            
    res_best_df = pd.DataFrame(results_best_only)
    
    print("\n" + "="*80)
    print("🏆 【単勝期待値シミュレーション】最適な設定の探索 (各レース期待値最大「1頭のみ」購入ルール)")
    print("="*80)
    
    filtered_best_res = res_best_df[res_best_df['total_bets'] >= 50] # 1頭のみなので閾値を少し下げる
    if filtered_best_res.empty:
        filtered_best_res = res_best_df[res_best_df['total_bets'] >= 10]
        
    top_recovery_best = filtered_best_res.sort_values(by='recovery_rate', ascending=False).head(10)
    
    print(f"\n📈 回収率トップ10の条件（購入馬数 50回以上）:")
    for idx, row in top_recovery_best.iterrows():
        print(f"順位: 最低勝率 {row['p_min']:.0%} | 最低期待値 {row['ev_min']:.2f} "
              f"➔ 回収率: {row['recovery_rate']:.2%} | 的中率: {row['hit_rate']:.2%} "
              f"(購入数: {int(row['total_bets'])}回 / 的中: {int(row['hits'])}回)")
              
    current_setting_best = res_best_df[(np.isclose(res_best_df['p_min'], 0.09)) & (np.isclose(res_best_df['ev_min'], 1.2))]
    if not current_setting_best.empty:
        row = current_setting_best.iloc[0]
        print("\n" + "-"*80)
        print("📌 【現在の設定（最低勝率 9% 以上、最低期待値 1.2 以上）の実績 (期待値最大1頭)】")
        print(f"  - 回収率: {row['recovery_rate']:.2%}")
        print(f"  - 的中率: {row['hit_rate']:.2%}")
        print(f"  - 購入数: {int(row['total_bets'])}回 (的中: {int(row['hits'])}回)")
        print("-"*80)

if __name__ == '__main__':
    main()
