# C:\KeibaAI\scratch\get_today_predictions.py
import sqlite3
import pandas as pd
import numpy as np
import sys

# Windows環境での文字コード対策
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

db_path = "C:/KeibaAI/predictions.db"

# JRA競馬場コードマップ
place_code_map = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
    '05': '東京', '06': '中山', '07': '中京', '08': '京都',
    '09': '阪神', '10': '小倉'
}

def get_keibajo_name(race_id):
    if not race_id or len(str(race_id)) < 8:
        return "不明"
    # race_idの5〜6桁目が競馬場コード
    code = str(race_id)[4:6]
    return place_code_map.get(code, f"地方/他({code})")

def main():
    conn = sqlite3.connect(db_path)
    
    # 今日の日付 (2026-06-06)
    target_date = "2026-06-06"
    
    query = """
    SELECT 
        race_id,
        kaisai_date,
        race_number,
        umaban,
        horse_name,
        pred_win,
        pred_rank,
        tansho_odds
    FROM predictions
    WHERE kaisai_date = ?
    ORDER BY race_id ASC, umaban ASC
    """
    df = pd.read_sql_query(query, conn, params=(target_date,))
    conn.close()

    if df.empty:
        print(f"{target_date} のデータが predictions テーブルに見つかりません。")
        return

    # 予測勝率のノーマライズ (レース内の合計を1.0にする)
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_pred_win'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    
    # 単勝期待値の計算 (オッズがNoneの場合はNaN)
    df['win_ev'] = df['norm_pred_win'] * df['tansho_odds'].astype(float)

    # 条件：予測1位 かつ 補正後勝率 15%以上
    target_horses = df[
        (df['pred_rank'] == 1) & 
        (df['norm_pred_win'] >= 0.15)
    ].copy()

    print(f"\n--- 【解析版】{target_date} の予測1位 ＆ 勝率15%以上の馬一覧 ---")
    if target_horses.empty:
        print("該当する馬はいませんでした。")
        return

    for idx, row in target_horses.iterrows():
        race_id = row['race_id']
        keibajo = get_keibajo_name(race_id)
        
        # オッズがNoneの場合の表示対策
        odds = row['tansho_odds']
        odds_str = f"{float(odds):4.1f}倍" if odds is not None and not pd.isna(odds) else "未取得"
        
        win_ev = row['win_ev']
        ev_str = f"{win_ev:.2f}" if win_ev is not None and not pd.isna(win_ev) else "計算不可"
        
        prob_pct = row['norm_pred_win'] * 100
        
        print(
            f"ID: {race_id} | {keibajo} {int(row['race_number']):2d}R | "
            f"馬番: {int(row['umaban']):2d} | "
            f"予測勝率: {prob_pct:4.1f}% | "
            f"単勝オッズ: {odds_str} | "
            f"期待値: {ev_str}"
        )

if __name__ == '__main__':
    main()
