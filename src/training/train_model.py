"""
モデル学習、評価、本番モデル構築を行うための統合司令塔（Facade/Controller）スクリプト。

■ 使い方
python src/training/train_model.py --mode [eval|prod|tune|selection] --target [win|place] --track [turf|dirt] [options]
"""
import sys
import os
import gc
import argparse
from typing import Dict, Any

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import config
from training.dataset_preparer import DatasetPreparer
from training.model_trainer import ModelTrainer
from training.hyperparameter_tuner import HyperparameterTuner
from training.feature_selector import FeatureSelector

class TrainingPipeline:
    """
    データ準備、学習、検証、チューニング、特徴量選択の各担当クラスを
    束ねて全体のトレーニングパイプラインを実行するオーケストレータークラス。
    """
    def __init__(self):
        self.preparer = DatasetPreparer()
        self.trainer = ModelTrainer()
        self.tuner = HyperparameterTuner()
        self.selector = FeatureSelector()

    def run_evaluation(self, target_type: str, track_type: str, evaluation_year: int):
        """評価モード: 指定されたテスト年で性能を評価する"""
        print(f"\n--- [EVALUATION MODE] Target: {target_type}, Track: {track_type}, Test Year: {evaluation_year} ---")
        
        # 1. データの読み込み
        df = self.preparer.load_data(track_type)
        if df is None: return

        # 時系列分割
        train_df = df[df['year'] < evaluation_year].copy()
        test_df = df[df['year'] == evaluation_year].copy()
        if train_df.empty or test_df.empty:
            print(f"[WARN] Not enough data for evaluation. Train: {len(train_df)}, Test: {len(test_df)}"); return

        # 2. 特徴量とラベルの抽出
        X_train, y_train_raw = self.preparer.prepare_features_and_labels(train_df, track_type, target_type, is_train=True)
        X_test, y_test_raw = self.preparer.prepare_features_and_labels(test_df, track_type, target_type, is_train=False)

        y_train = (y_train_raw == 1) if target_type == 'win' else (y_train_raw <= 3)
        y_test = (y_test_raw == 1) if target_type == 'win' else (y_test_raw <= 3)

        # 3. 欠損値補完 (Imputer)
        X_train_imputed, imputer = self.preparer.fit_transform_imputer(X_train)
        X_test_imputed = self.preparer.transform_imputer(X_test, imputer)

        # 4. 時系列サンプルの重み計算
        weights = self.preparer.calculate_sample_weights(train_df['year'])
        print(f"Applying sample weights (min: {weights.min():.2f}, max: {weights.max():.2f})")

        # 5. パラメータの取得と学習
        params = self.trainer.get_model_params(track_type, target_type)
        model = self.trainer.train(X_train_imputed, y_train, sample_weight=weights, params=params)

        # 6. 予測と評価指標の算出
        y_pred_proba = self.trainer.predict_proba(model, X_test_imputed)
        auc_score = self.trainer.evaluate(y_test, y_pred_proba)

        print(f"\n>>> RESULT for {track_type.upper()} {target_type.upper()}:")
        print(f"    Test Set AUC: {auc_score:.4f}")
        print("-" * 50)

    def run_production(self, target_type: str, track_type: str):
        """本番モデル構築モード: 全データを使用して本番予測用モデルを学習・保存する"""
        print(f"\n--- [PRODUCTION MODE] Building model for {target_type} / {track_type} ---")
        
        # 1. データの読み込み
        df = self.preparer.load_data(track_type)
        if df is None: return

        # 2. 特徴量とラベルの抽出
        X, y_raw = self.preparer.prepare_features_and_labels(df, track_type, target_type)
        y = (y_raw == 1) if target_type == 'win' else (y_raw <= 3)

        # 本番モデル保存先の設定
        output_dir = os.path.join(config.MODEL_DIR_BASE, config.EXPERIMENT_VERSION)
        os.makedirs(output_dir, exist_ok=True)
        print(f"Models will be saved to: {output_dir}")

        # 使用特徴量一覧の保存
        used_features = list(X.columns)
        features_path = os.path.join(output_dir, f'features_{track_type}_{target_type}.txt')
        with open(features_path, 'w', encoding='utf-8') as f:
            for feature in used_features:
                f.write(f"{feature}\n")
        print(f"Used features list saved to: {features_path}")

        # 3. 欠損値補完 (Imputer)
        X_imputed, imputer = self.preparer.fit_transform_imputer(X)

        # 4. 時系列サンプルの重み計算
        weights = self.preparer.calculate_sample_weights(df['year'])
        print(f"Applying sample weights (min: {weights.min():.2f}, max: {weights.max():.2f})")

        # 5. パラメータの取得と学習
        params = self.trainer.get_model_params(track_type, target_type)
        model = self.trainer.train(X_imputed, y, sample_weight=weights, params=params)

        # 6. 本番モデルとImputerの保存
        self.trainer.save_artifacts(model, imputer, output_dir, track_type, target_type)
        print("-" * 50)

    def run_tuning(self, target_type: str, track_type: str, n_trials: int, n_jobs: int):
        """チューニングモード: Optunaを使いハイパーパラメータを探索する"""
        print(f"\n--- [TUNING MODE] Tuning for {target_type} / {track_type} with {n_jobs} parallel jobs ---")
        
        # 1. データの読み込み
        df = self.preparer.load_data(track_type)
        if df is None: return

        # 時系列分割 (テスト年より前のデータをチューニングに使用)
        train_df = df[df['year'] < config.EVALUATION_YEAR].copy()
        X, y_raw = self.preparer.prepare_features_and_labels(train_df, track_type, target_type)
        y = (y_raw == 1) if target_type == 'win' else (y_raw <= 3)
        
        # 2. 欠損値補完 (Imputer)
        X_imputed, _ = self.preparer.fit_transform_imputer(X)

        # 3. 時系列サンプルの重み計算
        weights = self.preparer.calculate_sample_weights(train_df['year'])

        # 4. チューニングの実行
        best_params, best_auc = self.tuner.tune(X_imputed, y, sample_weights=weights, n_trials=n_trials, n_jobs=n_jobs)

        print("\n--- Optimization Finished! ---")
        print(f"Best trial AUC: {best_auc:.4f}")
        print("Best params:")
        for key, value in best_params.items():
            print(f"  '{key}': {value},")

        # 結果の保存
        model_name = f"{target_type}_{track_type}"
        result_dir = os.path.join(config.TUNING_RESULTS_DIR, model_name)
        self.tuner.save_best_params(best_params, best_auc, result_dir, track_type, target_type)
        print("-" * 50)

    def run_feature_selection(self, target_type: str, track_type: str):
        """特徴量選択モード: デフォルトパラメータで学習し重要度の低い特徴量を抽出する"""
        print(f"\n--- [SELECTION MODE] Analyzing Feature Importance for {target_type} / {track_type} ---")
        
        # 1. データの読み込み
        df = self.preparer.load_data(track_type)
        if df is None: return

        # 2. 特徴量とラベルの抽出
        X, y_raw = self.preparer.prepare_features_and_labels(df, track_type, target_type)
        y = (y_raw == 1) if target_type == 'win' else (y_raw <= 3)
        
        # 3. 欠損値補完
        X_imputed, _ = self.preparer.fit_transform_imputer(X)

        # 4. パラメータの取得と学習
        params = self.trainer.get_model_params(track_type, target_type)
        model = self.trainer.train(X_imputed, y, sample_weight=None, params=params)

        # 5. 特徴量重要度の分析
        fi_df = self.selector.analyze_importance(model, list(X.columns))

        # 6. ドロップ候補と重要度ランキングの出力保存
        self.selector.export_candidates_to_drop(fi_df, config.FEATURE_SELECTION_DIR, track_type, target_type)
        print("-" * 50)


def main():
    parser = argparse.ArgumentParser(description="Unified model training and evaluation script.")
    parser.add_argument('--mode', type=str, required=True, choices=['eval', 'prod', 'tune', 'selection'], help="Operating mode.")
    parser.add_argument('--target', type=str, required=True, choices=['win', 'place'], help="Prediction target (win or place).")
    parser.add_argument('--track', type=str, required=True, choices=['turf', 'dirt'], help="Track type.")
    parser.add_argument('--evaluation-year', type=int, default=config.EVALUATION_YEAR, help="Test year for eval mode.")
    parser.add_argument('--n-trials', type=int, default=100, help="Number of trials for tune mode.")
    parser.add_argument('--n-jobs', type=int, default=1, help="Number of parallel jobs for tuning.")
    
    args = parser.parse_args()

    pipeline = TrainingPipeline()

    if args.mode == 'eval':
        pipeline.run_evaluation(args.target, args.track, args.evaluation_year)
    elif args.mode == 'prod':
        pipeline.run_production(args.target, args.track)
    elif args.mode == 'tune':
        pipeline.run_tuning(args.target, args.track, args.n_trials, args.n_jobs)
    elif args.mode == 'selection':
        pipeline.run_feature_selection(args.target, args.track)

if __name__ == "__main__":
    main()