# code/utils/filter_encoded_by_date.py
# python code/utils/filter_encoded_by_date.py --date 2025-09-30

"""
 - encodedフォルダ内の加工済みデータの中から YYYY-MM-DD 以降のデータを削除する
 手順
 1. m02_build_training_data.pyを実行して全データ加工済みにしておく(1回目のみ)
 2. python code/utils/filter_encoded_by_date.py --date [YYYY-MM-DD]を実行する
 3. モデルの再学習
    - python code/a3_training/m03_train_model.py --mode prod --target win --track turf
    - python code/a3_training/m03_train_model.py --mode prod --target win --track dirt
 4. 対応するレースを予測実行
    - python code/a4_prediction/m04_predict.py [race_id] --no-shap
    - python main_scheduler.py 2025-11-30
 5. 2から繰り返す

Simulate past data availability by filtering encoded data based on a cutoff date.
This enables Walk-Forward Validation (Backtesting).

Usage:
    python code/utils/filter_encoded_by_date.py --date 2024-01-01 --track turf

Logic:
    1. Checks for 'encoded_full_{track}.csv'.
    2. If not found, renames current 'encoded_data_{track}.csv' to 'encoded_full_{track}.csv' (One-time backup).
    3. Loads full data.
    4. Filters: df['日付'] < target_date.
    5. Overwrites 'encoded_data_{track}.csv' with the subset.
"""

import os
import sys
import argparse
import pandas as pd
import shutil

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(project_root)

import config

def filter_data(target_date: str, track: str):
    base_dir = os.path.join(config.ENCODED_DIR, config.EXPERIMENT_VERSION)
    
    if track == 'all':
        tracks = ['turf', 'dirt']
    else:
        tracks = [track]
        
    for t in tracks:
        full_file = os.path.join(base_dir, f"encoded_full_{t}.csv")
        working_file = os.path.join(base_dir, f"encoded_data_{t}.csv")
        
        # 1. Ensure Full Data Exists
        if os.path.exists(full_file):
            print(f"[INFO] Using existing Master Data: {full_file}")
        elif os.path.exists(working_file):
            print(f"[INFO] First run detected. Backing up {working_file} to Master Data: {full_file}")
            shutil.copy2(working_file, full_file)
        else:
            print(f"[ERROR] No data found for {t}. Expected {working_file} or {full_file}")
            continue
            
        # 2. Load Full Data
        try:
            df = pd.read_csv(full_file, low_memory=False)
            if '日付' not in df.columns:
                print(f"[ERROR] '日付' column missing in {full_file}.")
                continue
            df['日付'] = pd.to_datetime(df['日付'])
        except Exception as e:
            print(f"[ERROR] Failed to load {full_file}: {e}")
            continue
            
        # 3. Filter
        cutoff = pd.to_datetime(target_date)
        original_count = len(df)
        
        # Keep data STRICTLY BEFORE target_date (assuming we want to predict target_date onwards)
        # However, user said "指定した日付以降のデータを削除" (Remove independent of date >= date).
        # Usually for training, we use data < race_date.
        # If simulation starts on 2024-01-01, we train on data < 2024-01-01.
        
        df_subset = df[df['日付'] < cutoff].copy()
        subset_count = len(df_subset)
        
        print(f"--- Processing {t.upper()} ---")
        print(f"  Cutoff Date: {cutoff.date()}")
        print(f"  Original Rows: {original_count}")
        print(f"  Subset Rows  : {subset_count}")
        print(f"  Removed Rows : {original_count - subset_count}")
        
        if subset_count == 0:
            print("[WARN] Subset is empty! Check your date.")
        
        # 4. Save to Working File
        df_subset.to_csv(working_file, index=False)
        print(f"  -> Overwritten {working_file} with filtered data.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter encoded data by date for backtesting.")
    parser.add_argument("--date", type=str, required=True, help="Cutoff date (YYYY-MM-DD). Data on or after this date will be removed.")
    parser.add_argument("--track", type=str, default="all", choices=['turf', 'dirt', 'all'], help="Track type to process.")
    
    args = parser.parse_args()
    
    filter_data(args.date, args.track)
