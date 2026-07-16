# C:\KeibaAI\src\analysis\check_early_months.py
import sqlite3
import pandas as pd
import numpy as np

db_path = "C:/KeibaAI/predictions.db"

def run_monthly_report(df, month_name):
    if df.empty:
        print(f"[{month_name}] データが存在しません。")
        return
        
    # 前処理
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['expected_value'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    # 単勝払戻金の取得と補完
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 開催日数の取得
    unique_dates = df['kaisai_date'].nunique()

    # 条件：勝率 >= 10%, オッズ < 30倍, 期待値 >= 1.3
    selected = df[
        (df['norm_win_prob'] >= 0.1) & 
        (df['tansho_odds'] < 30.0) & 
        (df['expected_value'] >= 1.3)
    ]

    total = len(selected)
    
    print(f"\n=== 2026年{month_name}度 成績シミュレーション (EV >= 1.3) ===")
    print(f"集計期間の総データ数: {len(df)} 件")
    print(f"開催日数            : {unique_dates} 日")
    print("-" * 50)
    
    if total == 0:
        print("該当する馬はいませんでした。")
        return

    hits = selected['is_win'].sum()
    hit_rate = (hits / total) * 100
    investment = total * 100
    payout_sum = selected['payout'].sum()
    recovery_rate = (payout_sum / investment) * 100
    net_profit = payout_sum - investment
    avg_per_day = total / unique_dates

    print(f"購入頭数    : {total} 頭 (1日平均: {avg_per_day:.2f}頭)")
    print(f"的中数      : {hits} 頭")
    print(f"的中率      : {hit_rate:.1f} %")
    print(f"総投資額    : {investment:,} 円")
    print(f"総払戻額    : {int(payout_sum):,} 円")
    print(f"回収率      : {recovery_rate:.1f} %")
    print(f"純損益      : {int(net_profit):+,} 円")

def main():
    conn = sqlite3.connect(db_path)
    
    # 1月〜3月の月別データ件数確認用クエリ
    cursor = conn.cursor()
    
    months = [
        ("1月", "2026-01-01", "2026-01-31"),
        ("2月", "2026-02-01", "2026-02-28"),
        ("3月", "2026-03-01", "2026-03-31")
    ]
    
    for month_name, start_date, end_date in months:
        cursor.execute(
            "SELECT COUNT(*) FROM predictions WHERE kaisai_date >= ? AND kaisai_date <= ?", 
            (start_date, end_date)
        )
        count = cursor.fetchone()[0]
        print(f"2026年{month_name}のデータ件数: {count} 件")
        
    print("\n--- 詳細な集計処理を開始します ---")
    
    for month_name, start_date, end_date in months:
        # 該当月のデータをロード
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
        WHERE p.kaisai_date >= ? AND p.kaisai_date <= ?
        ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
        """
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
        run_monthly_report(df, month_name)
        
    conn.close()

if __name__ == '__main__':
    main()
