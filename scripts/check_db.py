import sqlite3
import os
import pandas as pd

def check_db(db_path):
    print(f"--- Checking {db_path} ---")
    if not os.path.exists(db_path):
        print("File does not exist.")
        return
    conn = sqlite3.connect(db_path)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", tables)
    for t in tables:
        tname = t[0]
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        print(f" Table '{tname}': {cnt} rows")
        df_head = pd.read_sql_query(f"SELECT * FROM {tname} LIMIT 3", conn)
        print(df_head.columns.tolist())
    conn.close()

check_db('predictions.db')
check_db('data/db/predictions.db')
