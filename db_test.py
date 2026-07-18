import os
import sys
import pymysql
from dotenv import load_dotenv

# Windows環境での文字化け対策（標準出力をUTF-8に変更）
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def main():
    # .env ファイルから環境変数を読み込む
    load_dotenv()

    # 環境変数からデータベース接続情報を取得
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "3306")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    print("=== MySQL 接続テスト開始 ===")
    print(f"現在の作業ディレクトリ: {os.getcwd()}")
    print(f"接続先ホスト: {db_host}")
    print(f"データベース: {db_name}")
    print(f"ユーザー: {db_user}")

    # 接続パラメータのチェック
    if not all([db_host, db_user, db_password, db_name]):
        print("[エラー] 必要な環境変数が .env に設定されていないか、.env ファイルが見つかりません。")
        print(f"確認：現在のディレクトリ内のファイル一覧: {os.listdir('.')}")
        print(".env.example を参考に、DB_HOST, DB_USER, DB_PASSWORD, DB_NAME を設定してください。")
        return

    try:
        # 接続の確立 (読み取り専用テストなので変更は行わない)
        connection = pymysql.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            database=db_name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        print("[成功] データベース接続に成功しました。\n")
    except Exception as e:
        print(f"[エラー] データベースへの接続に失敗しました: {e}")
        print("Cloudflare WARPへの接続状況や、.env の設定値が正しいか確認してください。")
        return

    try:
        with connection.cursor() as cursor:
            # 1. テーブル一覧の取得
            print("--- テーブル一覧を取得します ---")
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if not tables:
                print("データベース内にテーブルが見つかりませんでした。")
                return

            print(f"検出されたテーブル数: {len(tables)}")
            
            # テーブル名一覧を表示
            table_names = []
            for row in tables:
                table_name = list(row.values())[0]
                table_names.append(table_name)
            
            # 最大20件表示
            for name in table_names[:20]:
                print(f"  - {name}")
            if len(table_names) > 20:
                print(f"  ...他 {len(table_names) - 20} 件のテーブルがあります")

            print("\n--- 最新データのテスト取得を開始します ---")
            # 2. 競馬AIデータ（レースデータ等）のテーブルを探して1件取得
            # 代表的なJRA-VANのテーブルプレフィックスやキーワードで探す
            target_keywords = ["race", "jvd_ra", "jvd_race", "races", "uma", "horse"]
            selected_table = None

            for keyword in target_keywords:
                for name in table_names:
                    if keyword in name.lower():
                        selected_table = name
                        break
                if selected_table:
                    break

            # キーワードで見つからない場合は最初のテーブルを使用
            if not selected_table and table_names:
                selected_table = table_names[0]

            if selected_table:
                print(f"テスト取得対象テーブル: {selected_table}")
                
                # 安全な SELECT クエリのみを実行 (1件取得)
                # データ変更は一切行わない
                sql = f"SELECT * FROM `{selected_table}` LIMIT 1"
                print(f"クエリ実行: {sql}")
                
                cursor.execute(sql)
                result = cursor.fetchone()
                
                if result:
                    print("\n--- 取得結果 (1件) ---")
                    for key, val in result.items():
                        print(f"  {key}: {val}")
                else:
                    print(f"テーブル `{selected_table}` は空です。")
            else:
                print("テスト取得可能なテーブルが見つかりませんでした。")

    except Exception as e:
        print(f"[エラー] クエリの実行中にエラーが発生しました: {e}")
    finally:
        connection.close()
        print("\n=== MySQL 接続テスト終了 ===")

if __name__ == "__main__":
    main()
