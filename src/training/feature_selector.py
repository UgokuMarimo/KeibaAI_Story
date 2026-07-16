import os
import sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from typing import List

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

import config

class FeatureSelector:
    """
    特徴量重要度の分析、貢献度0（または閾値未満）の特徴量の抽出、および
    ドロップ候補のファイルレポート出力を行うクラス。
    """
    def __init__(self):
        pass

    def analyze_importance(self, model: lgb.LGBMClassifier, feature_names: List[str]) -> pd.DataFrame:
        """
        学習済みモデルから Split & Gain 重要度を取得し、DataFrameにまとめて返す。
        """
        importance_split = model.booster_.feature_importance(importance_type='split')
        importance_gain = model.booster_.feature_importance(importance_type='gain')
        
        fi_df = pd.DataFrame({
            'feature': feature_names,
            'importance_split': importance_split,
            'importance_gain': importance_gain
        })
        return fi_df

    def export_candidates_to_drop(self, fi_df: pd.DataFrame, output_dir: str, track_type: str, target_type: str):
        """
        重要度が0の特徴量を抽出し、Configにコピペしやすいテキスト形式およびCSVで保存する。
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # 貢献度0（Split & Gain ともに 0）のものを抽出
        zero_importance_features = fi_df[
            (fi_df['importance_split'] == 0) & (fi_df['importance_gain'] == 0)
        ]['feature'].tolist()
        
        # テキスト形式でのドロップ候補保存
        output_txt_file = os.path.join(output_dir, f'candidates_to_drop_{track_type}_{target_type}.txt')
        with open(output_txt_file, 'w', encoding='utf-8') as f:
            f.write("# Candidates to drop (Zero split & gain importance)\n")
            for feat in zero_importance_features:
                f.write(f"'{feat}',\n")
                
        # 全特徴量の重要度ランキングをCSVで保存
        output_csv_file = os.path.join(output_dir, f'importance_ranking_{track_type}_{target_type}.csv')
        fi_df.sort_values(by='importance_gain', ascending=False).to_csv(output_csv_file, index=False)
        
        print(f"[SUCCESS] Zero importance features count: {len(zero_importance_features)}")
        print(f"-> Saved drop candidates to: {output_txt_file}")
        print(f"-> Saved full ranking CSV to: {output_csv_file}")
