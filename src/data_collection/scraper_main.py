import os
import sys
import re
import argparse
from typing import List, Optional, Dict, Any

# ==========================================================
# --- プロジェクトルートとsrcを【最優先】でパスに追加 ---
# この位置に書くことで、どのディレクトリから実行してもModuleNotFoundErrorを防ぎます！
# ==========================================================
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if os.path.join(PROJECT_ROOT, 'src') not in sys.path:
    sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# クリーンオブジェクト指向パーツと設定情報のインポート
import config
from data_collection.html_downloader import HTMLDownloader
from data_collection.netkeiba_parser import NetkeibaParser
from data_collection.race_data_writer import RaceDataWriter

def update_database_from_offline(db_path: str, race_id: str, results_list: List[Dict[str, Any]], payouts_data: dict):
    """オフラインで解析された馬成績リストと払い戻し情報で、predictions.dbを更新する"""
    import sqlite3
    if not results_list:
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # payouts テーブルが存在することを確認（無ければ作成）
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS payouts (
                race_id TEXT PRIMARY KEY, tansho_payout INTEGER, tansho_numbers TEXT,
                fukusho_payouts TEXT, wakuren_payout INTEGER, wakuren_numbers TEXT,
                umaren_payout INTEGER, umaren_numbers TEXT, wide_payouts TEXT,
                umatan_payout INTEGER, umatan_numbers TEXT, sanrenpuku_payout INTEGER,
                sanrenpuku_numbers TEXT, sanrentan_payout INTEGER, sanrentan_numbers TEXT
            );
            """)
            conn.commit()
            
            # 1. predictions テーブルの更新
            # レースIDと馬番に一致する既存の予測レコードがある場合のみ、着順、オッズ、人気を上書き更新します。
            # 予測データが無い過去のレースはインサートされません。
            update_count = 0
            for row in results_list:
                try:
                    rank_str = str(row.get('rank', '99')).strip()
                    rank = int(rank_str) if rank_str.isdigit() else 99
                except ValueError:
                    rank = 99
                
                try:
                    odds = float(str(row.get('odds', '0.0')).strip())
                except ValueError:
                    odds = 0.0
                
                try:
                    pop_str = str(row.get('pop', '0')).strip()
                    pop = int(pop_str) if pop_str.isdigit() else 0
                except ValueError:
                    pop = 0
                
                try:
                    umaban = int(row.get('umaban'))
                except (ValueError, TypeError):
                    continue
                
                query = """
                UPDATE predictions 
                SET result_rank = ?, tansho_odds = ?, tansho_ninki = ? 
                WHERE race_id = ? AND umaban = ?;
                """
                cursor.execute(query, (rank, odds, pop, race_id, umaban))
                update_count += cursor.rowcount
            
            # 2. payouts テーブルへの挿入 (INSERT OR REPLACE)
            # 払い戻し情報は過去の全レースについて完璧に保存します。
            if payouts_data:
                payouts_data['race_id'] = race_id
                columns = ', '.join(payouts_data.keys())
                placeholders = ', '.join(['?'] * len(payouts_data))
                query = f"INSERT OR REPLACE INTO payouts ({columns}) VALUES ({placeholders});"
                cursor.execute(query, list(payouts_data.values()))
                
            conn.commit()
            if update_count > 0:
                print(f"  -> [DB] predictionsテーブルを {update_count} 件更新しました。")
            if payouts_data:
                print(f"  -> [DB] payoutsテーブルに払い戻し情報を保存しました。")
    except Exception as e:
        print(f"  [DB ERROR] データベース更新中にエラーが発生しました: {e}")

class ScrapingController:
    """データ収集のライフサイクル（通信 ➔ パース ➔ 保存）を一元管理するコントローラークラス。
    
    JavaのMVCモデルにおける「C (Controller)」に相当し、
    コマンド引数や起動モードに応じて、Downloader、Parser、Writer を協調動作させます。
    """
    
    def __init__(self, raw_data_dir: str = "data/raw", html_cache_dir: str = "data/raw_html", wait_time: float = 1.0):
        """コンストラクタ（依存クラスの生成と初期化）
        
        Javaでいう「依存性注入（Dependency Injection）」に相当し、
        他の役割を持ったインスタンスを生成して内部で保持（コンポジション）します。
        
        Args:
            raw_data_dir (str): CSVを保存するフォルダ
            html_cache_dir (str): HTMLをキャッシュするフォルダ
            wait_time (float): ダウンロードの待機時間
        """
        self.downloader = HTMLDownloader(save_dir=html_cache_dir, wait_time=wait_time)
        self.writer = RaceDataWriter(save_dir=raw_data_dir)
        local_raw_dir = os.path.join(config.DATA_DIR, "local", "raw")
        self.local_writer = RaceDataWriter(save_dir=local_raw_dir)
        self.wait_time = wait_time

    def _process_single_race(self, race_id: str) -> List[Dict[str, Any]]:
        """単一のレースIDに対して「ダウンロード ➔ パース」の連携フローを実行する内部メソッド。
        
        このコントローラーの心臓部であり、3つのパーツがここで見事にコラボレーションします！
        """
        # 1. Downloaderを使ってHTML文字列を取得（キャッシュがあれば一瞬、なければ通信）
        html_content = self.downloader.get_html(race_id)
        if not html_content:
            return []

        # 2. Parserを使ってHTMLを解析し、構造化された成績リストに変換する
        parser = NetkeibaParser(html_content)
        horse_results = parser.get_horse_results(race_id)
        
        return horse_results

    def run_single_race_id_base(self, race_id_base: str):
        """特定のレースIDベース (例: 2025060403) に紐づく1R〜12Rのデータを収集・保存する"""
        if not re.fullmatch(r'\d{10}', race_id_base):
            print(f"[ERROR] 無効なレースIDベース形式です: {race_id_base}. 10桁の数字(YYYYPPCCDD)を指定してください。")
            return

        year = race_id_base[0:4]
        print(f"\n--- Processing 1R to 12R for race_id_base: {race_id_base} ---")
        
        all_race_results = []
        day_has_no_race_counter = 0

        # 1Rから12Rまでループ処理
        for race_num in range(1, 13):
            race_id = f"{race_id_base}{race_num:02d}"
            
            # 各レースのデータを「ダウンロード ➔ パース」
            results = self._process_single_race(race_id)
            
            if not results:
                # 3連続でレースが見つからない場合は、その日の開催レースは終了とみなしてブレイク
                day_has_no_race_counter += 1
                if day_has_no_race_counter >= 3:
                    print(f"\n[INFO] {race_num-1}R以降のレースが見つかりません。ループを終了します。")
                    break
                continue
            
            day_has_no_race_counter = 0
            all_race_results.extend(results)
            print(f"\r[INFO] データをフェッチ中: {race_num:02d}R. 累計レコード数: {len(all_race_results)} 件", end="", flush=True)

        # 3. 集まった1日分の全レースデータを、Writerを使ってCSVに一括書き出し！
        if all_race_results:
            self.writer.write_rows(year, all_race_results)
            print(f">>> {race_id_base} のデータ収集および保存が完了しました！\n")
        else:
            print(f"[WARN] {race_id_base} のデータは1件も収集されませんでした。\n")

    def run_date_specific(self, dates: List[str]):
        """指定された日付リスト (YYYYMMDD) の全レースをスクレイピングして保存する"""
        import requests
        from bs4 import BeautifulSoup
        
        print(f"\n--- 指定日付のスクレイピングを開始します: {dates} ---")
        
        for date_str in dates:
            if not re.fullmatch(r'\d{8}', date_str):
                print(f"[WARN] 無効な日付形式です: {date_str}. スキップします。")
                continue
                
            year = date_str[:4]
            url = f"https://db.netkeiba.com/race/list/{date_str}/"
            print(f"[INFO] 日付 {date_str} のレース一覧を取得中: {url}")
            
            try:
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                r.raise_for_status()
                
                import time
                time.sleep(self.wait_time)
                soup = BeautifulSoup(r.content.decode("euc-jp", "ignore"), "html.parser")
                
                # レース一覧から個々の12桁のレースIDを抽出
                race_ids = []
                seen = set()
                for a in soup.find_all("a", href=True):
                    match = re.search(r'/race/(\d{12})/', a['href'])
                    if match:
                        rid = match.group(1)
                        if rid not in seen:
                            race_ids.append(rid)
                            seen.add(rid)
                race_ids.sort()
                print(f"[INFO] 日付 {date_str} から {len(race_ids)} 件のレースが見つかりました。")
                
                # 各レースIDを処理して、1日分の全データを集める
                jra_results = []
                local_results = []
                for rid in race_ids:
                    results = self._process_single_race(rid)
                    place_id = rid[4:6]
                    if place_id in config.PLACE_MAP:
                        jra_results.extend(results)
                    else:
                        local_results.extend(results)
                
                # CSVにそれぞれ保存
                if jra_results:
                    self.writer.write_rows(year, jra_results)
                    print(f">>> 日付 {date_str} の中央競馬データ収集および保存が完了しました！\n")
                if local_results:
                    self.local_writer.write_rows(year, local_results)
                    print(f">>> 日付 {date_str} の地方競馬データ収集および保存が完了しました！\n")
                    
            except Exception as e:
                print(f"[ERROR] 日付 {date_str} のレース一覧取得に失敗しました: {e}")
                continue

    def run_full_period(self, start_year: int, end_year: int):
        """YEAR_STARTからYEAR_END-1までの全期間の全レース結果をループで処理して保存する"""
        print(f"\n--- 全期間の一括スクレイピングを開始します: {start_year}年 〜 {end_year-1}年 ---")
        
        for year in range(start_year, end_year):
            print(f"\n==================== 対象年: {year}年 ====================")
            year_results = []
            
            for place_id, place_name in config.PLACE_MAP.items():
                print(f"== 競馬場: {place_name} の処理を開始 ==")
                for kai in range(1, 7):      # 開催回（最大6回）
                    for nichi in range(1, 13):  # 開催日（最大12日）
                        day_has_no_race_counter = 0
                        day_results = []
                        
                        for race_num in range(1, 13): # レース番号（1R〜12R）
                            # 12桁のレースIDを組み立てる (例: 202305010101)
                            race_id = f"{year}{place_id}{kai:02d}{nichi:02d}{race_num:02d}"
                            
                            # 通信 ➔ 解析
                            results = self._process_single_race(race_id)
                            
                            if not results:
                                day_has_no_race_counter += 1
                                if day_has_no_race_counter >= 3:
                                    break
                                continue
                                
                            day_has_no_race_counter = 0
                            day_results.extend(results)
                            print(f"\r[INFO] フェッチ中: {place_name} 開催{kai}回-{nichi}日目 {race_num}R. 累計レコード数: {len(day_results)} 件", end="", flush=True)
                        
                        # 1日分のデータが集まったら年ごとの一時バッファに結合
                        if day_results:
                            year_results.extend(day_results)
                            print() # 改行
            
            # その年の全データ収集が完了したら、一気にその年のCSVファイルに書き込む！
            if year_results:
                self.writer.write_rows(str(year), year_results)
                print(f">>> {year}年の全データ収集および保存が完了しました！\n")

    def run_year_offline(self, year: int, db_sync: bool = False, test_csv: bool = False):
        """指定された年(YYYY)のローカルHTMLキャッシュをスキャンして解析・保存・同期する"""
        print(f"\n==================== オフライン解析対象年: {year}年 ====================")
        year_results = []
        
        # 1年分の競馬場・開催・日の組み合わせをループ処理
        for place_id, place_name in config.PLACE_MAP.items():
            print(f"== 競馬場: {place_name} のオフライン処理を開始 ==")
            for kai in range(1, 7):      # 開催回（最大6回）
                for nichi in range(1, 13):  # 開催日（最大12日）
                    day_has_no_race_counter = 0
                    day_results = []
                    
                    for race_num in range(1, 13): # レース番号（1R〜12R）
                        race_id = f"{year}{place_id}{kai:02d}{nichi:02d}{race_num:02d}"
                        
                        # ローカルHTMLが存在するか確認
                        file_path = self.downloader._get_file_path(race_id)
                        if not os.path.exists(file_path):
                            day_has_no_race_counter += 1
                            if day_has_no_race_counter >= 3:
                                break
                            continue
                        
                        day_has_no_race_counter = 0
                        
                        # 1. HTMLの読み込みとパース
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                html_content = f.read()
                            
                            parser = NetkeibaParser(html_content)
                            results = parser.get_horse_results(race_id)
                            
                            if results:
                                day_results.extend(results)
                                print(f"\r[INFO] パース完了: {place_name} {kai}回-{nichi}日目 {race_num}R (レコード数: {len(results)}件)", end="", flush=True)
                                
                                # 2. DBへの同期処理
                                if db_sync:
                                    payouts = parser.get_payouts()
                                    update_database_from_offline(config.DB_PATH, race_id, results, payouts)
                        except Exception as e:
                            print(f"\n[ERROR] レース {race_id} のオフライン解析中にエラーが発生しました: {e}")
                            continue
                        
                    if day_results:
                        year_results.extend(day_results)
                        print() # 改行
        
        # 3. CSVへの書き込み
        if year_results:
            suffix = "_parsed" if test_csv else ""
            csv_filename = f"{year}{suffix}"
            self.writer.write_rows(csv_filename, year_results)
            print(f"\n>>> {year}年のオフライン解析と保存が完了しました！ ({len(year_results)}件のレコード)\n")
        else:
            print(f"\n[WARN] {year}年のHTMLデータは見つかりませんでした。\n")

def main():
    # 引数処理
    parser = argparse.ArgumentParser(description="Netkeiba Clean Object-Oriented Scraping Engine")
    parser.add_argument('race_id_base', nargs='?', help="特定のレースIDベース (10桁: YYYYPPCCDD) を指定して1日分のみ取得")
    parser.add_argument('--date', nargs='+', help="特定の日付 (形式: YYYYMMDD) を指定して取得（複数指定可）")
    parser.add_argument('--year', type=int, help="オフライン解析する特定の年 (例: 2026)")
    parser.add_argument('--db-sync', action='store_true', help="解析した結果をpredictions.dbに同期する")
    parser.add_argument('--test-csv', action='store_true', help="元のファイルを上書きせず、YYYY_parsed.csvとして出力する")
    
    args = parser.parse_args()

    # コントローラーの初期化（config設定を一元適用して本番用に出力）
    controller = ScrapingController(
        raw_data_dir=config.RAW_DATA_DIR,
        html_cache_dir="data/raw_html",
        wait_time=1.0
    )

    if args.year:
        controller.run_year_offline(args.year, db_sync=args.db_sync, test_csv=args.test_csv)
    elif args.date:
        controller.run_date_specific(args.date)
    elif args.race_id_base:
        controller.run_single_race_id_base(args.race_id_base)
    else:
        # 引数なしの場合は、config に設定された全期間を実行
        controller.run_full_period(config.SCRAPE_START_YEAR, config.SCRAPE_END_YEAR)

if __name__ == "__main__":
    main()
