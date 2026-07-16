import numpy as np
from itertools import permutations

class ProbabilityCalculator:
    """
    Calculates probabilities for various betting ticket types using Harville's Formula.
    """

    @staticmethod
    def harville_formula(win_probs: dict, combination: list) -> float:
        """
        Calculates the probability of a specific ordered combination (e.g., 1-2-3)
        occurring using Harville's Formula.

        Args:
            win_probs (dict): Dictionary mapping horse_id/number to its win probability (0.0 to 1.0).
            combination (list): List of horse_ids/numbers in the order of finish (1st, 2nd, 3rd, ...).

        Returns:
            float: The calculated probability of this exact order.
        """
        prob = 1.0
        remaining_prob_sum = 1.0
        
        current_denominator_subtraction = 0.0
        
        for horse in combination:
            if horse not in win_probs:
                raise ValueError(f"Horse {horse} not found in win probabilities.")
            
            p_horse = win_probs[horse]
            
            # Harville Formula Denominator: 1 - sum(probabilities of previous horses)
            # This assumes the input probabilities sum to 1.
            # If not, we should strictly use: sum(probabilities of REMAINING horses)
            # Let's calculate the sum of remaining candidates for robustness.
            
            denominator = remaining_prob_sum - current_denominator_subtraction
            
            # Robustness check: if the remaining probability is effectively zero, return 0
            if denominator <= 1e-9:
                return 0.0
                
            prob *= (p_horse / denominator)
            
            current_denominator_subtraction += p_horse
            
        return prob

    @staticmethod
    def normalize_probabilities(win_probs: dict) -> dict:
        """
        Normalizes probabilities so they sum to 1.0.
        """
        total = sum(win_probs.values())
        if total == 0:
            return win_probs
        return {k: v / total for k, v in win_probs.items()}

    def calculate_trifecta_probabilities(self, win_probs: dict) -> dict:
        """
        Calculates probabilities for all possible Trifecta (3-Ren-Tan) combinations.
        
        Returns:
            dict: Key is tuple (1st, 2nd, 3rd), Value is probability.
        """
        normalized_probs = self.normalize_probabilities(win_probs)
        horses = list(normalized_probs.keys())
        combinations = permutations(horses, 3)
        
        results = {}
        for comb in combinations:
            prob = self.harville_formula(normalized_probs, comb)
            results[comb] = prob
            
        return results

    def calculate_exacta_probabilities(self, win_probs: dict) -> dict:
        """
        Calculates probabilities for all possible Exacta (Uma-Tan) combinations.
        """
        normalized_probs = self.normalize_probabilities(win_probs)
        horses = list(normalized_probs.keys())
        combinations = permutations(horses, 2)
        
        results = {}
        for comb in combinations:
            prob = self.harville_formula(normalized_probs, comb)
            results[comb] = prob
            
        return results

# Example Usage
if __name__ == "__main__":
    # Example: 5 horses with win probabilities
    example_probs = {
        "1": 0.40,
        "2": 0.30,
        "3": 0.15,
        "4": 0.10,
        "5": 0.05
    }
    
    calculator = ProbabilityCalculator()
    
    print("--- Exacta (Uma-Tan) Probabilities ---")
    exacta_probs = calculator.calculate_exacta_probabilities(example_probs)
    # Sort by probability descending
    sorted_exacta = sorted(exacta_probs.items(), key=lambda x: x[1], reverse=True)
    for comb, prob in sorted_exacta[:5]:
        print(f"{comb}: {prob:.4f}")

    print("\n--- Trifecta (3-Ren-Tan) Probabilities ---")
    trifecta_probs = calculator.calculate_trifecta_probabilities(example_probs)
    sorted_trifecta = sorted(trifecta_probs.items(), key=lambda x: x[1], reverse=True)
    for comb, prob in sorted_trifecta[:5]:
        print(f"{comb}: {prob:.4f}")
