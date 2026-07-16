import os
import sys
import pandas as pd
import numpy as np
import optuna
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from typing import Tuple, Dict, Any

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

import config

class HyperparameterTuner:
    """
    Optunaを使用してLightGBMの最適なハイパーパラメータを探索・保存するクラス。
    """
    def __init__(self):
        pass

    def tune(self, X: pd.DataFrame, y: pd.Series, sample_weights: np.ndarray, n_trials: int, n_jobs: int = 1) -> Tuple[Dict[str, Any], float]:
        """
        Optunaによる最適ハイパーパラメータの探索を実行する。
        """
        def objective(trial: optuna.trial.Trial) -> float:
            param = {
                'objective': 'binary', 
                'metric': 'auc', 
                'verbosity': -1,
                'boosting_type': 'gbdt', 
                'class_weight': 'balanced',
                'num_leaves': trial.suggest_int('num_leaves', 20, 150),
                'max_depth': trial.suggest_int('max_depth', 4, 12),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15),
                'n_estimators': trial.suggest_int('n_estimators', 100, 600, step=50),
                'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
                'lambda_l1': trial.suggest_float('lambda_l1', 1e-8, 10.0, log=True),
                'lambda_l2': trial.suggest_float('lambda_l2', 1e-8, 10.0, log=True),
                'n_jobs': -1, # LightGBMスレッド並列
            }
            
            # データ分割
            X_train, X_valid, y_train, y_valid, w_train, _ = train_test_split(
                X, y, sample_weights, test_size=0.2, random_state=42, stratify=y
            )
            
            model = lgb.LGBMClassifier(**param)
            model.fit(
                X_train, y_train, 
                sample_weight=w_train,
                eval_set=[(X_valid, y_valid)], 
                callbacks=[lgb.early_stopping(10, verbose=False)]
            )
            
            preds = model.predict_proba(X_valid)[:, 1]
            return float(roc_auc_score(y_valid, preds))

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, n_jobs=n_jobs)
        
        return study.best_params, study.best_value

    def save_best_params(self, best_params: Dict[str, Any], best_score: float, output_dir: str, track_type: str, target_type: str):
        """
        探索結果（最良パラメータとAUCスコア）を指定テキストファイルに保存する。
        """
        os.makedirs(output_dir, exist_ok=True)
        result_path = os.path.join(output_dir, config.PARAMS_FILE_TEMPLATE.format(track=track_type, target_type=target_type))
        
        with open(result_path, 'w') as f:
            f.write(f"Best trial AUC: {best_score}\nBest params:\n")
            for key, value in best_params.items():
                f.write(f"  '{key}': {value},\n")
                
        print(f"[SUCCESS] Saved tuning results to: {result_path}")
