"""
地方・海外レースデータ抽出スクリプト (extract_local_overseas.py)

■ 役割
2025年のJRAレースに出走する馬（`data/2025.csv`に含まれる馬）を対象に、
過去の全戦績をスクレイピングし、その中から「地方競馬」および「海外競馬」のレースデータのみを抽出する。
抽出されたデータは、JRAデータと同じカラム構成（一部ダミー値）に整形され、
将来的なモデル学習や特徴量エンジニアリング（m02）で利用可能な形式で保存される。

■ 主な機能
1. `data/2025.csv` から対象馬リストと馬主情報を読み込む。
2. 各馬の競走馬データベースページから過去走データをスクレイピングする。
3. JRA以外のレース（地方・海外）をフィルタリングする。
4. カラム名をJRAデータ形式（`走破時間`, `通過順`, `体重` など）に統一・整形する。
5. 不足データ（クラス、場IDなど）を補完またはダミー値で埋める。
6. 中断・再開機能（`--resume`）と増分保存機能。
   - `scrape_status.json` で各馬の最終スクレイピング日時を管理。
   - 10頭ごとにCSVとステータスを保存し、クラッシュ時のデータ損失を防ぐ。

■ 使い方
python code/a1_data_collection/extract_local_overseas.py [--resume]

オプション:
  --resume: 過去24時間以内にスクレイピングされた馬をスキップします。
            中断した処理を再開する場合に便利です。
            定期更新などで最新データを取得したい場合は指定しないでください。

※ 事前に `m01_scraping.py` を実行して `data/2025.csv` を作成しておく必要があります。
"""
import pandas as pd
import os
import sys
import time
import re
import json
import argparse
import datetime
from tqdm import tqdm


# Setup path to import from code directory
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import config
from a1_data_collection.scrape_horse_past_races import scrape_all_past_races_from_horse_page

STATUS_FILE = os.path.join(config.DATA_DIR, 'kaigai', 'scrape_status.json')
RESUME_THRESHOLD_HOURS = 24

def load_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_status(status):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=4)

def parse_class_from_race_name(race_name):
    """レース名からクラス（G1, Jpn1など）を抽出する簡易ロジック"""
    if pd.isna(race_name): return pd.NA
    
    # G1, G2, G3, GⅠ, GⅡ, GⅢ, Jpn1, Jpn2, Jpn3 などを抽出
    # カッコ書きの中にあることが多い: "ドバイシーマクラシック(G1)"
    match = re.search(r'\((G[1-3I-IIIⅠ-Ⅲ]|Jpn[1-3])\)', str(race_name), re.IGNORECASE)
    if match:
        return match.group(1)
    
    # カッコなしの場合も考慮（必要なら追加）
    return pd.NA

def extract_local_and_overseas_past_races(horse_id_list: list, owner_map: dict, output_path: str, resume_mode: bool):
    """
    指定されたhorse_idのリストに対して過去走をスクレイピングし、
    地方・海外レース（is_jra_race=False）のみを抽出して保存する。
    """
    print(f"--- Starting extraction for {len(horse_id_list)} horses (Resume Mode: {resume_mode}) ---")
    
    # 既存データのロード
    if os.path.exists(output_path):
        try:
            existing_df = pd.read_csv(output_path, encoding='SHIFT-JIS', dtype={'horse_id': str})
            print(f"Loaded existing data: {len(existing_df)} rows")
        except Exception as e:
            print(f"[WARN] Failed to load existing CSV: {e}. Starting fresh.")
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    status = load_status()
    processed_count = 0
    updated_horses_count = 0
    
    # 保存用バッファ（DataFrame操作を減らすため）
    # ただし、既存削除 -> 新規追加 のロジックなので、今回は既存dfを直接操作する方針にする
    # データ量が巨大な場合はバッファ式が良いが、今回の規模なら都度concatでも許容範囲か、あるいはリストに貯めて定期マージ。
    # ここでは「10頭ごとに existing_df を更新して保存」する。
    
    current_batch_records = []
    horses_in_batch = []

    for i, horse_id in enumerate(tqdm(horse_id_list, desc="Processing horses")):
        
        # Resume Check
        if resume_mode:
            last_scraped_str = status.get(horse_id)
            if last_scraped_str:
                last_scraped = datetime.datetime.fromisoformat(last_scraped_str)
                if datetime.datetime.now() - last_scraped < datetime.timedelta(hours=RESUME_THRESHOLD_HOURS):
                    continue # Skip recent

        # URL生成
        horse_url = f"https://db.netkeiba.com/horse/result/{horse_id}/"
        
        # スクレイピング実行 (MAX 50レース取得)
        try:
            df = scrape_all_past_races_from_horse_page(horse_id, horse_url, max_races=50)
            status[horse_id] = datetime.datetime.now().isoformat()
            horses_in_batch.append(horse_id)
            processed_count += 1
        except Exception as e:
            print(f"\n[ERROR] Failed to scrape {horse_id}: {e}")
            continue
        
        if df is not None and not df.empty:
            # 地方・海外レースのみ抽出
            non_jra_df = df[df['is_jra_race'] == False].copy()
            
            if not non_jra_df.empty:
                updated_horses_count += 1
                
                # --- カラム名の変更と調整 (Previous Logic) ---
                rename_map = {
                    'num_horses': '頭数', 'passing_order': '通過順', 'runtime': '走破時間',
                    'weight': '体重', 'weight_dif': '体重変化', 'wakuban': '枠番', 'prize_money': '賞金'
                }
                if '馬体重' in non_jra_df.columns: non_jra_df.rename(columns={'馬体重': '体重'}, inplace=True)
                
                # 不足カラムの追加・加工
                non_jra_df['クラス'] = non_jra_df['レース名'].apply(parse_class_from_race_name)
                non_jra_df['場id'] = '99' 
                non_jra_df['馬主'] = owner_map.get(horse_id, pd.NA)
                non_jra_df['owner_id'] = pd.NA
                non_jra_df['race_id'] = 'local_overseas' 
                non_jra_df['馬'] = pd.NA
                non_jra_df['調教師'] = pd.NA
                non_jra_df['trainer_id'] = pd.NA
                non_jra_df['jockey_id'] = pd.NA
                non_jra_df['回り'] = pd.NA
                
                target_columns = [
                    'race_id', '馬', 'horse_id', '騎手', 'jockey_id', '馬番', '走破時間', 'オッズ', 
                    '通過順', '着順', '体重', '体重変化', '性', '齢', '斤量', '上がり', '人気', 
                    'レース名', '日付', '開催', 'クラス', '芝・ダート', '距離', '回り', '馬場', '天気', 
                    '場id', '場名', '調教師', 'trainer_id', '馬主', 'owner_id', '賞金',
                    '頭数', '枠番', 'ペース', '厩舎'
                ]
                
                for col in target_columns:
                    if col not in non_jra_df.columns: non_jra_df[col] = pd.NA
                
                filtered_df = non_jra_df[target_columns]
                current_batch_records.append(filtered_df)

        # 10頭ごとに保存 (Incremental Save)
        if len(horses_in_batch) >= 10:
            existing_df = update_and_save(existing_df, current_batch_records, horses_in_batch, output_path, status)
            current_batch_records = []
            horses_in_batch = []
        
        # サーバー負荷軽減のための待機 (1.0秒)
        time.sleep(1.0)
            
    # 最後のバッファを保存
    if horses_in_batch:
        existing_df = update_and_save(existing_df, current_batch_records, horses_in_batch, output_path, status)

    print(f"--- Finished. Processed {processed_count} horses. Found non-JRA races for {updated_horses_count} horses. ---")

def update_and_save(main_df, new_records_list, horse_ids_processed, output_path, status):
    """
    既存DataFrameから処理済み馬のデータを削除し、新しいデータを追加して保存する。
    """
    # 1. 処理済み馬の既存データを削除 (Update Logic)
    if not main_df.empty:
        # horse_id は object または float/int の可能性があるため文字列に統一して比較
        main_df['horse_id'] = main_df['horse_id'].astype(str)
        main_df = main_df[~main_df['horse_id'].isin(horse_ids_processed)]
    
    # 2. 新しいデータを追加
    if new_records_list:
        new_df = pd.concat(new_records_list, ignore_index=True)
        new_df['horse_id'] = new_df['horse_id'].astype(str)
        main_df = pd.concat([main_df, new_df], ignore_index=True)
        
    # 3. CSV保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    main_df.to_csv(output_path, index=False, encoding='SHIFT-JIS')
    
    # 4. ステータス保存
    save_status(status)
    
    return main_df

def main():
    parser = argparse.ArgumentParser(description="Extract local/overseas race data.")
    parser.add_argument('--resume', action='store_true', help="Skip horses scraped within last 24h.")
    args = parser.parse_args()

    # 1. 2025年の出走馬リストと馬主情報を取得
    source_file = os.path.join(config.RAW_DATA_DIR, '2025.csv')
    if not os.path.exists(source_file):
        print(f"[ERROR] Source file {source_file} not found. Please run scraping first.")
        return

    print(f"Loading horse list from {source_file}...")
    try:
        df_2025 = pd.read_csv(source_file, encoding='SHIFT-JIS', usecols=['horse_id', '馬主'], dtype={'horse_id': str, '馬主': str})
        horse_id_list = df_2025['horse_id'].unique().tolist()
        owner_map = df_2025.drop_duplicates(subset=['horse_id'], keep='last').set_index('horse_id')['馬主'].to_dict()
        print(f"Found {len(horse_id_list)} unique horses.")
    except Exception as e:
        print(f"[ERROR] Failed to read {source_file}: {e}")
        return

    # 2. 抽出実行
    output_path = os.path.join(config.DATA_DIR, 'kaigai', 'local_overseas_past_races_2025.csv')
    extract_local_and_overseas_past_races(horse_id_list, owner_map, output_path, args.resume)

if __name__ == "__main__":
    main()
