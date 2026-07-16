# C:\KeibaAI\src\analysis\ev_comparison_single_vs_all.py
import sqlite3
import json
import pandas as pd
import numpy as np
import urllib.request
import sys

# Windows環境でのコンソール文字コード対策
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

db_path = "C:/KeibaAI/predictions.db"
webhook_url = "https://discordapp.com/api/webhooks/1513097156091711538/0RoI66LGE-rw2M3D9dlmaG22Tl8TWO12WBCRUqufAwwkWCzuGh7XgxG9yYn9WKfGAqdh"

def send_discord_message(content):
    payload = {"content": content}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    
    req = urllib.request.Request(
        webhook_url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers=headers, 
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            if response.status in [200, 204]:
                print("Discordへの送信が成功しました。")
            else:
                print(f"送信ステータス: {response.status}")
    except Exception as e:
        print(f"送信エラー: {e}")

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

    print(f"Loaded {len(df)} predictions from DB.")

    # 2. 前処理
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    df['win_ev'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 基本フィルター (勝率10%以上、オッズ30倍以下)
    df_filtered = df[(df['norm_win_prob'] >= 0.1) & (df['tansho_odds'] < 30.0)].copy()

    # 期待値のしきい値バリエーション
    thresholds = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

    report_lines = []
    report_lines.append("📊 **【期待値別：全頭買い vs 最高EV1頭買い 比較レポート】**")
    report_lines.append("🔒 フィルター: 補正後勝率 >= 10% ＆ 単勝オッズ < 30倍")
    report_lines.append("```yaml")
    report_lines.append("{:<6} | {:<20} | {:<20}".format("EV下限", "【A】全頭買い", "【B】期待値最高1頭のみ買い"))
    report_lines.append("-" * 60)

    for th in thresholds:
        # 1レースごとに該当馬を調べるためのグループ化
        # シナリオA (全頭買い)
        selected_all = df_filtered[df_filtered['win_ev'] >= th].copy()
        total_all = len(selected_all)
        hits_all = selected_all['is_win'].sum()
        hit_rate_all = (hits_all / total_all * 100) if total_all > 0 else 0
        invest_all = total_all * 100
        payout_all = selected_all['payout'].sum()
        rec_all = (payout_all / invest_all * 100) if invest_all > 0 else 0
        profit_all = payout_all - invest_all

        # シナリオB (期待値最高1頭のみ)
        # レース内で期待値がしきい値以上の馬をグループ化し、各レースで期待値が最大のもののみを抽出
        grouped = df_filtered[df_filtered['win_ev'] >= th].groupby('race_id')
        selected_single_list = []
        for race_id, group in grouped:
            # 最も期待値が高い馬を1頭だけ抽出
            best_horse = group.sort_values(by='win_ev', ascending=False).iloc[0]
            selected_single_list.append(best_horse)
            
        if selected_single_list:
            selected_single = pd.DataFrame(selected_single_list)
            total_single = len(selected_single)
            hits_single = selected_single['is_win'].sum()
            hit_rate_single = (hits_single / total_single * 100) if total_single > 0 else 0
            invest_single = total_single * 100
            payout_single = selected_single['payout'].sum()
            rec_single = (payout_single / invest_single * 100) if invest_single > 0 else 0
            profit_single = payout_single - invest_single
        else:
            total_single = 0
            hits_single = 0
            hit_rate_single = 0.0
            invest_single = 0
            payout_single = 0.0
            rec_single = 0.0
            profit_single = 0.0

        # 出力テキストの生成
        str_all = f"{total_all}点/{rec_all:.1f}% ({profit_all:+,.0f}円)"
        str_single = f"{total_single}点/{rec_single:.1f}% ({profit_single:+,.0f}円)"
        
        report_lines.append("{:<6.1f} | {:<20} | {:<20}".format(
            th, str_all, str_single
        ))

    report_lines.append("```")
    full_message = "\n".join(report_lines)
    
    # コンソール表示
    print(full_message)
    
    # 引数に "send" が指定されている場合は Discord に送信
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        send_discord_message(full_message)

if __name__ == '__main__':
    main()
