# C:\KeibaAI\src\analysis\generate_may_report.py
import sqlite3
import json
import os
import pandas as pd
import numpy as np
import urllib.request
import sys

# Windows環境でのコンソール文字化け・エンコードエラー対策
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# 設定
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
                print("Discordへの通知に成功しました。")
            else:
                print(f"Discordへの通知ステータスコード: {response.status}")
    except Exception as e:
        print(f"Discord通知中にエラーが発生しました: {e}")

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
    WHERE p.kaisai_date >= '2026-05-01' AND p.kaisai_date <= '2026-05-31'
    ORDER BY p.kaisai_date ASC, p.race_id ASC, p.umaban ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("2026年5月のデータが見つかりませんでした。")
        return

    print(f"Loaded {len(df)} predictions for May 2026.")

    # 2. 前処理
    # 予測勝率のノーマライズ
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['norm_win_prob'] = df['pred_win'] / np.where(race_sums > 0, race_sums, 1.0)
    
    # 期待値と払戻金の計算
    df['expected_value'] = df['norm_win_prob'] * df['tansho_odds']
    df['is_win'] = np.where(df['result_rank'] == 1, 1, 0)
    # 単勝払戻金: 的中なら tansho_payout (無い場合は tansho_odds * 100 で補完)
    df['payout'] = np.where(df['is_win'] == 1, df['tansho_payout'], 0.0)
    df['payout'] = np.where((df['is_win'] == 1) & (df['payout'] <= 0), df['tansho_odds'] * 100, df['payout'])

    # 3. 開催日数の取得
    unique_dates = df['kaisai_date'].nunique()

    # 4. 固定セーフティ条件：勝率 >= 10% かつ オッズ < 30倍
    base_df = df[(df['norm_win_prob'] >= 0.1) & (df['tansho_odds'] < 30.0)]

    # レポート用テキストの作成
    report_lines = []
    report_lines.append("🏆 **【2026年5月度 単勝期待値別 成績レポート】**")
    report_lines.append(f"📅 集計期間: 2026-05-01 〜 2026-05-31 (開催日数: {unique_dates}日)")
    report_lines.append("🔒 フィルター条件: 補正後勝率 >= 10% ＆ 単勝オッズ < 30倍")
    report_lines.append("```")
    report_lines.append("{:<6} | {:<5} | {:<4} | {:<7} | {:<8} | {:<8} | {:<7}".format(
        "EV下限", "購入数", "的中", "的中率", "総投資", "総払戻", "回収率"
    ))
    report_lines.append("-" * 65)

    for ev_thresh in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]:
        sub_df = base_df[base_df['expected_value'] >= ev_thresh]
        total = len(sub_df)
        if total == 0:
            report_lines.append("{:<6.1f} | {:<5} | {:<4} | {:<7} | {:<8} | {:<8} | {:<7}".format(
                ev_thresh, 0, 0, "0.0%", "0円", "0円", "0.0%"
            ))
            continue
            
        hits = sub_df['is_win'].sum()
        hit_rate = hits / total * 100
        investment = total * 100
        payout_sum = sub_df['payout'].sum()
        recovery_rate = payout_sum / investment * 100
        net_profit = payout_sum - investment
        
        report_lines.append("{:<6.1f} | {:<5} | {:<4} | {:<6.1f}% | {:<6,}円 | {:<6,}円 | {:<6.1f}% ({:+,.0f}円)".format(
            ev_thresh, total, hits, hit_rate, investment, int(payout_sum), recovery_rate, net_profit
        ))

    report_lines.append("```")
    
    # Discord送信用テキスト結合
    full_message = "\n".join(report_lines)
    
    # コンソール表示 (エラー回避のため、安全な出力処理)
    try:
        print(full_message)
    except Exception:
        # 万が一のエラー時は代替テキストを表示
        print("--- 2026年5月度 成績レポート (出力文字コードエラー回避) ---")
        for line in report_lines:
            try:
                print(line)
            except Exception:
                pass
    
    # Discord送信
    send_discord_message(full_message)

if __name__ == '__main__':
    main()
