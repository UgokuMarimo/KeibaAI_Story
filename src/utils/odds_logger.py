# C:\KeibaAI\src\utils\odds_logger.py
import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta, date
import threading
import argparse

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
sys.path.append(_current_dir)

import config
from src.utils.schedule_scraper import get_race_schedule_for_date
from src.utils.jra_odds_scraper import JRAOddsScraper

# 設定
LOG_START_MINUTES_BEFORE = 10     # 発走の何分前からロギングを開始するか
LOG_INTERVAL_SECONDS = 60         # 収集間隔（秒）

def log_race_odds_worker(race_id: str, venue_name: str, race_num: int, start_time: datetime, target_date_str: str):
    """
    1つのレースに対して、発走まで1分おきにオッズを取得しCSVファイルに記録し続けるワーカースレッド。
    """
    print(f"\n[ODDS-LOGGER] Worker started for Race {race_id} ({venue_name} {race_num}R), target start: {start_time.strftime('%H:%M')}")
    
    # 保存フォルダの準備
    save_dir = os.path.join(PROJECT_ROOT, 'data', 'odds_history')
    os.makedirs(save_dir, exist_ok=True)
    csv_path = os.path.join(save_dir, f"odds_{race_id}.csv")
    
    # スクレイパーの起動（ヘッドレスモード）
    scraper = JRAOddsScraper(headless=True)
    
    try:
        # 初回オッズ取得 & ページ展開
        print(f"[ODDS-LOGGER] [{race_id}] Initializing scraper page...")
        odds_df = scraper.get_odds(venue_name, race_num, target_date=target_date_str)
        
        # 初回データの書き込み
        if odds_df is not None and not odds_df.empty:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            odds_df['timestamp'] = now_str
            out_df = odds_df[['timestamp', '馬番', '馬名', '単勝']]
            
            header = not os.path.exists(csv_path)
            out_df.to_csv(csv_path, mode='a', header=header, index=False, encoding='utf-8-sig')
            print(f"[ODDS-LOGGER] [{race_id}] Initial odds saved ({len(out_df)} horses).")
        
        # 発走予定時刻まで毎分ループ
        end_time = start_time
        
        while datetime.now() < end_time:
            # 次の正分（またはLOG_INTERVAL_SECONDS秒後）まで待機するが、細かくスリープして終了判定を割り込み可能にする
            sleep_start = time.time()
            while time.time() - sleep_start < LOG_INTERVAL_SECONDS:
                if datetime.now() >= end_time:
                    break
                time.sleep(1)
            
            if datetime.now() >= end_time:
                break
                
            print(f"[ODDS-LOGGER] [{race_id}] Fetching minute-by-minute odds...")
            odds_df = scraper.refresh_odds()
            
            if odds_df is not None and not odds_df.empty:
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                odds_df['timestamp'] = now_str
                out_df = odds_df[['timestamp', '馬番', '馬名', '単勝']]
                out_df.to_csv(csv_path, mode='a', header=False, index=False, encoding='utf-8-sig')
                print(f"[ODDS-LOGGER] [{race_id}] Odds logged at {now_str}.")
            else:
                print(f"[ODDS-LOGGER WARN] [{race_id}] Failed to fetch odds at this minute.")
                
        print(f"[ODDS-LOGGER] [{race_id}] Race start time reached. Stopping worker.")
        
    except Exception as e:
        print(f"[ODDS-LOGGER ERROR] [{race_id}] Error in worker: {e}")
    finally:
        scraper.close()
        print(f"[ODDS-LOGGER] [{race_id}] Scraper session closed safely.")

def main():
    parser = argparse.ArgumentParser(description="JRA Real-time Odds Logger (1-minute intervals before race)")
    parser.add_argument(
        'target_date', 
        nargs='?', 
        default=date.today().strftime("%Y-%m-%d"), 
        help="Target date in YYYY-MM-DD format. Defaults to today."
    )
    args = parser.parse_args()
    
    target_date_str = args.target_date
    print(f"=== [START] JRA Odds Logger (Target Date: {target_date_str}) ===")
    
    # 1. スケジュールを取得
    schedule_df = get_race_schedule_for_date(target_date_str)
    if schedule_df is None or schedule_df.empty:
        print("No races found for the specified date. Exiting.")
        return
        
    print(f"Found {len(schedule_df)} races to monitor.")
    print(schedule_df[['race_id', 'start_time']].to_string())
    
    # レースごとのスレッド追跡 {race_id: thread}
    active_workers = {}
    
    print("\n--- Odds monitoring loop started. (Press Ctrl+C to exit) ---")
    try:
        while True:
            now = datetime.now()
            all_races_done = True
            
            for index, row in schedule_df.iterrows():
                race_id = row['race_id']
                try:
                    start_time = datetime.strptime(f"{target_date_str} {row['start_time']}", "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    continue
                
                # ロギング開始判定（発走15分前）
                log_start_trigger = start_time - timedelta(minutes=LOG_START_MINUTES_BEFORE)
                
                # すでに発走したか
                is_finished = now >= start_time
                
                if not is_finished:
                    all_races_done = False
                
                # ロギング開始条件に合致し、かつスレッドが未起動の場合
                if log_start_trigger <= now < start_time and race_id not in active_workers:
                    course_id = race_id[4:6]
                    race_num = int(race_id[10:])
                    venue_name = config.PLACE_MAP_IDS.get(course_id)
                    
                    if venue_name:
                        t = threading.Thread(
                            target=log_race_odds_worker,
                            args=(race_id, venue_name, race_num, start_time, target_date_str),
                            daemon=True
                        )
                        active_workers[race_id] = t
                        t.start()
                    else:
                        print(f"[ODDS-LOGGER ERROR] Unknown course ID '{course_id}' for race {race_id}. Skipping.")
            
            # 不要になった完了スレッドのクリーンアップ
            finished_races = []
            for r_id, t in active_workers.items():
                if not t.is_alive():
                    finished_races.append(r_id)
            for r_id in finished_races:
                del active_workers[r_id]
                
            if all_races_done and not active_workers:
                print("\nAll scheduled races have finished. Stopping logger.")
                break
                
            # メイン監視のコンソール進捗表示
            active_count = len(active_workers)
            print(f"\r[{now.strftime('%H:%M:%S')}] Monitoring... Active Logger Threads: {active_count}", end="")
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nOdds Logger interrupted by user.")
        
    print("\n=== Odds Logger shutting down. ===")

if __name__ == "__main__":
    main()
