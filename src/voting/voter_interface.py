# C:\KeibaAI\src\voting\voter_interface.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any

class BaseVoter(ABC):
    """
    投票システムの抽象ベースクラス。
    UMACA、即PAT、Mock（テスト用）のすべての投票エンジンはこのインターフェースを実装する。
    """
    
    @abstractmethod
    def login(self) -> bool:
        """
        投票システムへのログインを実行する。
        """
        pass
        
    @abstractmethod
    def get_balance(self) -> float:
        """
        現在の投票口座/UMACA残高を取得する。
        """
        pass
        
    @abstractmethod
    def vote(self, race_id: str, bets: List[Dict[str, Any]]) -> bool:
        """
        指定されたレースに対して投票（購入）を実行する。
        
        bets のフォーマット例:
        [
            {
                'umaban': 12,       # 馬番 (int)
                'bet_type': 'win',  # 賭け式 ('win': 単勝, 'place': 複勝, etc.)
                'amount': 100       # 金額 (int, 円単位)
            }
        ]
        """
        pass

    @abstractmethod
    def close(self):
        """
        ブラウザやセッションをクローズし、クリーンアップする。
        """
        pass

    def navigate_to_race_and_bet_type(self, race_id: str, bet_type: str) -> bool:
        """
        投票のために競馬場・レース・式別を選択し、馬番選択画面へ遷移する（一本化フロー用）。
        """
        return True

    def get_odds_from_page(self) -> Dict[int, float]:
        """
        馬番選択画面からリアルタイムオッズを一括取得する（一本化フロー用）。
        """
        return {}

    def vote_on_current_page(self, bets: List[Dict[str, Any]]) -> bool:
        """
        現在開いている馬番選択画面から、選択した馬・金額で投票を完了させる（一本化フロー用）。
        """
        return True
