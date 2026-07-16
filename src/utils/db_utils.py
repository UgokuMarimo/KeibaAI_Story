import sqlite3
import pandas as pd
import requests
import json
import os
import sys

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__)); PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..')); sys.path.append(PROJECT_ROOT); sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
import config

def save_prediction_to_db(result_df: pd.DataFrame, shutuba_df: pd.DataFrame, race_id: str):
    """予測結果をSQLiteデータベースに保存する (新DB設計対応版)"""
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS predictions (
                race_id TEXT, umaban INTEGER, horse_name TEXT, kaisai_date TEXT, 
                keibajo TEXT, race_number INTEGER, track_type TEXT, 
                race_class TEXT, race_name TEXT,
                pred_win REAL, pred_rank INTEGER, 
                pred_place REAL, -- 3着内率の予測結果を追加
                tansho_odds REAL, tansho_ninki INTEGER, 
                result_rank INTEGER,  -- 結果更新用に残す
                prediction_timestamp TEXT, 
                PRIMARY KEY (race_id, umaban)
            );"""
            conn.execute(create_table_query)

            # 既存テーブルにカラムがない場合の追加・アップデート処理
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(predictions);")
            existing_cols = [row[1] for row in cursor.fetchall()]
            
            required_cols = {
                'race_class': 'TEXT',
                'race_name': 'TEXT',
                'pred_place': 'REAL'
            }
            for col_name, col_type in required_cols.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE predictions ADD COLUMN {col_name} {col_type};")
                        print(f"[DB INFO] Added column {col_name} ({col_type}) to predictions table.")
                    except sqlite3.OperationalError as alter_err:
                        print(f"[DB WARN] Failed to add column {col_name}: {alter_err}")

            save_target_df = shutuba_df[['馬番', 'オッズ', '人気']].copy()
            save_target_df.rename(columns={'オッズ': '単勝オッズ'}, inplace=True)
            save_target_df['馬番'] = pd.to_numeric(save_target_df['馬番'], errors='coerce')
            save_df = pd.merge(result_df, save_target_df, on='馬番', how='left')
            
            race_info = shutuba_df.iloc[0]
            save_df['race_id'] = race_id
            parsed_date = pd.to_datetime(race_info['日付'], format='%Y年%m月%d日', errors='coerce')
            if pd.isna(parsed_date):
                parsed_date = pd.to_datetime(race_info['日付'], errors='coerce')
                if pd.isna(parsed_date):
                    parsed_date = pd.Timestamp.now()
            save_df['kaisai_date'] = parsed_date.strftime('%Y-%m-%d')
            save_df['keibajo'] = race_info['場名']
            save_df['race_number'] = int(str(race_id)[-2:])
            save_df['track_type'] = 'turf' if '芝' in race_info['芝・ダート'] else 'dirt'
            save_df['race_class'] = race_info['クラス'] if 'クラス' in race_info else ''
            save_df['race_name'] = race_info['レース名'] if 'レース名' in race_info else ''
            save_df['prediction_timestamp'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

            save_df.rename(columns={
                '馬名': 'horse_name', '馬番': 'umaban', 
                'pred_win': 'pred_win', 'rank_win': 'pred_rank', 
                '単勝オッズ': 'tansho_odds', '人気': '人気'
            }, inplace=True)

            final_cols = ['race_id', 'umaban', 'horse_name', 'kaisai_date', 'keibajo', 'race_number', 'track_type', 'race_class', 'race_name', 'pred_win', 'pred_rank', 'pred_place', 'tansho_odds', 'tansho_ninki', 'prediction_timestamp']
            final_save_df = save_df[[col for col in final_cols if col in save_df.columns]]
            
            cursor = conn.cursor()
            cursor.execute("DELETE FROM predictions WHERE race_id = ?", (race_id,))
            final_save_df.to_sql('predictions', conn, if_exists='append', index=False)
            conn.commit()
            print(f"-> Prediction for race_id {race_id} saved to clean 'predictions' table successfully.")

    except Exception as e:
        print(f"[DB ERROR] Failed to save prediction to database: {e}")

def send_discord_webhook(message: str, webhook_url: str = None):
    # デフォルトは config.DISCORD_WEBHOOK_URL
    target_url = webhook_url if webhook_url else getattr(config, 'DISCORD_WEBHOOK_URL', None)
    
    if not target_url: return

    try:
        requests.post(target_url, json={"content": message, "username": "競馬AI予測"})
        print(f"-> Message sent to Discord successfully. (Target: {target_url[-10:]}...)")
    except requests.exceptions.RequestException as e: print(f"[DISCORD ERROR]: {e}")

def format_for_discord(race_id, race_info, result_df):
    race_name = race_info.get('レース名', '不明'); venue = race_info.get('場名', '不明')
    race_number = str(race_id)[-2:].lstrip('0')
    # ヘッダーの線を5つに短縮
    header = f"🐴 **{venue}{race_number}R {race_name} 予測** 🐴\n" + "="*5 + "\n"
    
    prob_col = 'normalized_pred_win' if 'normalized_pred_win' in result_df.columns else 'pred_win'
    max_horses = getattr(config, 'DISCORD_NOTIFY_MAX_HORSES', 10) # 10頭程度に制限
    
    target_horses = result_df.head(max_horses).copy()
    
    # モバイル向けにカラムを極限まで絞る (番, 馬名, 勝率, 複勝)
    body = "```\n" + "{:<2} {:<5} {:^5} {:^5}\n".format("番", "馬名", "勝率", "複勝") + "-"*23 + "\n"
    
    for _, row in target_horses.iterrows():
        win_prob_val = row.get(prob_col, 0)
        place_prob_val = row.get('pred_place', 0)
        
        # 馬名を5文字に制限
        name = row['馬名'][:5]
        
        body += "{:>2} {:<5} {:>4.1%}|{:>4.1%}\n".format(
            int(row['馬番']), 
            name,
            win_prob_val,
            place_prob_val
        )
    body += "```"
    return header + body

def save_vote_to_db(race_id: str, umaban: int, horse_name: str, kaisai_date: str, 
                     vote_type: str, vote_odds: float, pred_win_prob: float, 
                     amount: int, status: str, mode: str):
    """実際に投票した馬の履歴をデータベースに保存する"""
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS votes (
                race_id TEXT,
                umaban INTEGER,
                horse_name TEXT,
                kaisai_date TEXT,
                vote_type TEXT,
                vote_odds REAL,
                pred_win_prob REAL,
                amount INTEGER,
                status TEXT,
                mode TEXT,
                vote_timestamp TEXT,
                PRIMARY KEY (race_id, umaban)
            );"""
            conn.execute(create_table_query)
            conn.commit()

            insert_query = """
            INSERT OR REPLACE INTO votes (
                race_id, umaban, horse_name, kaisai_date, 
                vote_type, vote_odds, pred_win_prob, amount, 
                status, mode, vote_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            vote_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(insert_query, (
                race_id, umaban, horse_name, kaisai_date,
                vote_type, vote_odds, pred_win_prob, amount,
                status, mode, vote_timestamp
            ))
            conn.commit()
            print(f"-> Vote for race_id {race_id}, horse {horse_name} (Umaban: {umaban}) saved to 'votes' table successfully.")
    except Exception as e:
        print(f"[DB ERROR] Failed to save vote to database: {e}")