import os
import json
import pandas as pd
from datetime import datetime

import config
from .jra_odds_scraper import JRAOddsScraper
from .db_utils import send_discord_webhook

def get_prediction_data(race_id: str):
    """予測結果をJSONファイルから読み込む（EV計算用）"""
    try:
        year, course, kaisai, nissuu, race_num = race_id[:4], race_id[4:6], race_id[6:8], race_id[8:10], race_id[10:]
        shap_dir = os.path.join(config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num)
        summary_path = os.path.join(shap_dir, "prediction_summary.json")
        
        if not os.path.exists(summary_path):
            return None
            
        with open(summary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return pd.DataFrame(data)
    except Exception:
        return None

def format_ev_message(venue_name, race_num, df):
    """Discord用のEV通知メッセージを成形"""
    header = f"💰 **{venue_name}{race_num}R 期待値速報** 💰\n" + "="*5 + "\n"
    df_sorted = df.sort_values('expected_value', ascending=False)
    # 勝率 MIN_WIN_PROB 以上の馬のみを対象にする
    min_win_prob = getattr(config, 'MIN_WIN_PROB', 0.10)
    df_filtered = df_sorted[df_sorted['pred_win_prob'] >= min_win_prob].copy()
    target_ev = getattr(config, 'TARGET_EV_5MIN', 1.3)
    display_df = df_filtered.head(8)
    
    if display_df.empty:
        return header + "※対象馬なし\n"
    
    body = "```\n" + "{:<2} {:<5} {:^5} {:^6}\n".format("番", "馬名", "オッズ", "EV") + "-"*22 + "\n"
    for _, row in display_df.iterrows():
        ev_val = row['expected_value']
        mark = "★" if ev_val >= target_ev else ""
        name = row['horse_name'][:5]
        body += "{:>2} {:<5} {:>5.1f} {:>6.3f}{}\n".format(
            int(row['umaban']), name, row['win_odds'] if pd.notna(row['win_odds']) else 0.0, ev_val, mark
        )
    body += "```"
    return header + body

def process_odds_and_ev_5min(race_id: str, target_date_str: str) -> bool:
    """発走5分前にリアルタイムオッズを取得し、EVを計算してDiscord通知を送信する。
    さらに、勝率 MIN_WIN_PROB 以上かつEVが TARGET_EV_5MIN 以上の『投票候補馬』がいるかどうか判定して返す。
    """
    print(f"\n--- [TRIGGER] 5-min Odds & EV for race {race_id} at {datetime.now().strftime('%H:%M:%S')} ---")
    
    # 1. 予測データの読み込み
    pred_df = get_prediction_data(race_id)
    if pred_df is None or pred_df.empty:
        print("[ERROR] No prediction data found for EV calculation.")
        return False

    # 2. オッズ取得
    course_id = race_id[4:6]
    race_num = int(race_id[10:])
    venue_name = config.PLACE_MAP_IDS.get(course_id)
    
    scraper = JRAOddsScraper(headless=True)
    try:
        odds_df = scraper.get_odds(venue_name, race_num, target_date=target_date_str)
    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
        return False
    finally:
        scraper.close()
        
    if odds_df is None or odds_df.empty:
        return False

    # 3. マージとEV計算
    def clean_odds(x):
        try: return float(x)
        except: return None

    odds_df['clean_odds'] = odds_df['単勝'].apply(clean_odds)
    merged_df = pd.merge(pred_df, odds_df[['馬番', 'clean_odds']], left_on='umaban', right_on='馬番', how='left')
    merged_df['win_odds'] = merged_df['clean_odds']
    merged_df['expected_value'] = merged_df['pred_win_prob'] * merged_df['win_odds']
    merged_df['expected_value'] = merged_df['expected_value'].fillna(0)
    
    # 4. 通知
    message = format_ev_message(venue_name, race_num, merged_df)
    webhook_url = getattr(config, 'DISCORD_EV_WEBHOOK_URL', None)
    if webhook_url:
        send_discord_webhook(message, webhook_url=webhook_url)
        print("[SUCCESS] EV Notification sent.")
        
    # 5. 投票候補馬がいるか判定 (勝率 >= MIN_WIN_PROB かつ EV >= TARGET_EV_5MIN)
    has_candidate = False
    min_win_prob = getattr(config, 'MIN_WIN_PROB', 0.10)
    target_ev_5min = getattr(config, 'TARGET_EV_5MIN', 1.2)
    
    for _, row in merged_df.iterrows():
        win_prob = row.get('pred_win_prob', 0.0)
        win_odds = row.get('win_odds', 0.0)
        if pd.notna(win_odds) and win_odds > 0:
            ev = win_prob * win_odds
            if win_prob >= min_win_prob and ev >= target_ev_5min:
                has_candidate = True
                print(f" -> [5-min CANDIDATE] {row.get('horse_name')} (Umaban:{row.get('umaban')}) met 5-min EV criteria: {ev:.3f} >= {target_ev_5min}")
                
    return has_candidate

def process_odds_and_ev_2min(race_id: str, target_date_str: str) -> bool:
    """発走2分前にリアルタイムオッズを再取得し、EVを再計算して、
    期待値が TARGET_EV_VOTE 以上の馬がいれば自動投票を実行する。
    """
    print(f"\n--- [TRIGGER] 2-min Final Odds & Auto-Voting for race {race_id} at {datetime.now().strftime('%H:%M:%S')} ---")
    
    if not getattr(config, 'AUTO_VOTING_ENABLED', False):
        print("[AUTO-VOTER] Auto voting is disabled in config. Skipping.")
        return False

    # 1. 予測データの読み込み
    pred_df = get_prediction_data(race_id)
    if pred_df is None or pred_df.empty:
        print("[ERROR] No prediction data found for EV calculation.")
        return False

    # 2. オッズ取得
    course_id = race_id[4:6]
    race_num = int(race_id[10:])
    venue_name = config.PLACE_MAP_IDS.get(course_id)
    
    scraper = JRAOddsScraper(headless=True)
    try:
        # 2分前の時点で再度オッズを取得
        odds_df = scraper.get_odds(venue_name, race_num, target_date=target_date_str)
    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
        return False
    finally:
        scraper.close()
        
    if odds_df is None or odds_df.empty:
        return False

    # 3. マージとEV再計算
    def clean_odds(x):
        try: return float(x)
        except: return None

    odds_df['clean_odds'] = odds_df['単勝'].apply(clean_odds)
    merged_df = pd.merge(pred_df, odds_df[['馬番', 'clean_odds']], left_on='umaban', right_on='馬番', how='left')
    merged_df['win_odds'] = merged_df['clean_odds']
    merged_df['expected_value'] = merged_df['pred_win_prob'] * merged_df['win_odds']
    merged_df['expected_value'] = merged_df['expected_value'].fillna(0)
    
    # 4. 自動投票 (Auto-Voting) の最終判定と実行
    min_win_prob = getattr(config, 'MIN_WIN_PROB', 0.10)
    target_ev_vote = getattr(config, 'TARGET_EV_VOTE', 1.3)
    
    has_target_horse = False
    for _, row in merged_df.iterrows():
        win_prob = row.get('pred_win_prob', 0.0)
        win_odds = row.get('win_odds', 0.0)
        if pd.notna(win_odds) and win_odds > 0:
            ev = win_prob * win_odds
            if win_prob >= min_win_prob and ev >= target_ev_vote:
                has_target_horse = True
                break
                
    if has_target_horse:
        print(f"[AUTO-VOTER] Target horse(s) found at 2 min before (EV >= {target_ev_vote}). Triggering AutoVoterManager...")
        try:
            from voting.auto_voter_manager import AutoVoterManager
            manager = AutoVoterManager()
            vote_result = manager.process_race_prediction(race_id, merged_df)
            if vote_result:
                print(f"[AUTO-VOTER] Race {race_id}: Automated voting process completed successfully.")
                return True
            else:
                print(f"[AUTO-VOTER WARN] Race {race_id}: Automated voting process returned False.")
                return False
        except Exception as e:
            print(f"[AUTO-VOTER ERROR] Failed to execute automated voting process: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"[AUTO-VOTER] No horses met 2 min before criteria (EV >= {target_ev_vote}). Skipping voting engine invocation.")
        return False
