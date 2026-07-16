# C:\KeibaAI\src\a4_prediction\generate_daily_report.py

import sys
import os
import sqlite3
import argparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# 環境変数の読み込み
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

import config
from utils.result_scraper import get_tansho_result, get_race_odds_and_popularity
from utils.db_utils import send_discord_webhook

def get_latest_kaisai_date(conn) -> str:
    """予測DBに存在する最新の開催日（kaisai_date）を取得する"""
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(kaisai_date) FROM predictions")
    result = cursor.fetchone()
    return result[0] if result and result[0] else None

def generate_report(target_date_str: str = None, send_discord: bool = True):
    """
    指定された日付の予測結果と確定結果を照合し、
    「本命購入」および「期待値購入」の両方の単勝回収率レポートを生成・送信する。
    """
    if not os.path.exists(config.DB_PATH):
        print(f"[ERROR] Database file not found at: {config.DB_PATH}")
        return

    with sqlite3.connect(config.DB_PATH) as conn:
        # 日付が指定されていない場合、自動的に予測履歴の最新日付を取得
        if not target_date_str:
            target_date_str = get_latest_kaisai_date(conn)
            if not target_date_str:
                print("[ERROR] No prediction history found in database.")
                return
            print(f"[INFO] Automatically selected the latest predicted date: {target_date_str}")
        
        # 指定日の全予測データを取得 (全馬の勝率正規化やオッズを考慮するため全頭取得)
        query = """
        SELECT race_id, umaban, horse_name, keibajo, race_number, race_name, pred_win, pred_rank, tansho_odds, tansho_ninki
        FROM predictions
        WHERE kaisai_date = ?
        ORDER BY race_id ASC, pred_rank ASC
        """
        df_preds = pd.read_sql_query(query, conn, params=(target_date_str,))
        
        if df_preds.empty:
            print(f"[WARN] No predictions found in database for date: {target_date_str}")
            return
            
        print(f"\nAnalyzing predictions for {target_date_str}... Found {df_preds['race_id'].nunique()} races ({len(df_preds)} horses).")
        
        # --- 予測データのオッズ・人気補完 (確定ページからスクレイピングして補正) ---
        print("[INFO] Hydrating missing odds and popularity from netkeiba results...")
        unique_race_ids = df_preds['race_id'].unique().tolist()
        
        # 確定オッズをキャッシュ
        odds_hydration_cache = {}
        for rid in unique_race_ids:
            try:
                odds_pop = get_race_odds_and_popularity(rid)
                if odds_pop:
                    odds_hydration_cache[rid] = odds_pop
            except Exception as e:
                pass

        # predictions の null/0/NaN オッズを補完
        hydrated_count = 0
        for idx, row in df_preds.iterrows():
            rid = row['race_id']
            u = int(row['umaban'])
            if rid in odds_hydration_cache and u in odds_hydration_cache[rid]:
                cur_odds = row['tansho_odds']
                if pd.isna(cur_odds) or cur_odds <= 0.0:
                    df_preds.at[idx, 'tansho_odds'] = odds_hydration_cache[rid][u]['odds']
                    df_preds.at[idx, 'tansho_ninki'] = odds_hydration_cache[rid][u]['ninki']
                    hydrated_count += 1
                    
        if hydrated_count > 0:
            print(f"[INFO] Successfully hydrated {hydrated_count} horses with finalized odds from netkeiba.")
        
        # --- 予測勝率の動的正規化と期待値 (EV) の算出 ---
        # 各レース内で pred_win スコアの総和を 1.0 に正規化
        df_preds['pred_win_prob'] = df_preds.groupby('race_id')['pred_win'].transform(lambda x: x / x.sum() if x.sum() > 0 else 0.0)
        df_preds['expected_value'] = df_preds['pred_win_prob'] * df_preds['tansho_odds']
        
        # --- 集計用変数 ---
        # 1. 本命 (予測1位) 購入シミュレーション (A)
        a_races_count = 0
        a_hits_count = 0
        a_investment = 0
        a_payout = 0
        a_hit_details = []
        
        # 2. 期待値購入シミュレーション (B)
        # (config.TARGET_EV & config.MIN_WIN_PROB の基準に合致する馬をすべて購入)
        b_races_seen = set()  # 購入対象馬がいたレースIDセット
        b_hits_count = 0
        b_investment = 0
        b_payout = 0
        b_hit_details = []
        
        # 的中チェックのためのレースごとの結果キャッシュ
        # {race_id: (win_horses_list, payout_list)}
        results_cache = {}
        skip_count = 0
        
        # レースごとにグルーピングして照合
        grouped = df_preds.groupby('race_id')
        for race_id, group in grouped:
            # 確定結果を取得
            if race_id not in results_cache:
                win_horses, payouts = get_tansho_result(race_id)
                results_cache[race_id] = (win_horses, payouts)
            else:
                win_horses, payouts = results_cache[race_id]
                
            if win_horses is None or payouts is None:
                # 結果未確定または取得失敗
                skip_count += 1
                continue
                
            keibajo = group.iloc[0]['keibajo']
            race_number = group.iloc[0]['race_number']
            race_name = group.iloc[0]['race_name']
            
            # ───────────────────────────────────────
            # シミュレーションA: 本命購入 (pred_rank == 1)
            # ───────────────────────────────────────
            fav_horse = group[group['pred_rank'] == 1]
            if not fav_horse.empty:
                fav_row = fav_horse.iloc[0]
                fav_umaban = int(fav_row['umaban'])
                fav_name = fav_row['horse_name']
                fav_ninki = fav_row['tansho_ninki']
                
                a_races_count += 1
                a_investment += 100  # 単勝100円
                
                # 的中チェック
                for idx, win_u in enumerate(win_horses):
                    if win_u == fav_umaban:
                        payout_amount = payouts[idx]
                        a_payout += payout_amount
                        a_hits_count += 1
                        pop_str = f" ({int(fav_ninki)}番人気)" if pd.notna(fav_ninki) and not pd.isna(fav_ninki) else ""
                        a_hit_details.append(
                            f"・ {keibajo}{race_number}R ({race_name}): {fav_umaban}番 {fav_name}{pop_str} 🎉 払戻金: {payout_amount:,}円"
                        )
                        break
            
            # 閾値基準: 勝率 MIN_WIN_PROB 以上、かつ レポート（事後検証）では最終オッズでの期待値 1.3 以上を評価
            target_ev = 1.3
            min_win_prob = getattr(config, 'MIN_WIN_PROB', 0.10)
            ev_horses = group[(group['pred_win_prob'] >= min_win_prob) & (group['expected_value'] >= target_ev)]
            
            if not ev_horses.empty:
                b_races_seen.add(race_id)
                
                # 該当する馬をすべて購入する (複数頭買い対応)
                for _, ev_row in ev_horses.iterrows():
                    ev_umaban = int(ev_row['umaban'])
                    ev_name = ev_row['horse_name']
                    ev_ninki = ev_row['tansho_ninki']
                    ev_val = ev_row['expected_value']
                    
                    b_investment += 100  # 単勝100円
                    
                    # 的中チェック
                    for idx, win_u in enumerate(win_horses):
                        if win_u == ev_umaban:
                            payout_amount = payouts[idx]
                            b_payout += payout_amount
                            b_hits_count += 1
                            pop_str = f" ({int(ev_ninki)}番人気)" if pd.notna(ev_ninki) and not pd.isna(ev_ninki) else ""
                            b_hit_details.append(
                                f"・ {keibajo}{race_number}R ({race_name}): {ev_umaban}番 {ev_name}{pop_str} (EV: {ev_val:.2f}) 🎉 払戻金: {payout_amount:,}円"
                            )
                            break
                            
        # --- 回収率・的中率の算出 ---
        # A. 本命シミュレーション
        a_recovery_rate = (a_payout / a_investment) * 100 if a_investment > 0 else 0.0
        a_hit_rate = (a_hits_count / a_races_count) * 100 if a_races_count > 0 else 0.0
        
        # B. 期待値シミュレーション
        b_races_count = len(b_races_seen)
        b_recovery_rate = (b_payout / b_investment) * 100 if b_investment > 0 else 0.0
        b_hit_rate = (b_hits_count / (b_investment / 100)) * 100 if b_investment > 0 else 0.0  # 的中頭数/購入点数

        if a_races_count == 0 and b_races_count == 0:
            print(f"[WARN] All {skip_count} races for this date are still unconfirmed. Report skipped.")
            return

        # 日本語日付フォーマットの作成
        try:
            dt = datetime.strptime(target_date_str, "%Y-%m-%d")
            weekday_map = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
            formatted_date = f"{dt.year}年{dt.month}月{dt.day}日 ({weekday_map[dt.weekday()]})"
        except ValueError:
            formatted_date = target_date_str
        
        # --- 速報メッセージ構築 ---
        header = f"📊 **AI予測結果レポート（単勝速報）** 📊\n"
        separator = "━" * 22 + "\n"
        
        body = f"📅 **対象日**: {formatted_date}\n\n"
        
        # 1. 本命購入シミュレーション表示
        body += f"🔴 **【本命（予測1位）購入シミュレーション】**\n"
        body += f"● 参加レース数: {a_races_count} R\n"
        body += f"● 購入点数: {a_races_count} 点 ({a_investment:,}円)\n"
        body += f"● 的中レース数: {a_hits_count} R (的中率: {a_hit_rate:.1f}%)\n"
        body += f"● 合計払い戻し: {a_payout:,} 円\n"
        body += f"● 回収率: {a_recovery_rate:.1f}% "
        
        if a_recovery_rate >= 100.0: body += "🚀"
        elif a_recovery_rate >= 80.0: body += "✨"
        else: body += "💧"
        body += "\n\n"
        
        # 2. 期待値購入シミュレーション表示
        min_win_prob = getattr(config, 'MIN_WIN_PROB', 0.10)
        body += f"🔵 **【期待値（EV >= {target_ev:.1f} & 勝率 >= {min_win_prob*100:.0f}%）購入シミュレーション】**\n"
        body += f"● 対象レース数: {b_races_count} R (※購入条件合致レース)\n"
        body += f"● 購入点数: {b_investment // 100} 点 ({b_investment:,}円) ※複数頭買い含む\n"
        body += f"● 的中頭数: {b_hits_count} 頭 (的中率: {b_hit_rate:.1f}%)\n"
        body += f"● 合計払い戻し: {b_payout:,} 円\n"
        body += f"● 回収率: {b_recovery_rate:.1f}% "
        
        if b_recovery_rate >= 100.0: body += "🚀"
        elif b_recovery_rate >= 80.0: body += "✨"
        else: body += "💧"
        body += "\n\n"
        
        # 3. 的中詳細の表示
        body += "**【本命購入の的中詳細】**\n"
        if a_hit_details:
            body += "\n".join(a_hit_details) + "\n"
        else:
            body += "・的中はありませんでした。\n"
        body += "\n"
        
        body += "**【期待値購入の的中詳細】**\n"
        if b_hit_details:
            body += "\n".join(b_hit_details) + "\n"
        else:
            body += "・的中はありませんでした。\n"
            
        if skip_count > 0:
            body += f"\n※ 結果未確定につきスキップしたレース: {skip_count} R\n"
            
        full_message = header + separator + body + separator
        
        # コンソール出力 (CP932などのWindows標準エンコード環境でのUnicodeEncodeErrorを防止)
        print("\n" + "="*50)
        try:
            print(full_message)
        except UnicodeEncodeError:
            encoding = sys.stdout.encoding or 'utf-8'
            safe_message = full_message.encode(encoding, errors='replace').decode(encoding)
            print(safe_message)
        print("="*50 + "\n")
        
        # Discord 送信
        if send_discord:
            report_webhook = os.getenv("DISCORD_REPORT_WEBHOOK_URL")
            if report_webhook:
                send_discord_webhook(full_message, webhook_url=report_webhook)
                print("-> Report notification sent to Discord.")
            else:
                print("[INFO] DISCORD_REPORT_WEBHOOK_URL not configured. Discord skip.")

def main():
    parser = argparse.ArgumentParser(description="Generate daily prediction report.")
    parser.add_argument('--date', nargs='+', help="Target date(s) in YYYY-MM-DD format. Can specify multiple dates. Defaults to the latest available predicted date.")
    parser.add_argument('--no-discord', action='store_false', dest='send_discord', help="Disable Discord notification.")
    args = parser.parse_args()
    
    if args.date:
        # 複数日付が指定された場合はそれぞれレポートを生成
        for date_str in args.date:
            print(f"\n{'='*60}")
            print(f"[REPORT] Generating report for date: {date_str}")
            print(f"{'='*60}")
            generate_report(date_str, send_discord=args.send_discord)
    else:
        # 日付未指定の場合は最新日のみ
        generate_report(None, send_discord=args.send_discord)

if __name__ == "__main__":
    main()
