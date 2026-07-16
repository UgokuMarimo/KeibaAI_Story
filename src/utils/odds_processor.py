import os
import sys
import json
import pandas as pd
import argparse
from datetime import datetime

# --- Project Path Setup ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import config
from utils.jra_odds_scraper import JRAOddsScraper
from utils.db_utils import send_discord_webhook

def get_prediction_data(race_id: str):
    """
    Load prediction data from JSON file in shap_results.
    """
    try:
        race_id_str = str(race_id)
        if len(race_id_str) == 12:
            year, course, kaisai, nissuu, race_num = race_id_str[:4], race_id_str[4:6], race_id_str[6:8], race_id_str[8:10], race_id_str[10:]
            shap_dir = os.path.join(config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num)
        else:
            shap_dir = os.path.join(config.SHAP_RESULTS_DIR, race_id_str)
            
        summary_path = os.path.join(shap_dir, "prediction_summary.json")
        
        if not os.path.exists(summary_path):
            print(f"[ERROR] Prediction summary not found at {summary_path}")
            return None
            
        with open(summary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return pd.DataFrame(data)
        
    except Exception as e:
        print(f"[ERROR] Failed to load prediction data: {e}")
        return None

def format_ev_message(race_id, venue_name, race_num, df):
    """
    Format the Discord message specifically for EV results.
    """
    # ヘッダーを短縮し、線を5つに
    header = f"💰 **{venue_name}{race_num}R 期待値速報** 💰\n" + "="*5 + "\n"
    
    # Sort by EV descending
    df_sorted = df.sort_values('expected_value', ascending=False)
    
    # 勝率 MIN_WIN_PROB 以上の馬のみを対象にする
    win_prob_threshold = getattr(config, 'MIN_WIN_PROB', 0.10)
    df_filtered = df_sorted[df_sorted['pred_win_prob'] >= win_prob_threshold].copy()
    
    target_ev = getattr(config, 'TARGET_EV', 1.3)
    display_df = df_filtered.head(8)
    
    if display_df.empty:
        return header + "※対象馬なし\n"
    
    # モバイル重視のコンパクトなカラム (番, 馬名, オッズ, EV)
    body = "```\n" + "{:<2} {:<5} {:^5} {:^6}\n".format("番", "馬名", "オッズ", "EV") + "-"*22 + "\n"
    
    for _, row in display_df.iterrows():
        ev_val = row['expected_value']
        mark = "★" if ev_val >= target_ev else ""
        
        # 馬名を5文字に制限
        name = row['horse_name'][:5]
        
        body += "{:>2} {:<5} {:>5.1f} {:>6.3f}{}\n".format(
            int(row['umaban']),
            name,
            row['win_odds'] if pd.notna(row['win_odds']) else 0.0,
            ev_val,
            mark
        )
    body += "```"
    
    return header + body

def process_odds_and_notify(race_id: str, target_date: str = None):
    """
    Main function to process odds and notify.
    """
    print(f"--- [START] Odds Processing for Race ID: {race_id} (Date: {target_date}) ---")
    
    # 1. Parse Race ID
    if len(race_id) != 12:
        print(f"[ERROR] Invalid Race ID format: {race_id}")
        return
    
    course_id = race_id[4:6]
    race_num = int(race_id[10:])
    venue_name = config.PLACE_MAP_IDS.get(course_id)
    
    if not venue_name:
        print(f"[ERROR] Unknown venue ID: {course_id}")
        return

    print(f"Target: {venue_name} {race_num}R")

    # 2. Load Prediction Data
    pred_df = get_prediction_data(race_id)
    if pred_df is None or pred_df.empty:
        print("[ERROR] No prediction data available.")
        return

    # 3. Scrape Odds
    # Use provided target_date or extract from pred_df if available
    if not target_date and not pred_df.empty and 'kaisai_date' in pred_df.columns:
        target_date = pred_df['kaisai_date'].iloc[0]
        print(f"Targeting date from prediction: {target_date}")

    scraper = JRAOddsScraper(headless=True)
    odds_df = None
    try:
        odds_df = scraper.get_odds(venue_name, race_num, target_date=target_date)
    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
    finally:
        scraper.close()
        
    if odds_df is None or odds_df.empty:
        print("[ERROR] Failed to get odds data.")
        return

    # 4. Merge Data
    # pred_df has 'umaban' (int), odds_df has '馬番' (int)
    # odds_df has '単勝' (nominal, string or float)
    
    # Clean odds data
    def clean_odds(x):
        try:
            return float(x)
        except:
            return None

    odds_df['clean_odds'] = odds_df['単勝'].apply(clean_odds)
    
    # Merge
    merged_df = pd.merge(pred_df, odds_df[['馬番', 'clean_odds']], left_on='umaban', right_on='馬番', how='left')
    
    # 5. Calculate EV
    merged_df['win_odds'] = merged_df['clean_odds']
    merged_df['expected_value'] = merged_df['pred_win_prob'] * merged_df['win_odds']
    merged_df['expected_value'] = merged_df['expected_value'].fillna(0)
    
    # 6. Format and Send Notification
    message = format_ev_message(race_id, venue_name, race_num, merged_df)
    
    webhook_url = getattr(config, 'DISCORD_EV_WEBHOOK_URL', None)
    if webhook_url:
        send_discord_webhook(message, webhook_url=webhook_url)
        print("[SUCCESS] Notification sent to EV channel.")
    else:
        print("[WARN] DISCORD_EV_WEBHOOK_URL not set in config.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process odds and send EV notification.")
    parser.add_argument("race_id", type=str, help="Target Race ID")
    parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD)", default=None)
    args = parser.parse_args()
    
    process_odds_and_notify(args.race_id, target_date=args.date)
