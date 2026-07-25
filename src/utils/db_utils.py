import sqlite3
import pandas as pd
import requests
import json
import os
import sys
import urllib.parse

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
                odds_5min REAL, -- 5分前オッズ
                odds_3min REAL, -- 3分前オッズ
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
                'pred_place': 'REAL',
                'odds_5min': 'REAL',
                'odds_3min': 'REAL'
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


def send_x_channel_notification(race_id, race_info, result_df, webhook_url=None):
    """
    X(旧Twitter)用チャンネルへ1タップ投稿リンク(Embed)およびコピペ枠を送信する。
    """
    if not webhook_url:
        webhook_url = getattr(config, 'DISCORD_X_WEBHOOK_URL', None)
    if not webhook_url:
        return

    if isinstance(race_info, pd.Series):
        race_info = race_info.to_dict()
    race_name = race_info.get('レース名', '不明')
    venue = race_info.get('場名', '不明')
    race_number = str(race_id)[-2:].lstrip('0')

    # 勝率の正規化 (全馬の合計が100%になるように計算)
    df_copy = result_df.copy()
    if 'normalized_pred_win' in df_copy.columns:
        prob_col = 'normalized_pred_win'
    elif 'pred_win' in df_copy.columns:
        total_pred = df_copy['pred_win'].sum()
        if total_pred > 0:
            df_copy['normalized_pred_win'] = df_copy['pred_win'] / total_pred
            prob_col = 'normalized_pred_win'
        else:
            prob_col = 'pred_win'
    else:
        prob_col = 'pred_win'

    # 正規化勝率が10% (0.10) 以上の馬を全頭抽出
    filtered_horses = df_copy[df_copy[prob_col] >= 0.10].sort_values(prob_col, ascending=False)
    # 10%以上の馬がゼロ頭の場合は上位2頭をフォールバック表示
    if filtered_horses.empty:
        filtered_horses = df_copy.sort_values(prob_col, ascending=False).head(2)

    rank_emojis = ["🥇", "🥈", "🥉"]

    # 本文テキスト生成
    x_lines = [f"🏁【{venue}{race_number}R {race_name}】AI勝率予測"]
    for idx, (_, r) in enumerate(filtered_horses.iterrows()):
        w_val = r.get(prob_col, 0)
        
        # カラム名のフォールバック (日本語カラム '馬番'/'馬名' または 英語カラム 'umaban'/'horse_name')
        u_num_raw = r.get('馬番') if pd.notnull(r.get('馬番')) else r.get('umaban', 0)
        u_num = int(u_num_raw) if u_num_raw is not None else 0
        
        h_name = str(r.get('馬名') if pd.notnull(r.get('馬名')) else r.get('horse_name', ''))
        
        emoji = rank_emojis[idx] if idx < 3 else f"{idx+1}."
        x_lines.append(f"{emoji} {u_num}番 {h_name} ({w_val:.1%})")

    # 末尾馬の後に確実に改行を入れてハッシュタグを配置
    x_lines.append(f"\n#競馬AI #競馬予想 #{venue}競馬")

    raw_tweet_text = "\n".join(x_lines)

    # X Intent URL 生成 (Embedのurlフィールドで使用すると二重エンコードされず完璧に動作)
    encoded_text = urllib.parse.quote(raw_tweet_text)
    intent_url = f"https://twitter.com/intent/tweet?text={encoded_text}"

    content = f"📱 **【X(旧Twitter) 投稿アシスト】** (`{venue}{race_number}R {race_name}`)\n\n"
    content += "↓ 1タップ投稿は下の**青いカードタイトル**をタップ、手動の場合は枠内を全選択コピーしてください:\n"
    content += "```\n" + raw_tweet_text + "\n```"

    payload = {
        "username": "競馬AI X投稿アシスト",
        "content": content,
        "embeds": [
            {
                "title": f"🚀 1タップでX(Twitter)に投稿する ({venue}{race_number}R)",
                "url": intent_url,
                "description": "👉 上の青いタイトル「🚀 1タップでX(Twitter)に投稿する」をタップすると、フルネーム＆改行済みのツイート画面が開きます！",
                "color": 1942002
            }
        ]
    }

    try:
        requests.post(webhook_url, json=payload)
        print(f"-> Sent X post assistance to Discord X channel successfully.")
    except Exception as e:
        print(f"[DISCORD ERROR]: Failed to send to X channel: {e}")





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

def update_predictions_odds_bulk(race_id: str, odds_dict: dict, target_col: str):
    """predictions テーブルの odds_5min または odds_3min を一括更新する"""
    if target_col not in ['odds_5min', 'odds_3min']:
        raise ValueError(f"Invalid odds column: {target_col}")
        
    updates = []
    for umaban, odds in odds_dict.items():
        if odds is not None:
            try:
                updates.append((float(odds), race_id, int(umaban)))
            except (ValueError, TypeError):
                continue
            
    if not updates:
        return

    # 1. ローカル SQLite の更新
    try:
        with sqlite3.connect(config.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(predictions);")
            cols = [row[1] for row in cursor.fetchall()]
            if target_col not in cols:
                conn.execute(f"ALTER TABLE predictions ADD COLUMN {target_col} REAL;")
                
            query = f"UPDATE predictions SET {target_col} = ? WHERE race_id = ? AND umaban = ?"
            conn.executemany(query, updates)
            conn.commit()
            print(f"[DB INFO] Updated {len(updates)} records for {target_col} (Local SQLite)")
    except Exception as e:
        print(f"[DB ERROR] Failed to bulk update {target_col} for {race_id} (Local): {e}")

    # 2. Supabase PostgreSQL の更新
    try:
        from utils.db_sync import get_pg_conn
        pg_conn = get_pg_conn()
        with pg_conn.cursor() as cur:
            query = f"UPDATE predictions SET {target_col} = %s WHERE race_id = %s AND umaban = %s"
            cur.executemany(query, updates)
        pg_conn.commit()
        pg_conn.close()
        print(f"[DB INFO] Updated {len(updates)} records for {target_col} (Supabase PostgreSQL)")
    except Exception as e:
        # 環境変数がない場合や、同期に失敗した場合は無視する（後で sync するため）
        pass