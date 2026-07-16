# C:\KeibaAI\src\voting\mock_voter.py
import os
import json
import time
from typing import Dict, List, Any
from voting.voter_interface import BaseVoter

class MockVoter(BaseVoter):
    """
    平日開発およびテスト用の擬似投票エンジン。
    実際のブラウザ操作や通信を行わず、ローカルファイルに投票履歴を保存し残高をシミュレートする。
    """
    
    def __init__(self, initial_balance: float = 10000.0, history_file: str = 'C:/KeibaAI/data/processed/mock_vote_history.json'):
        self.balance = initial_balance
        self.history_file = history_file
        self.logged_in = False
        
        # 履歴保存ディレクトリの作成
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        
        # 保存済みの残高・履歴があればロード
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.balance = data.get('balance', initial_balance)
            except Exception:
                pass

    def login(self) -> bool:
        print("[MOCK-VOTER] Logging in to JRA UMACA Smart (Simulated)...")
        time.sleep(0.5) # 通信遅延の再現
        self.logged_in = True
        print("[MOCK-VOTER] Login Success!")
        return True

    def get_balance(self) -> float:
        if not self.logged_in:
            print("[MOCK-VOTER ERROR] Must login before getting balance.")
            return 0.0
        print(f"[MOCK-VOTER] Current Balance: {self.balance:,} 円")
        return self.balance

    def vote(self, race_id: str, bets: List[Dict[str, Any]]) -> bool:
        if not self.logged_in:
            print("[MOCK-VOTER ERROR] Must login before voting.")
            return False
            
        if not bets:
            print("[MOCK-VOTER] No bets specified. Skipping.")
            return True

        total_cost = sum(bet['amount'] for bet in bets)
        print(f"[MOCK-VOTER] Processing vote for Race: {race_id} (Total Bets: {len(bets)} items, Total Cost: {total_cost:,} 円)")
        
        if self.balance < total_cost:
            print(f"[MOCK-VOTER ERROR] Insufficient balance! Required: {total_cost:,} 円, Available: {self.balance:,} 円")
            return False

        time.sleep(1.0) # 投票画面の遷移ディレイ再現
        
        # 残高の減算と履歴データの保存
        self.balance -= total_cost
        
        # 履歴の読み込み
        history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    history = history_data.get('history', [])
            except Exception:
                pass
                
        # 今回の投票履歴を追加
        new_entry = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'race_id': race_id,
            'bets': bets,
            'cost': total_cost,
            'remaining_balance': self.balance
        }
        history.append(new_entry)
        
        # ファイルへ保存
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'balance': self.balance,
                    'history': history
                }, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[MOCK-VOTER ERROR] Failed to save history file: {e}")

        print("[MOCK-VOTER] ===== SIMULATED VOTE COMPLETE =====")
        for idx, bet in enumerate(bets):
            print(f"  [{idx+1}] 馬番: {bet['umaban']}番, 賭け式: {bet['bet_type']}, 金額: {bet['amount']:,} 円 (SUCCESS)")
        print(f"  [新残高]: {self.balance:,} 円")
        print("[MOCK-VOTER] ===================================")
        return True

    def close(self):
        print("[MOCK-VOTER] Session closed.")
        self.logged_in = False

    def navigate_to_race_and_bet_type(self, race_id: str, bet_type: str) -> bool:
        print(f"[MOCK-VOTER] Navigated to race {race_id} and bet type {bet_type} (Simulated).")
        return True

    def get_odds_from_page(self) -> Dict[int, float]:
        print("[MOCK-VOTER] Generated dummy odds from mock page.")
        # テスト用のダミーオッズ
        return {13: 15.0, 14: 10.4, 3: 16.7}

    def vote_on_current_page(self, bets: List[Dict[str, Any]]) -> bool:
        # 既存の vote メソッドをそのまま呼ぶ
        return self.vote("", bets)
