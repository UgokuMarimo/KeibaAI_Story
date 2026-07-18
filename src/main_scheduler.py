# C:\KeibaAI\main_scheduler.py (最終版)

"""
競馬予測を自動実行するためのメインスケジューラー。

■ 主な役割
1. 指定された日付のレーススケジュールを取得する。
2. スケジュールを監視し、各レースの発走時刻の一定時間前になると予測をトリガーする。
3. 予測スクリプト(m04_predict.py)をサブプロセスとして呼び出し、自動実行する。
4. 発走の直前にリアルタイムオッズを取得し、期待値(EV)を計算して通知する。
5. 全てのレースの処理が完了すると自動的に終了する。

■ 使い方
# 今日のレースを対象に実行
python src/main_scheduler.py

# 特定の日付を対象に実行

python src/main_scheduler.py 2026-04-19
"""
import sys
import os
import json
import pandas as pd
from datetime import datetime, timedelta, date
import time
import subprocess
import argparse

# --- プロジェクトパス設定 ---
# 自身が src/ 配下に移ったため、PROJECT_ROOTは1階層上になります
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(_current_dir)
# ---

import config
from src.utils.schedule_scraper import get_race_schedule_for_date
from src.utils.db_utils import send_discord_webhook

# 新しく分割したモジュールをインポート
from src.utils.ev_worker import process_odds_and_ev_5min, process_odds_and_ev_2min
from prediction.predict import load_models, predict_race

# --- 設定 ---
CHECK_INTERVAL_SECONDS = 15     # 何秒おきにスケジュールをチェックするか
# ---

def run_prediction_direct(race_id: str, models, artifacts) -> str:
    """予測スクリプトを同一プロセス内で直接実行する。"""
    print(f"\n--- [TRIGGER] Predicting for race {race_id} at {datetime.now().strftime('%H:%M:%S')} ---")
    try:
        # SHAPとLLM(解説)をオフにして高速化・安定化
        result_df = predict_race(
            race_id=race_id, 
            run_shap=False, 
            enable_explanation=False, 
            models=models, 
            artifacts=artifacts
        )
        if result_df is None:
            # 障害・新馬戦スキップなど
            print(f"[SCHEDULER SKIPPED] Prediction for race {race_id} was skipped or failed safely.")
            return "SKIPPED"
        else:
            print(f"[SCHEDULER SUCCESS] Prediction for race {race_id} completed.")
            return "SUCCESS"
    except Exception as e:
        print(f"[SCHEDULER ERROR] An unexpected error occurred during prediction for {race_id}: {e}")
        return "ERROR"

def main(target_date_str: str, predict_past: bool = False):
    """メイン実行関数"""
    print(f"--- [START] Keiba Prediction Scheduler (Target Date: {target_date_str}, Predict Past: {predict_past}) ---")

    # --- 起動時データベース同期 (Cloud -> Local) ---
    try:
        from utils.db_sync import get_sqlite_conn, get_pg_conn, create_pg_tables_if_not_exists, sync_pg_to_sqlite
        print("\n[DB SYNC] 起動時データベース同期 (Cloud -> Local) を実行中...")
        sqlite_conn = get_sqlite_conn()
        pg_conn = get_pg_conn()
        create_pg_tables_if_not_exists(pg_conn)
        sync_pg_to_sqlite(pg_conn, sqlite_conn)
        sqlite_conn.close()
        pg_conn.close()
        print("[DB SYNC] 起動時同期完了。\n")
    except Exception as e:
        print(f"[DB SYNC WARN] 起動時データベース同期に失敗しました (ローカルデータで続行します): {e}\n")

    # 1. レーススケジュールを取得
    schedule_df = get_race_schedule_for_date(target_date_str)
    if schedule_df is None or schedule_df.empty:
        print("\nNo races found for the specified date. Exiting."); return

    print(f"\nFound {len(schedule_df)} races. Waiting for timing...")
    print(schedule_df.to_string())
    
    # 1.5. モデルとアーティファクトの事前読み込み (高速化)
    print("\n[INFO] Loading prediction models into memory (Slow start, fast prediction)...")
    try:
        models, artifacts = load_models()
        print("[INFO] Models loaded successfully!")
    except Exception as e:
        print(f"[FATAL] Failed to load models: {e}")
        return
    
    # 状態管理 {race_id: {'predicted': False, 'notified': False}}
    # 起動時にすでに発走時刻を過ぎている過去レースは自動スキップ。
    # また、すでに予測データ（prediction_summary.json）が存在するレースは、predicted=True から開始し、予測の再実行を防ぎます。
    race_status = {}
    now = datetime.now()
    for index, row in schedule_df.iterrows():
        race_id = row['race_id']
        try:
            start_time = datetime.strptime(f"{target_date_str} {row['start_time']}", "%Y-%m-%d %H:%M")
            
            # すでに予測データが存在するかチェック
            year, course, kaisai, nissuu, race_num = race_id[:4], race_id[4:6], race_id[6:8], race_id[8:10], race_id[10:]
            summary_path = os.path.join(config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num, "prediction_summary.json")
            has_pred = os.path.exists(summary_path)
            
            # 発走時刻の2分前を過ぎている過去レースの場合
            if now >= (start_time - timedelta(minutes=2)):
                # 自動投票は締切済みの過去のため、確実にスキップ（notified=True, voted=True）
                notified_status = True
                voted_status = True
                
                # --predict-past 指定があり、かつまだ予測データがない場合のみ予測を実行する
                if predict_past and not has_pred:
                    predicted_status = False
                    print(f"[SCHEDULER] レース {race_id} ({row['start_time']}発走) は過去ですが、--predict-past指定に基づき【予測のみ実行（DB保存用）】します。")
                else:
                    predicted_status = True
                    reason = "すでに予測データが存在するため" if has_pred else "締切時刻を過ぎているため"
                    print(f"[SCHEDULER] レース {race_id} ({row['start_time']}発走) は{reason}、予測・自動投票ともに【自動スキップ】しました。")
                    
                race_status[race_id] = {'predicted': predicted_status, 'notified': notified_status, 'voted': voted_status}
            else:
                # 未来のレースで、すでに予測データが存在する場合
                if has_pred:
                    race_status[race_id] = {'predicted': True, 'notified': False, 'voted': False}
                    print(f"[SCHEDULER] レース {race_id} ({row['start_time']}発走) は【予測データが存在するため予測ステップをスキップ】し、発走5分前のオッズ・期待値計算を待ちます。")
                else:
                    race_status[race_id] = {'predicted': False, 'notified': False, 'voted': False}
        except Exception:
            race_status[race_id] = {'predicted': False, 'notified': False}
    
    is_today = (target_date_str == date.today().strftime("%Y-%m-%d"))
    if not is_today:
        print(f"\n[INFO] Target date {target_date_str} is not today. Real-time odds fetching and EV notification will be skipped.")

    # 2. メインの監視ループを開始
    print("\n--- Monitoring loop started. (Press Ctrl+C to exit) ---")
    try:
        while True:
            now = datetime.now()
            all_complete = True
            
            for index, row in schedule_df.iterrows():
                race_id = row['race_id']
                status = race_status[race_id]
                
                if status['predicted'] and status['notified'] and status['voted']:
                    continue
                
                all_complete = False 

                try:
                    start_time = datetime.strptime(f"{target_date_str} {row['start_time']}", "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    print(f"\n[WARN] Could not parse start_time for race {race_id}. Skipping.")
                    status['predicted'] = True
                    status['notified'] = True
                    status['voted'] = True
                    continue

                prediction_trigger = start_time - timedelta(minutes=config.PREDICTION_TIMING_MINUTES)
                ev_trigger = start_time - timedelta(minutes=config.ODDS_NOTIFY_TIMING_MINUTES)
                
                # --- Phase 1: Prediction (50 min before) ---
                if now >= prediction_trigger and not status['predicted']:
                    pred_result = run_prediction_direct(race_id, models=models, artifacts=artifacts)
                    if pred_result == "SUCCESS":
                        status['predicted'] = True
                    elif pred_result == "SKIPPED":
                        # スキップされた場合はEV計算・通知・投票フェーズも完了（スキップ）扱いにする
                        status['predicted'] = True
                        status['notified'] = True
                        status['voted'] = True
                    else:
                        print(f"[WARN] Prediction failed for {race_id}. Retry next loop.")
                        time.sleep(1)
                
                # --- Phase 2: Odds & EV Notification (5 min before) ---
                # 予測が完了していることが前提
                if now >= ev_trigger and not status['notified']:
                    if not is_today:
                        # 本日以外の日付が指定された場合はオッズ取得とEV計算をスキップ
                        status['notified'] = True
                        status['voted'] = True
                    elif status['predicted']: 
                        # 5分前時点で仮選定（EV 1.2以上）を行い、候補馬がいるか判定
                        has_candidate = process_odds_and_ev_5min(race_id, target_date_str)
                        status['notified'] = True
                        if not has_candidate:
                            # 候補馬がいなければ、2分前の投票フェーズは不要なので完了にする
                            status['voted'] = True
                            print(f"[SCHEDULER] レース {race_id}: 5分前時点でEV 1.2以上の馬がいないため、2分前自動投票をスキップします。")
                    else:
                        # 予測がまだの場合は次まで待つ
                        pass

                # --- Phase 3: Auto Voting (2 min before) ---
                # 5分前通知が完了しており、かつまだ投票処理をしていない場合
                vote_trigger = start_time - timedelta(minutes=config.AUTO_VOTE_TIMING_MINUTES)
                if now >= vote_trigger and not status['voted']:
                    if not is_today:
                        status['voted'] = True
                    elif status['notified']:
                        # 2分前の時点で再度オッズを取得し、最終判定と投票を行う
                        process_odds_and_ev_2min(race_id, target_date_str)
                        status['voted'] = True
                    else:
                        pass
            
            if all_complete:
                print("\n-> All races have been processed.")
                break
            
            done_count = sum(1 for v in race_status.values() if v['predicted'] and v['notified'] and v['voted'])
            print(f"\r[{now.strftime('%H:%M:%S')}] Monitoring... Complete {done_count}/{len(schedule_df)} races.", end="")
            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\nScheduler interrupted by user.")
    finally:
        # --- 終了時データベース同期 (Local -> Cloud) ---
        try:
            from utils.db_sync import get_sqlite_conn, get_pg_conn, sync_sqlite_to_pg
            print("\n[DB SYNC] 終了時データベース同期 (Local -> Cloud) を実行中...")
            sqlite_conn = get_sqlite_conn()
            pg_conn = get_pg_conn()
            sync_sqlite_to_pg(sqlite_conn, pg_conn)
            sqlite_conn.close()
            pg_conn.close()
            print("[DB SYNC] 終了時同期完了。")
        except Exception as e:
            print(f"[DB SYNC WARN] 終了時データベース同期に失敗しました: {e}")

    print("\n\n--- All scheduled races have been processed. Scheduler shutting down. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Keiba Prediction Scheduler.")
    parser.add_argument(
        'target_date', 
        nargs='?', 
        default=date.today().strftime("%Y-%m-%d"), 
        help="Target date in YYYY-MM-DD format. Defaults to today."
    )
    parser.add_argument(
        '--predict-past', 
        action='store_true', 
        help="すでに発走時刻を過ぎた過去のレースに対しても、AI予測のみを実行して predictions.db に保存します（自動投票は安全にスキップされます）。"
    )
    args = parser.parse_args()
    main(args.target_date, predict_past=args.predict_past)