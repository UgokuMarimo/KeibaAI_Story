import pandas as pd
import numpy as np

class LapAnalyzer:
    """
    ラップタイム文字列を解析し、レースの質的特徴量（ペース変動、トレンド等）を抽出するクラス。
    """
    # 基準タイム: 1F 12.0秒 (平均スピード時速60km)
    THRESHOLD_SUPER_FAST = 11.0 # ~11.0
    THRESHOLD_FAST = 11.5       # 11.1 ~ 11.5
    THRESHOLD_NORMAL_FAST = 12.0 # 11.6 ~ 12.0
    THRESHOLD_NORMAL_SLOW = 12.5 # 12.1 ~ 12.5
    THRESHOLD_SLOW = 13.0       # 12.6 ~ 13.0

    @staticmethod
    def classify_lap(lap_val: float) -> str:
        if pd.isna(lap_val): 
            return 'unknown'
        if lap_val <= LapAnalyzer.THRESHOLD_SUPER_FAST: 
            return 'super_fast'
        if lap_val <= LapAnalyzer.THRESHOLD_FAST: 
            return 'fast'
        if lap_val <= LapAnalyzer.THRESHOLD_NORMAL_FAST: 
            return 'normal_fast'
        if lap_val <= LapAnalyzer.THRESHOLD_NORMAL_SLOW: 
            return 'normal_slow'
        if lap_val <= LapAnalyzer.THRESHOLD_SLOW: 
            return 'slow'
        return 'super_slow'
    
    @staticmethod
    def analyze_race_laps(lap_str: str) -> pd.Series:
        """
        文字列のラップタイム (例: "12.8 - 11.3 - 11.3...") を解析する。
        """
        cols = [
            'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
            'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
            'pace_volatility', 'pace_trend'
        ]
        null_res = pd.Series([np.nan] * len(cols), index=cols)
        
        if pd.isna(lap_str) or not isinstance(lap_str, str):
            return null_res
            
        try:
            laps = [float(x.strip()) for x in lap_str.split('-') if x.strip()]
            if not laps: 
                return null_res
            
            # --- 1. カウント特徴量 (Microscopic) ---
            counts = {
                'super_fast': 0, 'fast': 0, 'normal_fast': 0,
                'normal_slow': 0, 'slow': 0, 'super_slow': 0
            }
            for lap in laps:
                cat = LapAnalyzer.classify_lap(lap)
                if cat in counts: 
                    counts[cat] += 1
            
            # --- 2. 変動指標 (Macroscopic) ---
            volatility = np.std(laps) if len(laps) > 1 else 0.0
            
            # トレンド (回帰直線の傾き)
            trend = 0.0
            if len(laps) > 1:
                x = np.arange(len(laps))
                slope, _ = np.polyfit(x, laps, 1)
                trend = slope

            return pd.Series([
                counts['super_fast'], counts['fast'], counts['normal_fast'],
                counts['normal_slow'], counts['slow'], counts['super_slow'],
                volatility, trend
            ], index=cols)

        except Exception:
            return null_res

    def apply_lap_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        データフレーム全体のラップタイム特徴量を一括計算してマージする。
        予測時・学習時ともに同じ方法で処理される。
        """
        if df.empty:
            return df.copy()
            
        df_copy = df.copy()
        
        # 必要なカラムの存在チェック
        if 'lap_times' not in df_copy.columns or 'race_id' not in df_copy.columns:
            cols = [
                'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
                'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
                'pace_volatility', 'pace_trend'
            ]
            for c in cols:
                df_copy[c] = np.nan
            return df_copy
            
        # 計算効率化のために unique な (race_id, lap_times) に対して計算し、マージする
        unique_laps = df_copy[['race_id', 'lap_times']].drop_duplicates().dropna()
        if not unique_laps.empty:
            lap_feats = unique_laps['lap_times'].apply(self.analyze_race_laps)
            lap_feats['race_id'] = unique_laps['race_id']
            # 元のDFに結合
            df_copy = pd.merge(df_copy, lap_feats, on='race_id', how='left')
        else:
            cols = [
                'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
                'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
                'pace_volatility', 'pace_trend'
            ]
            for c in cols: 
                df_copy[c] = np.nan
                
        return df_copy
