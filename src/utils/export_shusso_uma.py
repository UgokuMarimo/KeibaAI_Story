import os
import sys
import pymysql
import pandas as pd

# プロジェクトルートの設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

# Windows環境での文字化け対策（標準出力をUTF-8に変更）
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def main():
    # 環境変数からデータベース接続情報を取得
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "3306")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    # 接続パラメータのチェック
    if not all([db_host, db_user, db_password, db_name]):
        print("[エラー] 必要な環境変数が .env に設定されていません。")
        return

    # 引数のチェック（YYYYMMDD形式）
    target_date_str = None
    if len(sys.argv) > 1:
        arg_date = sys.argv[1].strip()
        if len(arg_date) == 8 and arg_date.isdigit():
            target_date_str = arg_date
            print(f"指定された日付で抽出を行います: {target_date_str}")
        else:
            print("[警告] 引数は YYYYMMDD 形式（例: 20260531）で指定してください。自動検出にフォールバックします。")

    # 出力先の設定
    output_dir = os.path.join(PROJECT_ROOT, "data", "SQL_data")

    try:
        # 接続の確立 (読み取り専用)
        # ※ pandas.read_sql が正常に動作するよう、デフォルトのタプル型カーソルを使用します
        connection = pymysql.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            database=db_name,
            charset="utf8mb4"
        )
    except Exception as e:
        print(f"[エラー] データベースへの接続に失敗しました: {e}")
        return

    try:
        with connection.cursor() as cursor:
            # 1. 抽出対象の日付 (target_year, target_monthday) の決定
            if target_date_str:
                target_year = target_date_str[:4]
                target_monthday = target_date_str[4:]
            else:
                # 引数がない場合は、データベース全体の最新の開催日(Year, MonthDay)を取得する
                # （日付整合性のため N_RACE の最新日から判定）
                print("データベース内の最新開催日を検索中...")
                date_query = "SELECT Year, MonthDay FROM N_RACE WHERE Year REGEXP '^[0-9]{4}$' ORDER BY Year DESC, MonthDay DESC LIMIT 1"
                cursor.execute(date_query)
                latest_date = cursor.fetchone()

                if not latest_date:
                    print("N_RACE テーブルにデータが見つかりません。")
                    return

                target_year = latest_date[0]
                target_monthday = latest_date[1]
                target_date_str = f"{target_year}{target_monthday}"
            
            print(f"最新の開催日を検出しました: {target_year}年{target_monthday[:2]}月{target_monthday[2:]}日")
            output_file = os.path.join(output_dir, f"shusso_uma_{target_date_str}.csv")

            # 2. 指定日の1日分の出走馬データを取得するクエリ
            select_query = """
                SELECT * FROM N_UMA_RACE 
                WHERE Year = %s AND MonthDay = %s
                ORDER BY JyoCD, RaceNum, CAST(Umaban AS UNSIGNED)
            """
            
            print(f"出走馬データを抽出中 ({target_year}-{target_monthday})...")
            # pandasのread_sqlで安全に取得
            df = pd.read_sql(select_query, connection, params=(target_year, target_monthday))

            if df.empty:
                print(f"指定された日付 {target_date_str} の出走馬データがありませんでした。")
                return

            print(f"抽出成功: {len(df)} 件の出走馬データを取得しました。")

            # 3. 保存先フォルダの作成
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"フォルダを作成しました: {output_dir}")

            # 4. CSVファイルへ保存
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"CSV出力を完了しました: {output_file}")

            # 5. データの概要を簡易表示
            print("\n=== 抽出データのプレビュー ===")
            preview_cols = ['Year', 'MonthDay', 'JyoCD', 'RaceNum', 'Wakuban', 'Umaban', 'Bamei', 'KisyuRyakusyo', 'Futan']
            # プレビュー用の列が存在することを確認して表示
            available_cols = [col for col in preview_cols if col in df.columns]
            print(df[available_cols].head(10))

    except Exception as e:
        print(f"[エラー] データ抽出中にエラーが発生しました: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    main()
