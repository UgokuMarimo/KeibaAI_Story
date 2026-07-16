import sys
import os
import argparse
import pandas as pd

# プロジェクトルートの設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

# srcディレクトリもパスに追加 (m04_predict内のimport解決のため)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# codeモジュールとしてではなく、直接インポートできるように調整
# または code.a4_prediction... と記述するが、
# codeフォルダ直下のスクリプト実行構成と合わせるのが無難
from prediction.predict import predict_race
from prediction.probability_calculator import ProbabilityCalculator

def main():
    parser = argparse.ArgumentParser(description="Calculate ticket probabilities for a race.")
    parser.add_argument('race_id', type=str, help='Target race ID (12 digits)')
    args = parser.parse_args()
    
    # 1. レース予測を実行
    print(f"--- Predicting Race: {args.race_id} ---")
    
    # Discord通知などはOFFにして予測のみ実行
    result_df = predict_race(
        race_id=args.race_id,
        run_shap=False, # 今回は確率計算が目的なのでSHAPはスキップ
        use_overseas=False,
        enable_explanation=False,
        send_discord=False
    )
    
    if result_df is None or result_df.empty:
        print("[ERROR] Prediction failed.")
        return

    # 2. 勝率データの抽出と正規化
    # result_df には 'normalized_pred_win' (正規化済み) があるはずだが、
    # 念のため 'pred_win' (raw score) から再計算して確認する
    
    # 馬番と予測スコアの辞書を作成
    # key: 馬番(int), value: raw score
    raw_scores = {}
    for _, row in result_df.iterrows():
        try:
            umaban = int(row['馬番'])
            score = float(row['pred_win'])
            raw_scores[umaban] = score
        except ValueError:
            continue
            
    # 合計1.0に正規化
    total_score = sum(raw_scores.values())
    win_probs = {k: v / total_score for k, v in raw_scores.items()}
    
    print("\n--- Win Probabilities (Normalized) ---")
    for umaban, prob in sorted(win_probs.items(), key=lambda x: x[1], reverse=True):
        horse_name = result_df[result_df['馬番'] == umaban]['馬名'].iloc[0]
        print(f"馬番 {umaban:02d} ({horse_name}): {prob:.4f}")

    # 3. 確率計算
    calculator = ProbabilityCalculator(win_probs)
    
    # 例: 3連単の上位10点
    print("\n--- Top 10 Trifecta (3-Ren-Tan) Combinations ---")
    trifecta_df = calculator.get_all_trifecta_probs()
    print(trifecta_df.head(10).to_string(index=False))
    
    # 例: 3連複の上位10点
    print("\n--- Top 10 Trio (3-Ren-Fuku) Combinations ---")
    trio_df = calculator.get_all_trio_probs()
    print(trio_df.head(10).to_string(index=False))
    
    # 合計確率のチェック (検証用)
    print("\n--- Verification ---")
    print(f"Sum of Exacta Probs: {calculator.get_all_exacta_probs()['probability'].sum():.4f}")
    print(f"Sum of Trifecta Probs: {trifecta_df['probability'].sum():.4f}")

if __name__ == "__main__":
    main()
