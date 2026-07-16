import os
import sys
import re
import time
import argparse
from datetime import datetime

# ==========================================================
# --- プロジェクトルートとsrcを最優先でパスに追加 ---
# ==========================================================
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if os.path.join(PROJECT_ROOT, 'src') not in sys.path:
    sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# 共通設定と、昨日完成した「通信＆キャッシュクラス」をインポート
import config
from data_collection.html_downloader import HTMLDownloader

def run_html_history_scraper(start_year: int, end_year: int, wait_time: float):
    """過去の全レースHTMLを一括ダウンロードしてキャッシュ保存するメインロジック"""
    
    print("\n" + "="*70)
    print(f" 🚀 【HTML一括収集ミッション】開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   ・対象期間  : {start_year} 年 〜 {end_year - 1} 年")
    print(f"   ・待機時間  : {wait_time} 秒（リクエスト毎に厳守）")
    print(f"   ・安全装置  : レジューム機能、通信リトライ、404自動判定ループ抜け搭載")
    print("="*70 + "\n")
    
    # HTMLDownloader の初期化
    downloader = HTMLDownloader(save_dir="data/raw_html", wait_time=wait_time)
    
    # 統計用カウンター
    total_requested = 0
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0
    
    start_time = time.time()

    # 年ループ（例: 1990年から2026年まで）
    for year in range(start_year, end_year):
        print(f"\n==================== 📂 対象年: {year}年 ====================")
        
        # 競馬場ループ（configから取得。例: 札幌('01')〜小倉('10')）
        for place_id, place_name in config.PLACE_MAP.items():
            print(f"\n== 🏇 競馬場: {place_name} ({place_id}) ==")
            
            for kai in range(1, 7):        # 開催回（1回〜最大6回）
                for nichi in range(1, 13):    # 開催日（1日〜最大12日）
                    day_has_no_race_counter = 0  # その日の404エラー連続発生カウンター
                    
                    for race_num in range(1, 13): # レース番号（1R〜12R）
                        # 12桁のレースIDを組み立てる (例: 202305010101)
                        race_id = f"{year}{place_id}{kai:02d}{nichi:02d}{race_num:02d}"
                        
                        # 1. 【安全装置：レジューム機能】すでにファイルがあるか確認
                        file_path = downloader._get_file_path(race_id)
                        if os.path.exists(file_path):
                            # ローカルにある場合はネットにアクセスせず、一瞬でスキップ！
                            total_skipped += 1
                            day_has_no_race_counter = 0  # レースが存在しているためカウンターをリセット
                            continue
                        
                        # 2. まだローカルにない場合は、ネットからダウンロード
                        total_requested += 1
                        try:
                            # ネットから取得してキャッシュ保存する (get_htmlメソッドを呼び出し)
                            html_content = downloader.get_html(race_id)
                            
                            if html_content is None:
                                # レースが見つからない (404)
                                day_has_no_race_counter += 1
                                # 3連続でレースが見つからない場合は、その開催日のそれ以降のレースはないとみなしてループを抜ける（超高速化）
                                if day_has_no_race_counter >= 3:
                                    break
                                continue
                            
                            # 取得に成功
                            day_has_no_race_counter = 0
                            total_downloaded += 1
                            
                            # コンソールに進捗を表示
                            elapsed_min = (time.time() - start_time) / 60
                            print(f"[SUCCESS] Downloaded {race_id} ({place_name} {kai}回{nichi}日目 {race_num}R) | 累計新規: {total_downloaded}枚 | 経過時間: {elapsed_min:.1f}分")
                            
                        except KeyboardInterrupt:
                            # 会社に行く前に手動で止めたい場合（Ctrl + C）
                            print("\n\n[USER INTERRUPT] ユーザーによって処理が中断されました。進捗を安全に保存して終了します。")
                            _print_summary(total_requested, total_downloaded, total_skipped, total_failed, start_time)
                            sys.exit(0)
                            
                        except Exception as e:
                            # 通信の瞬断など、予期せぬエラーが起きても処理を絶対に止めない！
                            print(f"\n[ERROR] レース {race_id} の取得中にエラーが発生しました: {e}. スキップして続行します。")
                            total_failed += 1
                            continue

    print("\n" + "="*70)
    print(" 🎉 【ミッションコンプリート】指定された全期間のHTMLデータ収集が完了しました！")
    _print_summary(total_requested, total_downloaded, total_skipped, total_failed, start_time)
    print("="*70 + "\n")

def _print_summary(requested, downloaded, skipped, failed, start_time):
    elapsed = time.time() - start_time
    print(f"   ・新規ダウンロード枚数: {downloaded} 枚")
    print(f"   ・スキップ（保存済み） : {skipped} 枚 (二重取得なし)")
    print(f"   ・失敗（エラー数）     : {failed} 枚")
    print(f"   ・総リクエスト回数    : {requested} 回")
    print(f"   ・合計所要時間        : {elapsed//60:.0f} 分 {elapsed%60:.0f} 秒")

def main():
    parser = argparse.ArgumentParser(description="Netkeiba HTML Safe History Batch Downloader")
    parser.add_argument('--start-year', type=int, default=config.SCRAPE_START_YEAR, help="ダウンロードを開始する年 (デフォルト: config値)")
    parser.add_argument('--end-year', type=int, default=config.SCRAPE_END_YEAR, help="ダウンロードを終了する年 (デフォルト: config値)")
    parser.add_argument('--wait', type=float, default=1.0, help="リクエスト間のウェイト秒数 (デフォルト: 1.0秒)")
    
    args = parser.parse_args()
    
    run_html_history_scraper(args.start_year, args.end_year, args.wait)

if __name__ == "__main__":
    main()
