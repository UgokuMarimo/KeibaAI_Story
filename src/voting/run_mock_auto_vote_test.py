# C:\KeibaAI\src\voting\run_mock_auto_vote_test.py
import os
import sys
import sqlite3
import pandas as pd
import argparse

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# .envファイルのロードを明示的に行う
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

import config
from voting.auto_voter_manager import AutoVoterManager

def main():
    parser = argparse.ArgumentParser(description="Mock Auto-Vote Integration Test Runner")
    parser.add_argument("--scenario", type=int, default=1, choices=[1, 2, 3], help="Test scenario number (1: Maintain EV & Vote, 2: EV Drop & Skip, 3: Max Odds Over & Skip)")
    args = parser.parse_args()

    print(f"\n=== STARTING MOCK AUTO-VOTE INTEGRATION TEST (SCENARIO {args.scenario}) ===")
    
    # 1. データベースからテスト用のレース予測データをロード
    race_id = "202503030111"
    db_path = 'C:/KeibaAI/predictions.db'
    
    if not os.path.exists(db_path):
        print(f"[ERROR] Predictions database not found at {db_path}")
        return
        
    print(f"Loading predictions for race_id {race_id} from SQLite...")
    try:
        with sqlite3.connect(db_path) as conn:
            query = """
            SELECT umaban, horse_name AS horse_name, pred_win, pred_place, tansho_odds, tansho_ninki 
            FROM predictions 
            WHERE race_id = ?
            """
            df_preds = pd.read_sql_query(query, conn, params=(race_id,))
    except Exception as e:
        print(f"[ERROR] Failed to load data from SQLite: {e}")
        return

    if df_preds.empty:
        print(f"[ERROR] No predictions found for race_id {race_id} in SQLite. Please make sure the test run was saved.")
        return

    print(f"Loaded {len(df_preds)} horses. Normalizing win probabilities (total 1.0) for EV calculation...")
    df_preds['normalized_pred_win'] = df_preds['pred_win'] / df_preds['pred_win'].sum()
    
    # Windowsでの文字化けを防ぐため馬名を綺麗な英数字名に差し替える
    df_preds['tansho_odds'] = pd.to_numeric(df_preds['tansho_odds'], errors='coerce')
    df_preds = df_preds.sort_values('normalized_pred_win', ascending=False).reset_index(drop=True)
    
    dummy_odds = [15.0, 18.0, 22.0, 30.0, 45.0, 60.0, 80.0, 100.0, 150.0, 200.0, 250.0, 300.0, 400.0]
    for idx, row in df_preds.iterrows():
        df_preds.at[idx, 'horse_name'] = f"TestHorse-{chr(65+idx)}"
        if pd.isna(row['tansho_odds']) or row['tansho_odds'] <= 0:
            df_preds.at[idx, 'tansho_odds'] = dummy_odds[idx] if idx < len(dummy_odds) else 999.0

    # ------------------------------------------------------------
    # シナリオ別のモックデータ設定 (cp932エラー回避のため絵文字削除)
    # ------------------------------------------------------------
    if args.scenario == 1:
        print("\n[Scenario 1]: EV Maintained -> Vote Succeeds")
        print("Description: 5 min before: EV meets target (odds 3.6, win prob 50.0% -> EV 1.80).")
        print("             At voting: UMACA page odds is still 3.6 (meets target). Votes successfully.")
        # 07_screen_step.html上の馬番3番はオッズ3.6倍。勝率を50.0%に設定して期待値1.80にする。
        df_preds.loc[df_preds['umaban'] == 3, 'normalized_pred_win'] = 0.50
        df_preds.loc[df_preds['umaban'] == 3, 'tansho_odds'] = 3.6
        
    elif args.scenario == 2:
        print("\n[Scenario 2]: EV Drops -> Skip Vote")
        print("Description: 5 min before: EV meets target (odds 3.6, win prob 50.0% -> EV 1.80).")
        print("             At voting: win prob drops to 30.0% (EV 1.08 < target 1.3). Skips vote.")
        # 5分前は勝率50%（EV 1.80）と仮定。しかし直前判定での予測勝率を 30% に落とす
        df_preds.loc[df_preds['umaban'] == 3, 'normalized_pred_win'] = 0.30
        df_preds.loc[df_preds['umaban'] == 3, 'tansho_odds'] = 3.6
        
    elif args.scenario == 3:
        print("\n[Scenario 3]: Odds Exceeds Max -> Skip Vote")
        print("Description: 5 min before: EV meets target (odds 119.8, win prob 15.0% -> EV 17.97).")
        print("             At voting: UMACA page odds is 119.8, which exceeds max limit (15.0). Skips vote.")
        # 07_screen_step.html上の馬番1番（オッズ119.8倍）。勝率15%に設定する（EV 17.97）。
        df_preds.loc[df_preds['umaban'] == 1, 'normalized_pred_win'] = 0.15
        df_preds.loc[df_preds['umaban'] == 1, 'tansho_odds'] = 119.8

    # 2. 自動投票マネージャーと模擬投票エンジンの初期化
    from voting.umaca_voter import UmacaVoter
    voter = UmacaVoter(use_mock=True)
    manager = AutoVoterManager(
        voter=voter,
        target_ev=1.3,
        min_win_prob=0.10,
        default_amount=100
    )

    # 3. 判定と模擬投票の実行
    print("\nProcessing predictions through AutoVoterManager (UNIFIED)...")
    success = manager.process_race_prediction_unified(race_id, df_preds)
    
    if success:
        print("\n[TEST SUCCESS] Integration test complete!")
    else:
        print("\n[TEST FAILED] Auto-voting failed or skipped.")

if __name__ == '__main__':
    main()
