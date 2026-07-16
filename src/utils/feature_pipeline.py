"""
互換性維持のためのアダプター（ラッパー）モジュール。
既存の呼び出し元（build_features.py や予測スクリプトなど）を変更することなく、
新しくリファクタリングされた features.feature_pipeline.FeatureEngineerPipeline を実行します。
"""

import pandas as pd
from typing import List, Dict, Tuple, Any
from sklearn.preprocessing import LabelEncoder
import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)

from features.feature_pipeline import FeatureEngineerPipeline, LapAnalyzer, RunningStyleEstimator

# 各関数のインターフェースを維持したまま、内部でパイプラインオブジェクトのメソッドへ処理を委譲します。

def preprocess_and_clean(df: pd.DataFrame, time_scaler: dict = None) -> Tuple[pd.DataFrame, dict]:
    pipeline = FeatureEngineerPipeline()
    return pipeline.preprocess_and_clean(df, time_scaler)

def add_past_race_features(df: pd.DataFrame, num_past_races: int, past_race_features: List[str]) -> pd.DataFrame:
    pipeline = FeatureEngineerPipeline()
    return pipeline.add_past_race_features(df, num_past_races, past_race_features)

def engineer_advanced_features(df: pd.DataFrame, num_past_races: int, jockey_rates: Dict[str, pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    pipeline = FeatureEngineerPipeline()
    return pipeline.engineer_advanced_features(df, num_past_races, jockey_rates)

def add_race_level_features(df: pd.DataFrame) -> pd.DataFrame:
    pipeline = FeatureEngineerPipeline()
    return pipeline.add_race_level_features(df)

def encode_and_finalize(df: pd.DataFrame, categorical_features: List[str], label_encoders: Dict[str, LabelEncoder] = None) -> Tuple[pd.DataFrame, Dict[str, LabelEncoder]]:
    pipeline = FeatureEngineerPipeline()
    return pipeline.encode_and_finalize(df, categorical_features, label_encoders)

# 予測側等で直接 LapAnalyzer を呼んでいる箇所がある場合に備え、互換クラスとして公開します。
class CompatibleLapAnalyzer(LapAnalyzer):
    pass