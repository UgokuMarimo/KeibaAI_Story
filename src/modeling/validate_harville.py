import json
import os
import sys
from probability_calculator import ProbabilityCalculator

# Path setup to import local modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

def load_odds(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def main():
    # 1. Load Scraped Odds
    odds_file = r"c:\KeibaAI\data\odds\3rentan_latest.json"
    if not os.path.exists(odds_file):
        print(f"Odds file not found: {odds_file}")
        return

    odds_data = load_odds(odds_file)
    print(f"Loaded {len(odds_data)} odds records.")
    
    # Create a lookup dictionary for odds: (1st, 2nd, 3rd) -> Odds
    odds_lookup = {}
    horses = set()
    for entry in odds_data:
        key = (entry['1st'], entry['2nd'], entry['3rd'])
        try:
            odds_val = float(entry['odds'])
            odds_lookup[key] = odds_val
            horses.add(entry['1st'])
            horses.add(entry['2nd'])
            horses.add(entry['3rd'])
        except ValueError:
            pass # Skip invalid odds

    print(f"Identified {len(horses)} horses: {sorted(list(horses))}")

    # 2. Define "AI Model" Win Probabilities (Simulation)
    # in a real scenario, these would come from LightGBM/XGBoost predictions
    # Let's assign some probabilities favoring common favorites for demonstration
    # Example: Horse 1 is strong, Horse 5 is weak.
    
    # Create dummy probabilities for the detected horses
    # Distribute 1.0 probability somewhat randomly but with a trend
    num_horses = len(horses)
    
    # Simple skew: prob proportional to (num_horses - horse_num + 1)
    # So horse 1 has highest, horse 10 has lowest.
    raw_probs = {}
    total_weight = 0
    for h in horses:
        weight = (num_horses - int(h) + 1)
        raw_probs[h] = weight
        total_weight += weight
        
    win_probs = {h: w / total_weight for h, w in raw_probs.items()}
    
    print("\n--- Simulated AI Win Probabilities ---")
    for h in sorted(win_probs.keys(), key=lambda k: int(k)):
        print(f"Horse {h}: {win_probs[h]:.4f}")

    # 3. Calculate Ticket Probabilities using Harville's Formula
    calculator = ProbabilityCalculator()
    trifecta_probs = calculator.calculate_trifecta_probabilities(win_probs)
    
    # 4. Calculate Expected Value (EV) and Identify High Value Bets
    # EV = Probability * Odds
    # Good Bet if EV > 1.0 (theoretically), or > 0.8 (considering take-out rate ~75%)
    # Let's just find the top EV bets.
    
    ev_list = []
    
    for comb, prob in trifecta_probs.items():
        # comb is tuple ('1', '2', '3')
        if comb in odds_lookup:
            odds = odds_lookup[comb]
            ev = prob * odds
            ev_list.append({
                "combination": comb,
                "probability": prob,
                "odds": odds,
                "ev": ev
            })
    
    # Sort by EV descending
    ev_list.sort(key=lambda x: x['ev'], reverse=True)
    
    print("\n--- Top 10 High EV 3-Ren-Tan Bets ---")
    print(f"{'Combination':<15} | {'Win Prob(%)':<12} | {'Odds':<8} | {'EV':<6}")
    print("-" * 50)
    for bet in ev_list[:10]:
        comb_str = "-".join(bet['combination'])
        print(f"{comb_str:<15} | {bet['probability']*100:.4f}%      | {bet['odds']:<8.1f} | {bet['ev']:.4f}")

    print("\nValidation Complete. Harville's Formula successfully applied to scraped odds.")

if __name__ == "__main__":
    main()
