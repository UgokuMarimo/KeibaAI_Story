# C:\KeibaAI\src\update_model.py
import subprocess
import sys
import os
import time
import argparse
import datetime
from datetime import datetime as dt

# プロジェクトルートの設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
CODE_DIR = _current_dir
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

def run_command(command, description):
    """コマンドを実行し、成功/失敗を表示する"""
    print(f"\n{'='*60}")
    print(f"[{dt.now().strftime('%H:%M:%S')}] START: {description}")
    print(f"Command: {' '.join(command)}")
    print(f"{'='*60}")
    
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            command, 
            cwd=PROJECT_ROOT, 
            check=True,
            env=env
        )
        print(f"\n>>> SUCCESS: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n>>> FAILED: {description}")
        print(f"Error Code: {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n>>> ERROR: Command not found or script path invalid.")
        return False
    except Exception as e:
        print(f"\n>>> ERROR: Unexpected error: {e}")
        return False

def get_recent_weekend_dates() -> list:
    """
    今日の日付から遡って、直近7日間のうち土曜日(weekday=5)と日曜日(weekday=6)の日付を算出して返す。
    """
    today = datetime.date.today()
    weekend_dates = []
    for i in range(1, 8):
        d = today - datetime.timedelta(days=i)
        if d.weekday() in [5, 6]:
            weekend_dates.append(d.strftime("%Y%m%d"))
    weekend_dates.sort()
    return weekend_dates

def send_update_report(step_results, start_time, success=True):
    """モデル更新の結果をDiscordに通知する"""
    try:
        from utils.db_utils import send_discord_webhook
        import config
    except ImportError:
        print("[WARN] Failed to import db_utils/config for Discord notification.")
        return
        
    elapsed = time.time() - start_time
    elapsed_str = f"{elapsed//60:.0f}分 {elapsed%60:.0f}秒"
    
    # 総合ステータス判定
    all_ok = all(step_results.values())
    status_emoji = "✅" if success and all_ok else "⚠️"
    if not success:
        status_emoji = "❌"
        
    msg = f"🔄 **モデル定期更新完了レポート** {status_emoji}\n"
    msg += f"実行完了時刻: {dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"総実行時間: {elapsed_str}\n\n"
    
    msg += "**【各ステップの処理結果】**\n"
    for step, res in step_results.items():
        res_emoji = "✅ 成功" if res else "❌ 失敗"
        # Step 0は非致命的エラーのため警告扱いにする
        if not res and "Step 0" in step:
            res_emoji = "⚠️ 警告 (処理は続行)"
        msg += f"- {step}: {res_emoji}\n"
        
    if success and all_ok:
        msg += "\n🎉 すべてのステップが正常に完了し、モデルの更新が完了しました！"
    elif not success:
        msg += "\n🚨 致命的なエラーにより、途中で処理を中断しました。ログを確認してください。"
    else:
        msg += "\n⚠️ 一部のステップでエラーが発生しましたが、モデルの再学習は完了しました。"
        
    # WEBHOOK URL の決定 (DISCORD_REPORT_WEBHOOK_URL -> DISCORD_WEBHOOK_URL)
    webhook_url = getattr(config, 'DISCORD_REPORT_WEBHOOK_URL', None)
    if not webhook_url:
        webhook_url = getattr(config, 'DISCORD_WEBHOOK_URL', None)
        
    if webhook_url:
        send_discord_webhook(msg, webhook_url)
        print("-> Sent update report to Discord.")
    else:
        print("[WARN] Discord Webhook URL not set in config.")

def main():
    parser = argparse.ArgumentParser(description="KeibaAI Model Auto-Update Tool")
    parser.add_argument('--date', nargs='+', help="Specific dates to scrape (YYYYMMDD). Can specify multiple.")
    args = parser.parse_args()

    print(f"--- KeibaAI Model Auto-Update Tool ---")
    print(f"Started at: {dt.now()}")
    print(f"Target Project Root: {PROJECT_ROOT}")

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
    
    start_time = time.time()
    python_exe = sys.executable

    # ステータス追跡用辞書
    step_results = {
        "Step 0: レース結果/配当更新": False,
        "Step 1: 直近週末データ取得": False,
        "Step 2: 特徴量データ構築": False,
        "Step 3: 芝・単勝モデル学習": False,
        "Step 3: ダート・単勝モデル学習": False,
        "Step 3: 芝·複勝モデル学習": False,
        "Step 3: ダート·複勝モデル学習": False,
        "Step 4: 年間収支レポート送信": False,
    }

    # ターゲット日付リスト
    target_dates = []

    # --- 0. Update DB Race Results (未確定結果の収集・DB反映) ---
    cmd_update_results = [python_exe, os.path.join(CODE_DIR, 'prediction', 'update_results.py')]
    if run_command(cmd_update_results, "Step 0/4: Updating DB Race Results (Payouts/Ranks)"):
        step_results["Step 0: レース結果/配当更新"] = True
    else:
        print("[WARN] Failed to update some race results. Continuing anyway...")

    # --- 1. Scraping (最新データ取得の高速化) ---
    cmd_scraping = [python_exe, os.path.join(CODE_DIR, 'data_collection', 'scraper_main.py')]
    
    if args.date:
        target_dates = args.date
        cmd_scraping.extend(['--date'] + target_dates)
        print(f"[INFO] Scraping mode: Date-specific manually requested ({target_dates})")
    else:
        recent_weekends = get_recent_weekend_dates()
        if recent_weekends:
            target_dates = recent_weekends
            cmd_scraping.extend(['--date'] + target_dates)
            print(f"[INFO] Scraping mode: Auto-detected recent weekend dates -> {target_dates}")
        else:
            print(f"[WARN] Failed to auto-detect weekend dates. Scraping full period...")
            
    if run_command(cmd_scraping, "Step 1/4: Scraping Latest Weekend Data"):
        step_results["Step 1: 直近週末データ取得"] = True
    else:
        print("Aborting update process due to scraping failure.")
        send_update_report(step_results, start_time, success=False)
        return

    # --- 2. Build Training Data (特徴量生成) ---
    cmd_build = [python_exe, os.path.join(CODE_DIR, 'features', 'build_features.py')]
    if run_command(cmd_build, "Step 2/4: Building Training Data"):
        step_results["Step 2: 特徴量データ構築"] = True
    else:
        print("Aborting update process due to feature building failure.")
        send_update_report(step_results, start_time, success=False)
        return

    # --- 3. Train Models (本番モデル再学習) ---
    print("\n--- Step 3/4: Training Production Models ---")
    targets = [
        {'target': 'win', 'track': 'turf', 'key': 'Step 3: 芝・単勝モデル学習'},
        {'target': 'win', 'track': 'dirt', 'key': 'Step 3: ダート・単勝モデル学習'},
        {'target': 'place', 'track': 'turf', 'key': 'Step 3: 芝·複勝モデル学習'},
        {'target': 'place', 'track': 'dirt', 'key': 'Step 3: ダート·複勝モデル学習'},
    ]
    
    for t in targets:
        description = f"Training Model: {t['track'].upper()} - {t['target'].upper()}"
        cmd_train = [
            python_exe, 
            os.path.join(CODE_DIR, 'training', 'train_model.py'),
            '--mode', 'prod',
            '--target', t['target'],
            '--track', t['track']
        ]
        
        if run_command(cmd_train, description):
            step_results[t['key']] = True
        else:
            print(f"[WARN] Failed to update model for {t['track']}/{t['target']}. Continuing to next model...")

    # --- 4. Generate Daily Performance Report ---
    print("\n--- Step 4/4: Generating Annual Budget Performance Report ---")
    cmd_report = [python_exe, os.path.join(CODE_DIR, 'analysis', 'generate_annual_budget_report.py')]
    if run_command(cmd_report, "Step 4/4: Generating/Sending Annual Budget Report"):
        step_results["Step 4: 年間収支レポート送信"] = True

    # 最終的な Discord レポート送信
    send_update_report(step_results, start_time, success=True)

    # --- 終了時データベース同期 (Local -> Cloud) ---
    try:
        from utils.db_sync import get_sqlite_conn, get_pg_conn, sync_sqlite_to_pg
        print("\n[DB SYNC] 終了時データベース同期 (Local -> Cloud) を実行中...")
        sqlite_conn = get_sqlite_conn()
        pg_conn = get_pg_conn()
        sync_sqlite_to_pg(sqlite_conn, pg_conn)
        sqlite_conn.close()
        pg_conn.close()
        print("[DB SYNC] 終了時同期完了。\n")
    except Exception as e:
        print(f"[DB SYNC WARN] 終了時データベース同期に失敗しました: {e}\n")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"ALL PROCESSES FINISHED.")
    print(f"Total Time: {elapsed//60:.0f} min {elapsed%60:.0f} sec")
    print(f"{'='*60}")
    print("Please verify the logs above.")

if __name__ == "__main__":
    main()
