# C:\KeibaAI\src\analysis\generate_annual_budget_report.py
import sqlite3
import pandas as pd
import numpy as np
import os
import sys
import calendar
import requests

# プロジェクトルートの設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import config

# 新しいWebhook URL (個人予算・回収額管理用)
PERSONAL_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1515615707490947072/2vFsIK--ZqttNGmu4TayU4Wjg0qIo0DMizq80PtotuwK__kAFP-RTDsKgPSrpbLW0ej2"

def send_discord_message(content, webhook_url):
    """詳細なステータスチェック付きのDiscord送信関数"""
    try:
        res = requests.post(
            webhook_url,
            json={"content": content, "username": "競馬AI予算管理"},
            headers={"Content-Type": "application/json"}
        )
        if res.status_code in [200, 204]:
            print(f"-> Message sent to Discord successfully. (Target: {webhook_url[-10:]}...)")
            return True
        else:
            print(f"[ERROR] Discord returned status {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send Discord notification: {e}")
        return False

def calculate_consecutive_losses(is_win_series):
    """
    is_win_series: pandas Series or list where 0 means loss, 1 means win
    Returns (max_losses, current_losses)
    """
    if len(is_win_series) == 0:
        return 0, 0
    max_losses = 0
    current_losses = 0
    for val in is_win_series:
        if val == 0:
            current_losses += 1
            if current_losses > max_losses:
                max_losses = current_losses
        else:
            current_losses = 0
    return max_losses, current_losses

def probability_of_k_consecutive_losses(n, p, k):
    """
    n: total trials
    p: hit rate (0.0 <= p <= 1.0)
    k: consecutive losses (k >= 1)
    Returns probability (0.0 to 1.0)
    """
    if n < k or k <= 0 or n <= 0:
        return 0.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    q = 1.0 - p
    a = [0.0] * (n + 1)
    for i in range(k):
        a[i] = 1.0
    a[k] = 1.0 - (q ** k)
    pqk = p * (q ** k)
    for i in range(k + 1, n + 1):
        a[i] = a[i - 1] - a[i - k - 1] * pqk
    prob = 1.0 - a[n]
    return max(0.0, min(1.0, prob))

def main():
    db_path = config.DB_PATH
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    # 1. データの読み込み
    conn = sqlite3.connect(db_path)
    
    # 実際の投票実績（votesテーブル）のみを取得
    query = """
    SELECT 
        v.race_id,
        v.umaban,
        v.horse_name,
        v.kaisai_date,
        v.pred_win_prob AS norm_win_prob,
        v.vote_odds AS tansho_odds,
        v.amount,
        p.result_rank,
        pay.tansho_payout
    FROM votes v
    LEFT JOIN predictions p ON v.race_id = p.race_id AND v.umaban = p.umaban
    LEFT JOIN payouts pay ON v.race_id = pay.race_id
    WHERE v.kaisai_date >= '2026-01-01' AND v.kaisai_date <= '2026-12-31'
      AND v.status = 'success' AND v.mode = 'umaca'
    ORDER BY v.kaisai_date ASC, v.race_id ASC, v.umaban ASC
    """
    try:
        df_real = pd.read_sql_query(query, conn)
    except Exception as e:
        if "no such table" in str(e):
            df_real = pd.DataFrame()
        else:
            conn.close()
            raise e
    conn.close()

    if df_real.empty:
        print("[INFO] 2026年の実投票データがまだデータベースに存在しません。")
        # 最初の投票が行われるまではレポート送信を行わずに終了します
        return

    # 2. 前処理 (実投票データ)
    df_real['is_win'] = np.where(df_real['result_rank'] == 1, 1, 0)
    df_real['payout'] = np.where(df_real['is_win'] == 1, df_real['tansho_payout'], 0.0)
    # 配当データがない（あるいは0以下）の場合は投票オッズ * 投票金額で補完
    df_real['payout'] = np.where((df_real['is_win'] == 1) & (df_real['payout'] <= 0), df_real['tansho_odds'] * df_real['amount'], df_real['payout'])
    
    selected_single = df_real.copy()
    
    # 3. 個人実績データの合算 (1月〜6月の累計実績: ネット投票 14,300円 + UMACA 28,300円)
    PERSONAL_INVEST = 42600
    PERSONAL_PAYOUT = 25550

    # 指標の計算
    ai_bets = len(selected_single)
    ai_hits = selected_single['is_win'].sum()
    ai_hit_rate = ai_hits / ai_bets * 100 if ai_bets > 0 else 0.0
    ai_investment = ai_bets * 100
    ai_payout = selected_single['payout'].sum()

    # 全体（個人＋AI）の金銭成績
    total_investment = ai_investment + PERSONAL_INVEST
    total_payout_amount = ai_payout + PERSONAL_PAYOUT
    total_recovery_rate = total_payout_amount / total_investment * 100
    total_net_profit = total_payout_amount - total_investment

    # 4. 連敗数と統計的確率の計算
    is_win_series = selected_single['is_win'].tolist()
    max_losses, current_losses = calculate_consecutive_losses(is_win_series)
    
    # 確率の計算 (的中率 p, 試行回数 n, 最大連敗数 k)
    p = ai_hit_rate / 100.0
    n = ai_bets
    k = max_losses
    prob = probability_of_k_consecutive_losses(n, p, k)
    
    # 確率に基づく客観メッセージの定義
    if prob >= 0.50:
        prob_msg = "統計学的に普通に起こり得る現象です。一喜一憂せず、長期的な視点で運用を続けましょう。"
    elif prob >= 0.10:
        prob_msg = "統計的にやや珍しい偏りですが、十分に起こり得る範囲内です。"
    else:
        prob_msg = "統計的にかなり珍しい偏り（下振れ）が発生しています。モデルや市場環境の乖離がないか念のため注視してください。"

    # 予測が存在する最古の日付を取得 (参考用)
    min_date_str = selected_single['kaisai_date'].min() # 例: '2026-04-12'

    # AI単体の回収率計算
    ai_recovery_rate = ai_payout / ai_investment * 100 if ai_investment > 0 else 0.0

    # メッセージ作成
    border = "━" * 20
    message = f"""📅 **【2026年 競馬年間成績レポート】**
{border}
📊 **通算成績サマリー** (※個人実績分を含む)
- 💸 **総投資金額**   : {total_investment:,} 円
- 🏆 **総回収金額**   : {int(total_payout_amount):,} 円
- 📈 **トータル回収率** : {total_recovery_rate:.1f}%
- 💰 **トータル純損益** : {int(total_net_profit):+,} 円
{border}
🤖 **今週の実績**
- 🗳️ **AI購入頭数**   : {ai_bets} 頭
- 🎯 **AI的中率**     : {ai_hit_rate:.1f}% ({ai_hits} / {ai_bets})
- 💵 **AI投資金額**   : {ai_investment:,} 円
- 💎 **AI回収金額**   : {int(ai_payout):,} 円
- 📊 **AI回収率**     : {ai_recovery_rate:.1f}%"""

    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        print(message.encode(encoding, errors='replace').decode(encoding))

    # Discord送信
    if send_discord_message(message, PERSONAL_WEBHOOK_URL):
        print("-> Discord personal notification sent successfully.")
    else:
        print("-> Failed to send Discord notification.")

if __name__ == '__main__':
    main()
