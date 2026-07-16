import os
import sys
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import roc_auc_score
from joblib import dump, load
from typing import Dict, Any

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

import config

class ModelTrainer:
    """
    モデル（LightGBM）のハイパーパラメータ取得、学習、予測、
    評価指標（ROC-AUC）算出、モデルとアーティファクトの保存・ロードを管理するクラス。
    """
    def __init__(self):
        pass

    def get_model_params(self, track_type: str, target_type: str) -> Dict[str, Any]:
        """
        config.py から指定されたトラックと予測ターゲットに対応するハイパーパラメータを取得する。
        """
        param_key = f"LGB_PARAMS_{target_type.upper()}_{track_type.upper()}"
        params = getattr(config, param_key, None)
        if params is None:
            raise ValueError(f"Parameters for {param_key} not found in config.py")
        return params.copy()

    def train(self, X: pd.DataFrame, y: pd.Series, sample_weight: np.ndarray = None, params: Dict[str, Any] = None) -> lgb.LGBMClassifier:
        """
        LightGBM分類器をインスタンス化し、学習を実行する。
        """
        if params is None:
            raise ValueError("Parameters must be provided for training.")
            
        model = lgb.LGBMClassifier(**params)
        model.fit(X.values, y, sample_weight=sample_weight)
        return model

    def predict_proba(self, model: lgb.LGBMClassifier, X: pd.DataFrame) -> np.ndarray:
        """
        テストデータに対する1着（または3着以内）の確率予測値を算出して返す。
        """
        return model.predict_proba(X)[:, 1]

    def evaluate(self, y_true: pd.Series, y_pred_proba: np.ndarray) -> float:
        """
        ROC-AUC スコアを計算して返す。
        """
        return float(roc_auc_score(y_true, y_pred_proba))

    def save_artifacts(self, model: lgb.LGBMClassifier, imputer, output_dir: str, track_type: str, target_type: str):
        """
        本番モデルおよび Imputer を指定ディレクトリにシリアライズ保存する。
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Imputer の保存
        imputer_path = os.path.join(output_dir, config.IMPUTER_FILE_TEMPLATE.format(track=track_type, target_type=target_type))
        dump(imputer, imputer_path)
        
        # モデルの保存
        model_path = os.path.join(output_dir, config.MODEL_FILE_TEMPLATE.format(track=track_type, target_type=target_type))
        model.booster_.save_model(model_path)
        
        print(f"[SUCCESS] Saved model and imputer to: {output_dir}")
