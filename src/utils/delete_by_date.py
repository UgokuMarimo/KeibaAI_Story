import sqlite3
import argparse
import os
import sys

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
import config

def delete_predictions_by_date(target_date, force=False):
    """
    指定された日付(kaisai_date)のデータをpredictionsテーブルから削除する
    """
    db_path = config.DB_PATH
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # まず対象件数を確認
            cursor.execute("SELECT COUNT(*) FROM predictions WHERE kaisai_date = ?", (target_date,))
            count = cursor.fetchone()[0]
            
            if count == 0:
                print(f"No records found for date: {target_date}")
                return

            print(f"Found {count} records for date {target_date}.")
            
            if not force:
                confirm = input("Are you sure you want to delete them? (y/N): ")
                if confirm.lower() != 'y':
                    print("Operation cancelled.")
                    return

            cursor.execute("DELETE FROM predictions WHERE kaisai_date = ?", (target_date,))
            conn.commit()
            print(f"Successfully deleted {count} records.")

    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete prediction data for a specific date.")
    parser.add_argument("date", help="Target date in YYYY-MM-DD format (e.g., 2025-01-05)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()
    delete_predictions_by_date(args.date, force=args.force)
