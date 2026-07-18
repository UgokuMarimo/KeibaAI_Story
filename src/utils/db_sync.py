import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import argparse
from datetime import datetime
import dotenv

# プロジェクトルートの設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# .env を読み込む
dotenv.load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

import config

def get_sqlite_conn():
    """ローカル SQLite への接続を取得"""
    return sqlite3.connect(config.DB_PATH)

def get_pg_conn():
    """Supabase PostgreSQL への接続を取得"""
    # .envから環境変数をロード (configで読み込まれているはずだが、念のためosから取得)
    host = os.getenv("SUPABASE_DB_HOST")
    port = os.getenv("SUPABASE_DB_PORT", "5432")
    user = os.getenv("SUPABASE_DB_USER", "postgres")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    dbname = os.getenv("SUPABASE_DB_NAME", "postgres")
    
    if not host or not password:
        raise ValueError("[ERROR] Supabaseの接続設定 (.env) が不足しています。")
        
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=dbname
    )

def create_pg_tables_if_not_exists(pg_conn):
    """PostgreSQL 側に必要なテーブルを作成する"""
    queries = [
        # 1. predictions テーブル
        """
        CREATE TABLE IF NOT EXISTS predictions (
            race_id VARCHAR(50),
            umaban INTEGER,
            horse_name VARCHAR(100),
            kaisai_date VARCHAR(20),
            keibajo VARCHAR(50),
            race_number INTEGER,
            track_type VARCHAR(20),
            race_class VARCHAR(100),
            race_name VARCHAR(200),
            pred_win DOUBLE PRECISION,
            pred_rank INTEGER,
            pred_place DOUBLE PRECISION,
            tansho_odds DOUBLE PRECISION,
            tansho_ninki INTEGER,
            result_rank INTEGER,
            prediction_timestamp VARCHAR(30),
            PRIMARY KEY (race_id, umaban)
        );
        """,
        # 2. votes テーブル
        """
        CREATE TABLE IF NOT EXISTS votes (
            race_id VARCHAR(50),
            umaban INTEGER,
            horse_name VARCHAR(100),
            kaisai_date VARCHAR(20),
            vote_type VARCHAR(50),
            vote_odds DOUBLE PRECISION,
            pred_win_prob DOUBLE PRECISION,
            amount INTEGER,
            status VARCHAR(50),
            mode VARCHAR(50),
            vote_timestamp VARCHAR(30),
            PRIMARY KEY (race_id, umaban)
        );
        """,
        # 3. payouts テーブル
        """
        CREATE TABLE IF NOT EXISTS payouts (
            race_id VARCHAR(50) PRIMARY KEY,
            tansho_payout INTEGER,
            tansho_numbers VARCHAR(50),
            fukusho_payouts TEXT,
            wakuren_payout INTEGER,
            wakuren_numbers VARCHAR(50),
            umaren_payout INTEGER,
            umaren_numbers VARCHAR(50),
            wide_payouts TEXT,
            umatan_payout INTEGER,
            umatan_numbers VARCHAR(50),
            sanrenpuku_payout INTEGER,
            sanrenpuku_numbers VARCHAR(50),
            sanrentan_payout INTEGER,
            sanrentan_numbers VARCHAR(50)
        );
        """
    ]
    with pg_conn.cursor() as cur:
        for q in queries:
            cur.execute(q)
    pg_conn.commit()
    print("[DB SYNC] Supabaseのテーブルスキーマ確認完了。")

def sync_sqlite_to_pg(sqlite_conn, pg_conn):
    """SQLite (ローカル) から PostgreSQL (Supabase) へプッシュ"""
    print("[DB SYNC] SQLite -> Supabase PostgreSQL 同期開始...")
    
    tables_info = {
        'predictions': {
            'cols': [
                'race_id', 'umaban', 'horse_name', 'kaisai_date', 'keibajo', 'race_number',
                'track_type', 'race_class', 'race_name', 'pred_win', 'pred_rank', 'pred_place',
                'tansho_odds', 'tansho_ninki', 'result_rank', 'prediction_timestamp'
            ],
            'pkeys': ['race_id', 'umaban']
        },
        'votes': {
            'cols': [
                'race_id', 'umaban', 'horse_name', 'kaisai_date', 'vote_type', 'vote_odds',
                'pred_win_prob', 'amount', 'status', 'mode', 'vote_timestamp'
            ],
            'pkeys': ['race_id', 'umaban']
        },
        'payouts': {
            'cols': [
                'race_id', 'tansho_payout', 'tansho_numbers', 'fukusho_payouts', 'wakuren_payout',
                'wakuren_numbers', 'umaren_payout', 'umaren_numbers', 'wide_payouts', 'umatan_payout',
                'umatan_numbers', 'sanrenpuku_payout', 'sanrenpuku_numbers', 'sanrentan_payout', 'sanrentan_numbers'
            ],
            'pkeys': ['race_id']
        }
    }
    
    for table_name, info in tables_info.items():
        # SQLiteから全件読み込み
        sqlite_cur = sqlite_conn.cursor()
        try:
            sqlite_cur.execute(f"SELECT {', '.join(info['cols'])} FROM {table_name}")
            rows = sqlite_cur.fetchall()
        except sqlite3.OperationalError as e:
            # テーブルが存在しない場合はスキップ
            print(f"[DB SYNC] SQLiteテーブル {table_name} が存在しないためプッシュをスキップします: {e}")
            continue
            
        if not rows:
            print(f"[DB SYNC] SQLiteテーブル {table_name} は空です。")
            continue
            
        # PostgreSQLへUpsert
        # ON CONFLICT句の構築
        non_pkey_cols = [c for c in info['cols'] if c not in info['pkeys']]
        update_set_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in non_pkey_cols])
        
        insert_query = f"""
            INSERT INTO {table_name} ({', '.join(info['cols'])})
            VALUES %s
            ON CONFLICT ({', '.join(info['pkeys'])})
            DO UPDATE SET {update_set_clause}
        """
        
        with pg_conn.cursor() as pg_cur:
            execute_values(pg_cur, insert_query, rows)
        pg_conn.commit()
        print(f"[DB SYNC] {table_name}: {len(rows)} 件を Supabase へプッシュしました。")

def sync_pg_to_sqlite(pg_conn, sqlite_conn):
    """PostgreSQL (Supabase) から SQLite (ローカル) へプル"""
    print("[DB SYNC] Supabase PostgreSQL -> SQLite 同期開始...")
    
    # SQLite側のテーブル作成 (未作成の場合)
    # 本番実行時にDBが存在しない場合があるため、db_utilsのスキーマを参考にテーブル作成
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        race_id TEXT, umaban INTEGER, horse_name TEXT, kaisai_date TEXT, 
        keibajo TEXT, race_number INTEGER, track_type TEXT, 
        race_class TEXT, race_name TEXT,
        pred_win REAL, pred_rank INTEGER, 
        pred_place REAL,
        tansho_odds REAL, tansho_ninki INTEGER, 
        result_rank INTEGER,
        prediction_timestamp TEXT, 
        PRIMARY KEY (race_id, umaban)
    );
    """)
    sqlite_cur.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        race_id TEXT, umaban INTEGER, horse_name TEXT, kaisai_date TEXT, 
        vote_type TEXT, vote_odds REAL, pred_win_prob REAL, amount INTEGER, 
        status TEXT, mode TEXT, vote_timestamp TEXT,
        PRIMARY KEY (race_id, umaban)
    );
    """)
    sqlite_cur.execute("""
    CREATE TABLE IF NOT EXISTS payouts (
        race_id TEXT PRIMARY KEY, tansho_payout INTEGER, tansho_numbers TEXT,
        fukusho_payouts TEXT, wakuren_payout INTEGER, wakuren_numbers TEXT,
        umaren_payout INTEGER, umaren_numbers TEXT, wide_payouts TEXT,
        umatan_payout INTEGER, umatan_numbers TEXT, sanrenpuku_payout INTEGER,
        sanrenpuku_numbers TEXT, sanrentan_payout INTEGER, sanrentan_numbers TEXT
    );
    """)
    sqlite_conn.commit()

    tables = ['predictions', 'votes', 'payouts']
    
    for table_name in tables:
        # PostgreSQLから読み込み
        with pg_conn.cursor() as pg_cur:
            # カラム一覧を正確に取得するため一度SQLiteのPRAGMAか固定定義を使う
            # SQLite側のテーブル定義とカラム位置を合わせる
            if table_name == 'predictions':
                cols = [
                    'race_id', 'umaban', 'horse_name', 'kaisai_date', 'keibajo', 'race_number',
                    'track_type', 'race_class', 'race_name', 'pred_win', 'pred_rank', 'pred_place',
                    'tansho_odds', 'tansho_ninki', 'result_rank', 'prediction_timestamp'
                ]
            elif table_name == 'votes':
                cols = [
                    'race_id', 'umaban', 'horse_name', 'kaisai_date', 'vote_type', 'vote_odds',
                    'pred_win_prob', 'amount', 'status', 'mode', 'vote_timestamp'
                ]
            else: # payouts
                cols = [
                    'race_id', 'tansho_payout', 'tansho_numbers', 'fukusho_payouts', 'wakuren_payout',
                    'wakuren_numbers', 'umaren_payout', 'umaren_numbers', 'wide_payouts', 'umatan_payout',
                    'umatan_numbers', 'sanrenpuku_payout', 'sanrenpuku_numbers', 'sanrentan_payout', 'sanrentan_numbers'
                ]
                
            pg_cur.execute(f"SELECT {', '.join(cols)} FROM {table_name}")
            rows = pg_cur.fetchall()
            
        if not rows:
            print(f"[DB SYNC] Supabaseの {table_name} テーブルは空です。")
            continue
            
        # SQLiteへ流し込み (INSERT OR REPLACE)
        placeholders = ", ".join(["?"] * len(cols))
        insert_query = f"INSERT OR REPLACE INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
        
        sqlite_cur.executemany(insert_query, rows)
        sqlite_conn.commit()
        print(f"[DB SYNC] {table_name}: {len(rows)} 件を Supabase からローカルへプルしました。")

def main():
    parser = argparse.ArgumentParser(description="Synchronize SQLite and Supabase PostgreSQL databases.")
    parser.add_argument('--action', choices=['push', 'pull', 'sync'], default='sync',
                        help="push: Local->Cloud, pull: Cloud->Local, sync: Bidirectional (default)")
    args = parser.parse_args()
    
    start_time = datetime.now()
    print(f"\n[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] --- DB Sync Tool Started ---")
    
    # 接続確認
    try:
        sqlite_conn = get_sqlite_conn()
        pg_conn = get_pg_conn()
    except Exception as e:
        print(f"[FATAL] データベース接続エラー: {e}")
        sys.exit(1)
        
    try:
        # Supabase側の初期化
        create_pg_tables_if_not_exists(pg_conn)
        
        if args.action == 'push':
            sync_sqlite_to_pg(sqlite_conn, pg_conn)
        elif args.action == 'pull':
            sync_pg_to_sqlite(pg_conn, sqlite_conn)
        else: # sync
            # 双方向マージ (SQLite -> Pg -> SQLite) の順で行うことで、両方の差分がすべてマージされる
            sync_sqlite_to_pg(sqlite_conn, pg_conn)
            sync_pg_to_sqlite(pg_conn, sqlite_conn)
            
        print(f"[SUCCESS] データベース同期完了 (処理時間: {datetime.now() - start_time})")
    except Exception as e:
        print(f"[ERROR] 同期処理中に予期せぬエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_conn.close()
        pg_conn.close()
        print("----------------------------------------\n")

if __name__ == "__main__":
    main()
