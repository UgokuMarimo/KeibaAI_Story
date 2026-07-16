import sqlite3

def main():
    conn = sqlite3.connect('predictions.db')
    cursor = conn.cursor()
    
    # テーブル一覧の取得
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    # 各テーブルのスキーマ取得
    for table_tuple in tables:
        table_name = table_tuple[0]
        print(f"\nSchema of {table_name}:")
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
            
    conn.close()

if __name__ == '__main__':
    main()
