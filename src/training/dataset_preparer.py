import os
import sys
import gc
import pandas as pd
import numpy as np
from sklearn.impute import SimpleImputer
from typing import Tuple, List, Dict, Any

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

import config

class DatasetPreparer:
    """
    特徴量データのロード、メモリ最適化、特徴量/ラベル切り出し、
    サンプルウェイト計算、欠損値補完（Imputer）を担当するクラス。
    """
    def __init__(self):
        self.feature_columns = None # 学習時に決定された最終特徴量列リスト

    def load_data(self, track_type: str) -> pd.DataFrame | None:
        """
        指定されたトラックのエンコード済みデータを読み込み、メモリダウンキャストを行う。
        """
        file_path = os.path.join(config.ENCODED_DIR, config.EXPERIMENT_VERSION, f'encoded_data_{track_type}.csv')
        if not os.path.exists(file_path):
            print(f"[ERROR] Data file not found: {file_path}")
            return None
            
        print(f"--- Loading data from: {file_path} ---")
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig', low_memory=False)
        except Exception as e:
            print(f"[WARN] Failed to load with utf-8-sig encoding ({e}). Falling back to default parser...")
            df = pd.read_csv(file_path, low_memory=False)
            
        # メモリ節約のため、float64カラムをfloat32にダウンキャスト
        float_cols = df.select_dtypes(include=['float64']).columns
        if len(float_cols) > 0:
            print(f"Downcasting {len(float_cols)} float64 columns to float32 for memory efficiency...")
            df[float_cols] = df[float_cols].astype('float32')
            
        gc.collect()
        return df

    def prepare_features_and_labels(self, df: pd.DataFrame, track_type: str, target_type: str = None, is_train: bool = True) -> Tuple[pd.DataFrame, pd.Series]:
        """
        特徴量(X)と目的変数(y)を分離し、不要カラム・リークカラムを削除する。
        """
        df_copy = df.copy()
        
        # 目的変数
        y_raw = df_copy['着順'] if '着順' in df_copy.columns else None

        if not is_train and self.feature_columns is not None:
            # 評価・予測時は、学習時に決定された最終特徴量カラムリストに完全に一致させる
            X = pd.DataFrame(index=df_copy.index)
            for col in self.feature_columns:
                if col in df_copy.columns:
                    X[col] = df_copy[col]
                else:
                    X[col] = np.nan
            return X, y_raw

        # 学習時の処理 (または状態がない場合)
        # 共通の削除対象カラム
        cols_to_drop = [
            'race_id', 'horse_id', '騎手', '馬', '日付', 'レース名', '開催', '通過順', 
            '芝・ダート', 
            f'過去{config.NUM_PAST_RACES}走_条件_走破時間_scaled_times'
        ]
        
        # レース結果に紐づくリーク情報の削除
        leak_features_current_race = config.LEAKAGE_FEATURES
        cols_to_drop.extend([c for c in leak_features_current_race if c not in cols_to_drop])

        # 過去の日付カラムも削除
        past_date_cols = [f'日付{i}' for i in range(1, config.NUM_PAST_RACES + 2)]
        cols_to_drop.extend(past_date_cols)

        # 古いレースレベル特徴量を削除
        old_scaled_race_level_features = [
            '走破時間_scaled_race_mean', '走破時間_scaled_race_max', '走破時間_scaled_race_min', 
            '走破時間_scaled_race_dev', '走破時間_scaled_race_max_diff', '走破時間_scaled_race_min_diff'
        ]
        cols_to_drop.extend(old_scaled_race_level_features)

        # Configで指定された不要な特徴量を削除
        features_to_drop_conf = config.FEATURES_TO_DROP
        cols_to_drop.extend(features_to_drop_conf.get('common', []))
        cols_to_drop.extend(features_to_drop_conf.get(track_type, []))
        
        if target_type is not None:
            cols_to_drop.extend(features_to_drop_conf.get(f"{track_type}_{target_type}", []))
            
        # 重複を除去し、'year' と '着順' は一時的に残す
        cols_to_drop = [c for c in list(set(cols_to_drop)) if c not in ['year', '着順']]
        
        # インプレース削除でメモリ節約
        cols_to_drop_existing = [col for col in cols_to_drop if col in df_copy.columns]
        print(f"[INFO] Dropping {len(cols_to_drop_existing)} columns inplace to save memory...")
        df_copy.drop(columns=cols_to_drop_existing, errors='ignore', inplace=True)
        
        # 全てがNaNのカラムを削除
        nan_cols = df_copy.columns[df_copy.isna().all()].tolist()
        if nan_cols:
            print(f"[INFO] Dropping {len(nan_cols)} all-NaN columns inplace...")
            df_copy.drop(columns=nan_cols, errors='ignore', inplace=True)
        
        # object型（文字列）のカラムを削除
        object_cols = df_copy.select_dtypes(include=['object']).columns.tolist()
        if object_cols:
            print(f"[INFO] Dropping remaining object-type columns inplace: {object_cols}")
            df_copy.drop(columns=object_cols, errors='ignore', inplace=True)
        
        # 特徴量 X として 'year' と '着順' を除外
        cols_to_exclude_from_X = [c for c in ['year', '着順'] if c in df_copy.columns]
        X = df_copy.drop(columns=cols_to_exclude_from_X, errors='ignore')
        
        if is_train:
            self.feature_columns = list(X.columns)
            
        gc.collect()
        return X, y_raw

    def calculate_sample_weights(self, years: pd.Series) -> np.ndarray:
        """
        年度に基づいて学習データの重みを計算する (直近年度ほど重くする)。
        """
        if years.empty:
            return np.array([])
        min_year = years.min()
        weights = 1.0 + (years - min_year) * 0.2
        return weights.values

    def fit_transform_imputer(self, X: pd.DataFrame) -> Tuple[pd.DataFrame, SimpleImputer]:
        """
        学習データに対してインプレース前補完を行い、SimpleImputerをフィット・適用して返す。
        """
        X_copy = X.copy()
        print("[INFO] Pre-imputing NaNs using pandas to avoid float64 memory spikes...")
        for col in X_copy.columns:
            col_mean = X_copy[col].mean()
            if pd.isna(col_mean):
                X_copy[col].fillna(0.0, inplace=True)
            else:
                X_copy[col].fillna(col_mean, inplace=True)
                
        gc.collect()
        
        # SimpleImputerの内部コピーを完全に禁止し、メモリ使用を抑える
        imputer = SimpleImputer(strategy='mean', copy=False)
        X_imputed_array = imputer.fit_transform(X_copy)
        X_imputed = pd.DataFrame(X_imputed_array, columns=X_copy.columns)
        
        return X_imputed, imputer

    def transform_imputer(self, X: pd.DataFrame, imputer: SimpleImputer) -> pd.DataFrame:
        """
        評価・予測用データに対して、既存の SimpleImputer を適用して返す。
        """
        X_copy = X.copy()
        # 同様に前補完を実行してロバストにする
        for col in X_copy.columns:
            col_mean = X_copy[col].mean()
            if pd.isna(col_mean):
                X_copy[col].fillna(0.0, inplace=True)
            else:
                X_copy[col].fillna(col_mean, inplace=True)
                
        X_imputed_array = imputer.transform(X_copy)
        return pd.DataFrame(X_imputed_array, columns=X_copy.columns)
