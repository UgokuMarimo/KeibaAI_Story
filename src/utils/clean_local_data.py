import os
import shutil
import pandas as pd
import re

PROJECT_ROOT = r"C:\KeibaAI"
RAW_HTML_DIR = os.path.join(PROJECT_ROOT, "data", "raw_html", "2026")
LOCAL_HTML_DIR = os.path.join(PROJECT_ROOT, "data", "local", "raw_html", "2026")
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "2026.csv")
LOCAL_CSV_DIR = os.path.join(PROJECT_ROOT, "data", "local", "raw")
LOCAL_CSV_PATH = os.path.join(LOCAL_CSV_DIR, "2026.csv")

# 中央競馬の場ID
JRA_PLACE_IDS = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10"}

def clean_html():
    print("--- HTMLファイルのクレンジングを開始します ---")
    if not os.path.exists(RAW_HTML_DIR):
        print(f"HTMLディレクトリが存在しません: {RAW_HTML_DIR}")
        return

    os.makedirs(LOCAL_HTML_DIR, exist_ok=True)
    files = [f for f in os.listdir(RAW_HTML_DIR) if f.endswith(".html")]
    
    moved_count = 0
    for file_name in files:
        # レースIDの抽出 (例: 202654053001.html -> 202654053001)
        race_id = os.path.splitext(file_name)[0]
        if len(race_id) == 12:
            place_id = race_id[4:6]
            if place_id not in JRA_PLACE_IDS:
                src_path = os.path.join(RAW_HTML_DIR, file_name)
                dest_path = os.path.join(LOCAL_HTML_DIR, file_name)
                shutil.move(src_path, dest_path)
                moved_count += 1
                
    print(f"移動完了: {moved_count} 件の地方競馬HTMLファイルを {LOCAL_HTML_DIR} に移動しました。")

def clean_csv():
    print("--- CSVファイルのクレンジングを開始します ---")
    if not os.path.exists(RAW_CSV_PATH):
        print(f"CSVファイルが存在しません: {RAW_CSV_PATH}")
        return

    try:
        # SHIFT-JISで読み込み
        df = pd.read_csv(RAW_CSV_PATH, encoding="SHIFT-JIS", dtype={"race_id": str})
    except Exception as e:
        print(f"CSVの読み込みに失敗しました: {e}")
        return

    # race_idの5-6桁目を取得して判定
    df["place_id"] = df["race_id"].str[4:6]
    
    # 中央と地方に分離
    df_jra = df[df["place_id"].isin(JRA_PLACE_IDS)].copy()
    df_local = df[~df["place_id"].isin(JRA_PLACE_IDS)].copy()
    
    # 一時的なplace_id列を削除
    df_jra.drop(columns=["place_id"], inplace=True)
    df_local.drop(columns=["place_id"], inplace=True)

    # 中央競馬のCSVを上書き保存
    df_jra.to_csv(RAW_CSV_PATH, index=False, encoding="SHIFT-JIS")
    print(f"中央競馬CSV上書き完了: {len(df_jra)} 行を {RAW_CSV_PATH} に保存しました。")

    # 地方競馬のCSVを保存
    if not df_local.empty:
        os.makedirs(LOCAL_CSV_DIR, exist_ok=True)
        if os.path.exists(LOCAL_CSV_PATH):
            try:
                df_existing = pd.read_csv(LOCAL_CSV_PATH, encoding="SHIFT-JIS", dtype={"race_id": str})
                df_local_combined = pd.concat([df_existing, df_local]).drop_duplicates(subset=["race_id", "馬"])
            except Exception:
                df_local_combined = df_local
        else:
            df_local_combined = df_local
            
        df_local_combined.to_csv(LOCAL_CSV_PATH, index=False, encoding="SHIFT-JIS")
        print(f"地方競馬CSV保存完了: {len(df_local)} 行を {LOCAL_CSV_PATH} に追記/保存しました。")
    else:
        print("地方競馬のレコードはCSV内にありませんでした。")

if __name__ == "__main__":
    clean_html()
    clean_csv()
