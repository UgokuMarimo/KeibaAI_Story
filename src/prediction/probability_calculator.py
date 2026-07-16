import pandas as pd
import itertools

class ProbabilityCalculator:
    """
    Harvilleの公式を用いて、各馬の単勝確率（Win Probability）から
    馬単、3連単などの組み合わせ確率を計算するクラス。
    
    Harville's Formula:
    P(1st=i, 2nd=j) = P(1st=i) * (P(1st=j) / (1 - P(1st=i)))
    
    前提:
    - 入力のwin_probsは合計が1.0になるように正規化されていること。
    """
    
    def __init__(self, win_probs: dict):
        """
        Args:
            win_probs (dict): {umaban (int/str): probability (float)}
                              例: {1: 0.3, 2: 0.2, ...}
        """
        self.win_probs = win_probs
        self.umabans = list(win_probs.keys())
        
        # 検証: 合計が概ね1.0であること
        total_prob = sum(win_probs.values())
        if not (0.99 <= total_prob <= 1.01):
            print(f"[WARN] Total win probability is {total_prob:.4f}, not 1.0. Normalizing...")
            self.win_probs = {k: v / total_prob for k, v in win_probs.items()}

    def calculate_exacta(self, first: int, second: int) -> float:
        """
        馬単 (Exacta) P(1st=first, 2nd=second) を計算
        """
        p_1 = self.win_probs.get(first, 0.0)
        p_2 = self.win_probs.get(second, 0.0)
        
        if p_1 == 0 or p_2 == 0:
            return 0.0
            
        # P(2nd=j | 1st=i) = P(j) / (1 - P(i))
        prob = p_1 * (p_2 / (1.0 - p_1))
        return prob

    def calculate_trifecta(self, first: int, second: int, third: int) -> float:
        """
        3連単 (Trifecta) P(1st=first, 2nd=second, 3rd=third) を計算
        """
        p_1 = self.win_probs.get(first, 0.0)
        p_2 = self.win_probs.get(second, 0.0)
        p_3 = self.win_probs.get(third, 0.0)
        
        if p_1 == 0 or p_2 == 0 or p_3 == 0:
            return 0.0
        
        # Term 1: P(1st=i) = p_1
        # Term 2: P(2nd=j | 1st=i) = p_2 / (1 - p_1)
        # Term 3: P(3rd=k | 1st=i, 2nd=j) = p_3 / (1 - p_1 - p_2)
        
        term1 = p_1
        term2 = p_2 / (1.0 - p_1)
        term3 = p_3 / (1.0 - p_1 - p_2)
        
        return term1 * term2 * term3

    def get_all_exacta_probs(self) -> pd.DataFrame:
        """
        全ての馬単の組み合わせ確率を計算してDataFrameで返す
        """
        combinations = []
        for i, j in itertools.permutations(self.umabans, 2):
            prob = self.calculate_exacta(i, j)
            combinations.append({
                '1着': i,
                '2着': j,
                'probability': prob
            })
        
        df = pd.DataFrame(combinations)
        return df.sort_values('probability', ascending=False).reset_index(drop=True)

    def get_all_trifecta_probs(self) -> pd.DataFrame:
        """
        全ての3連単の組み合わせ確率を計算してDataFrameで返す
        注意: 頭数が多いと計算量が増える (16頭 -> 3360通り)
        """
        combinations = []
        for i, j, k in itertools.permutations(self.umabans, 3):
            prob = self.calculate_trifecta(i, j, k)
            combinations.append({
                '1着': i,
                '2着': j,
                '3着': k,
                'probability': prob
            })
            
        df = pd.DataFrame(combinations)
        return df.sort_values('probability', ascending=False).reset_index(drop=True)

    def get_all_quinella_probs(self) -> pd.DataFrame:
        """
        馬連 (Quinella) の確率計算
        馬単 P(i, j) + P(j, i)
        """
        exacta_df = self.get_all_exacta_probs()
        
        # combinations (set) to avoid duplicates like (1, 2) and (2, 1)
        quinella_probs = {}
        
        for _, row in exacta_df.iterrows():
            horse1 = int(row['1着'])
            horse2 = int(row['2着'])
            prob = row['probability']
            
            key = tuple(sorted([horse1, horse2]))
            if key in quinella_probs:
                quinella_probs[key] += prob
            else:
                quinella_probs[key] = prob
                
        results = []
        for (h1, h2), prob in quinella_probs.items():
            results.append({
                '1頭目': h1,
                '2頭目': h2,
                'probability': prob
            })
            
        df = pd.DataFrame(results)
        return df.sort_values('probability', ascending=False).reset_index(drop=True)

    def get_all_trio_probs(self) -> pd.DataFrame:
        """
        3連複 (Trio) の確率計算
        3連単の全順列 (6パターン) の和
        """
        trifecta_df = self.get_all_trifecta_probs()
        
        trio_probs = {}
        
        for _, row in trifecta_df.iterrows():
            h1 = int(row['1着'])
            h2 = int(row['2着'])
            h3 = int(row['3着'])
            prob = row['probability']
            
            key = tuple(sorted([h1, h2, h3]))
            if key in trio_probs:
                trio_probs[key] += prob
            else:
                trio_probs[key] = prob
        
        results = []
        for (h1, h2, h3), prob in trio_probs.items():
            results.append({
                '1頭目': h1,
                '2頭目': h2,
                '3頭目': h3,
                'probability': prob
            })
            
        df = pd.DataFrame(results)
        return df.sort_values('probability', ascending=False).reset_index(drop=True)
