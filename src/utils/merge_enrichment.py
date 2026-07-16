
"""
enrich_race_data.py で取得した拡充データ（data/enrichment_YYYY.csv）を
既存のメインデータ（data/YYYY.csv）に結合（マージ）するスクリプト。

機能:
1. 対象の年の `data/YYYY.csv` と `data/enrichment_YYYY.csv` を読み込む。
2. `race_id` をキーにして左結合 (Left Join) する。
   - メインデータにある全行に対し、該当する race_id の拡充データ（コーナー通過順、ラップ、ペース）を付与する。
3. 結合結果を `data/YYYY.csv` に上書き保存する。
   - 安全のため、元のファイルは `data/YYYY.csv.bak` としてバックアップする。

使い方:
python code/utils/merge_enrichment.py --year 2024
python code/utils/merge_enrichment.py --start 2010 --end 2024
"""

import os
import sys
import pandas as pd
import shutil
import argparse

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
import config

def merge_year(year):
    main_csv = os.path.join(config.DATA_DIR, f"{year}.csv")
    enrich_csv = os.path.join(config.DATA_DIR, f"enrichment_{year}.csv")

    if not os.path.exists(main_csv):
        print(f"[SKIP] Main data not found: {main_csv}")
        return
    if not os.path.exists(enrich_csv):
        print(f"[SKIP] Enrichment data not found: {enrich_csv}")
        return

    print(f"--- Merging data for {year} ---")

    # 1. データ読み込み (Shift-JIS / cp932)
    try:
        df_main = pd.read_csv(main_csv, encoding='cp932', low_memory=False)
        df_enrich = pd.read_csv(enrich_csv, encoding='cp932')
    except Exception as e:
        print(f"[ERROR] Failed to read CSVs for {year}: {e}")
        return

    # 2. 結合前のチェック
    initial_len = len(df_main)
    print(f"  Main rows: {len(df_main)}, Enrich races: {len(df_enrich)}")

    # race_idを文字列型に統一
    df_main['race_id'] = df_main['race_id'].astype(str)
    df_enrich['race_id'] = df_enrich['race_id'].astype(str)

    # 既存のカラムと被る場合は、拡充側を優先するか元のままにするか
    # ここでは「拡充データ側」のカラムがメインデータに既にある場合（m01を実行し直した場合など）、
    # いったん削除してからマージして更新する戦略を取る
    enrich_cols = [c for c in df_enrich.columns if c != 'race_id']
    for col in enrich_cols:
        if col in df_main.columns:
            print(f"  [INFO] Column '{col}' already exists in main data. Overwriting with enrichment data.")
            df_main.drop(columns=[col], inplace=True)

    # 3. マージ (Left Join)
    # race_id ごとのデータを、メインの各馬データにマージ
    df_merged = pd.merge(df_main, df_enrich, on='race_id', how='left')

    if len(df_merged) != initial_len:
        print(f"[WARN] Row count changed after merge! {initial_len} -> {len(df_merged)}")
    
    # NaNを空文字に置換 (CSV保存時の挙動など必要に応じて)
    # df_merged.fillna("", inplace=True) # 必要であれば

    # 4. バックアップと保存
    backup_path = f"{main_csv}.bak"
    try:
        shutil.copy2(main_csv, backup_path)
        print(f"  Backup created: {backup_path}")
    except Exception as e:
        print(f"[ERROR] Failed to create backup: {e}")
        return

    try:
        df_merged.to_csv(main_csv, index=False, encoding='cp932', errors='replace')
        print(f"  [SUCCESS] Merged data saved to {main_csv}")
    except Exception as e:
        print(f"[ERROR] Failed to save merged CSV: {e}")
        # 失敗時はバックアップから戻す?
        print("  Restoring from backup...")
        shutil.copy2(backup_path, main_csv)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, help='Specific year to merge')
    parser.add_argument('--start', type=int, help='Start year of range')
    parser.add_argument('--end', type=int, help='End year of range')
    args = parser.parse_args()

    if args.year:
        merge_year(args.year)
    elif args.start and args.end:
        for y in range(args.start, args.end + 1):
            merge_year(y)
    else:
        print("Please specify --year or --start/--end")

if __name__ == "__main__":
    main()
