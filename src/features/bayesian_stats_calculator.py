import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any

class BayesianStatsCalculator:
    """
    騎手、調教師、馬主、脚質、枠番などの各種切り口における
    ベイジアン平均勝率を計算、適用、保存する数理統計エンジン。
    """
    def __init__(self, c_jockey: int = 20, c_trainer: int = 20, c_owner: int = 50, c_bias: int = 50):
        self.c_jockey = c_jockey
        self.c_trainer = c_trainer
        self.c_owner = c_owner
        self.c_bias = c_bias

    @staticmethod
    def calculate_bayesian_rate(sub_df: pd.DataFrame, group_cols: List[str], target_col_name: str, C_val: int = 20, prior_rate_fallback: float = None) -> pd.DataFrame:
        """
        ベイジアン平均勝率の基本計算ロジック。
        """
        if sub_df.empty or '着順' not in sub_df.columns or not all(c in sub_df.columns for c in group_cols): 
            return pd.DataFrame(columns=group_cols + [target_col_name])
            
        prior_rate = (sub_df['着順'] == 1).mean() if prior_rate_fallback is None else prior_rate_fallback
        
        stats = sub_df.groupby(group_cols, observed=False).agg(
            wins=('着順', lambda x: (x == 1).sum()), 
            races=('着順', 'size')
        ).reset_index()
        
        stats[target_col_name] = (stats['wins'] + C_val * prior_rate) / (stats['races'] + C_val)
        return stats[group_cols + [target_col_name]]

    @staticmethod
    def create_track_bias_map(df: pd.DataFrame, C_val: int = 50) -> Dict[Tuple[str, str, float, str], float]:
        """
        開催場所、サーフェス、距離、実績脚質ごとのベイジアン勝率マップを作成する。
        """
        if df.empty or not all(col in df.columns for col in ['場名', '芝・ダート', '距離', '脚質', '着順']):
            return {}

        df_calc = df[['場名', '芝・ダート', '距離', '脚質', '着順']].copy()
        df_calc['距離'] = pd.to_numeric(df_calc['距離'], errors='coerce')
        df_calc = df_calc.dropna()
        df_calc = df_calc[df_calc['脚質'] != 'unknown']

        if df_calc.empty:
            return {}

        global_win_rate = (df_calc['着順'] == 1).mean()

        group_cols = ['場名', '芝・ダート', '距離', '脚質']
        stats = df_calc.groupby(group_cols, observed=False).agg(
            wins=('着順', lambda x: (x == 1).sum()),
            count=('着順', 'size')
        ).reset_index()

        stats['score'] = (stats['wins'] + C_val * global_win_rate) / (stats['count'] + C_val)

        track_bias_map = {}
        for _, row in stats.iterrows():
            key = (row['場名'], row['芝・ダート'], float(row['距離']), row['脚質'])
            track_bias_map[key] = row['score']

        return track_bias_map

    def fit(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        学習データから各種ベイジアン勝率等の集計マップを構築し、辞書型で返す。
        """
        calculated_stats = {}
        if df.empty:
            return calculated_stats

        df_temp = df.copy()

        # 1. Track Bias Map の作成
        if all(c in df_temp.columns for c in ['場名', '芝・ダート', '距離', '脚質', '着順']):
            calculated_stats['track_bias_map'] = self.create_track_bias_map(df_temp, self.c_bias)
        else:
            calculated_stats['track_bias_map'] = {}

        # ID列の標準化
        for key in ['jockey_id', 'trainer_id', 'owner_id']:
            if key in df_temp.columns:
                s = df_temp[key].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                s = s.apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
                df_temp[key] = s.replace('', np.nan)

        # 2. 騎手関連勝率
        if 'jockey_id' in df_temp.columns and '着順' in df_temp.columns:
            # 騎手勝率
            jockey_rate = self.calculate_bayesian_rate(df_temp, ['jockey_id'], '騎手勝率', C_val=self.c_jockey)
            calculated_stats['jockey_rate'] = jockey_rate

            # 騎手競馬場勝率
            if '場名' in df_temp.columns:
                jockey_venue_rate = self.calculate_bayesian_rate(df_temp, ['jockey_id', '場名'], '騎手競馬場勝率', C_val=self.c_jockey)
                calculated_stats['jockey_venue_rate'] = jockey_venue_rate

            # 騎手トラック勝率 (芝・ダート別)
            if '芝・ダート' in df_temp.columns:
                jockey_track_suitability = self.calculate_bayesian_rate(df_temp, ['jockey_id', '芝・ダート'], '騎手トラック適性', C_val=10)
                calculated_stats['jockey_track_suitability'] = jockey_track_suitability

        # 3. 調教師関連勝率
        if 'trainer_id' in df_temp.columns and '着順' in df_temp.columns:
            trainer_rate = self.calculate_bayesian_rate(df_temp, ['trainer_id'], '調教師勝率', C_val=self.c_trainer)
            calculated_stats['trainer_rate'] = trainer_rate

            if '場名' in df_temp.columns:
                trainer_venue_rate = self.calculate_bayesian_rate(df_temp, ['trainer_id', '場名'], '調教師競馬場勝率', C_val=self.c_trainer)
                calculated_stats['trainer_venue_rate'] = trainer_venue_rate

        # 4. 馬主関連勝率
        if 'owner_id' in df_temp.columns and '着順' in df_temp.columns:
            owner_rate = self.calculate_bayesian_rate(df_temp, ['owner_id'], '馬主勝率', C_val=self.c_owner)
            calculated_stats['owner_rate'] = owner_rate

        # 5. トラック脚質適性 (実績脚質ベース)
        if '脚質' in df_temp.columns and '芝・ダート' in df_temp.columns and '着順' in df_temp.columns:
            track_running_style = self.calculate_bayesian_rate(df_temp, ['芝・ダート', '脚質'], '芝ダート脚質適性', C_val=self.c_bias)
            calculated_stats['track_running_style_suitability'] = track_running_style

        # 6. 体重増減適性
        if '体重増減カテゴリ' in df_temp.columns and '着順' in df_temp.columns:
            weight_change_suitability = self.calculate_bayesian_rate(df_temp, ['体重増減カテゴリ'], '体重変化適性', C_val=self.c_bias)
            calculated_stats['weight_change_suitability'] = weight_change_suitability

        # 8. 馬体重統計
        if '馬' in df_temp.columns and '体重' in df_temp.columns:
            df_temp['体重'] = pd.to_numeric(df_temp['体重'], errors='coerce')
            horse_weight_stats = df_temp.groupby('馬')['体重'].agg(['mean', 'std']).reset_index()
            horse_weight_stats.columns = ['馬', '馬体重_平均', '馬体重_標準偏差']
            calculated_stats['horse_weight_stats'] = horse_weight_stats

        return calculated_stats

    def transform(self, df: pd.DataFrame, stats: Dict[str, Any]) -> pd.DataFrame:
        """
        算出済みのベイジアン勝率データをデータフレームにマージ（適用）する。
        予測時（推論時）と学習時（適用段階）で共通のロジック。
        """
        if df.empty or not stats:
            return df.copy()

        df_copy = df.copy()

        # ID列の標準化
        for key in ['jockey_id', 'trainer_id', 'owner_id']:
            if key in df_copy.columns:
                s = df_copy[key].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                s = s.apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
                df_copy[key] = s.replace('', np.nan)

        # 1. 騎手勝率のマージ
        if 'jockey_rate' in stats and 'jockey_id' in df_copy.columns:
            rate_df = stats['jockey_rate'].copy()
            rate_df['jockey_id'] = rate_df['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['jockey_id'] = df_copy['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on='jockey_id', how='left')
            df_copy['騎手勝率'] = df_copy['騎手勝率'].fillna(0.075)
        else:
            df_copy['騎手勝率'] = 0.075

        # 騎手競馬場勝率のマージ
        if 'jockey_venue_rate' in stats and 'jockey_id' in df_copy.columns and '場名' in df_copy.columns:
            rate_df = stats['jockey_venue_rate'].copy()
            rate_df['jockey_id'] = rate_df['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['jockey_id'] = df_copy['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on=['jockey_id', '場名'], how='left')
            df_copy['騎手競馬場勝率'] = df_copy['騎手競馬場勝率'].fillna(0.075)
        else:
            df_copy['騎手競馬場勝率'] = 0.075

        # 騎手トラック適性のマージ
        if 'jockey_track_suitability' in stats and 'jockey_id' in df_copy.columns and '芝・ダート' in df_copy.columns:
            rate_df = stats['jockey_track_suitability'].copy()
            rate_df['jockey_id'] = rate_df['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['jockey_id'] = df_copy['jockey_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on=['jockey_id', '芝・ダート'], how='left')
            df_copy['騎手トラック適性'] = df_copy['騎手トラック適性'].fillna(0.075)
        else:
            df_copy['騎手トラック適性'] = 0.075

        # 2. 調教師勝率のマージ
        if 'trainer_rate' in stats and 'trainer_id' in df_copy.columns:
            rate_df = stats['trainer_rate'].copy()
            rate_df['trainer_id'] = rate_df['trainer_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['trainer_id'] = df_copy['trainer_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on='trainer_id', how='left')
            df_copy['調教師勝率'] = df_copy['調教師勝率'].fillna(0.075)
        else:
            df_copy['調教師勝率'] = 0.075

        # 調教師競馬場勝率のマージ
        if 'trainer_venue_rate' in stats and 'trainer_id' in df_copy.columns and '場名' in df_copy.columns:
            rate_df = stats['trainer_venue_rate'].copy()
            rate_df['trainer_id'] = rate_df['trainer_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['trainer_id'] = df_copy['trainer_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on=['trainer_id', '場名'], how='left')
            df_copy['調教師競馬場勝率'] = df_copy['調教師競馬場勝率'].fillna(0.075)
        else:
            df_copy['調教師競馬場勝率'] = 0.075

        # 3. 馬主勝率のマージ
        if 'owner_rate' in stats and 'owner_id' in df_copy.columns:
            rate_df = stats['owner_rate'].copy()
            rate_df['owner_id'] = rate_df['owner_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy['owner_id'] = df_copy['owner_id'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True).apply(lambda x: x.zfill(5) if x.isdigit() and len(x) < 5 else x)
            df_copy = pd.merge(df_copy, rate_df, on='owner_id', how='left')
            df_copy['馬主勝率'] = df_copy['馬主勝率'].fillna(0.075)
        else:
            df_copy['馬主勝率'] = 0.075

        # 4. トラック脚質適性のマージ
        if 'track_running_style_suitability' in stats and '芝・ダート' in df_copy.columns and '脚質' in df_copy.columns:
            df_copy = pd.merge(df_copy, stats['track_running_style_suitability'], on=['芝・ダート', '脚質'], how='left')
            df_copy['芝ダート脚質適性'] = df_copy['芝ダート脚質適性'].fillna(0.075)
        else:
            df_copy['芝ダート脚質適性'] = 0.075

        # 5. 体重増減適性のマージ
        if 'weight_change_suitability' in stats and '体重増減カテゴリ' in df_copy.columns:
            df_copy = pd.merge(df_copy, stats['weight_change_suitability'], on='体重増減カテゴリ', how='left')
            df_copy['体重変化適性'] = df_copy['体重変化適性'].fillna(0.075)
        else:
            df_copy['体重変化適性'] = 0.075

        # 6. 馬体重統計のマージ
        if 'horse_weight_stats' in stats and '馬' in df_copy.columns:
            df_copy = pd.merge(df_copy, stats['horse_weight_stats'], on='馬', how='left')
        else:
            df_copy['馬体重_平均'] = np.nan
            df_copy['馬体重_標準偏差'] = np.nan

        # 8. トラック脚質適性 (想定脚質ベースの開催バイアスマップの適用)
        # JRA馬が遠征先で走る時などに機能
        track_bias_map = stats.get('track_bias_map', {})
        if track_bias_map and '想定脚質' in df_copy.columns:
            def get_track_suitability(row):
                key = (row.get('場名'), row.get('芝・ダート'), pd.to_numeric(row.get('距離'), errors='coerce'), row.get('想定脚質'))
                if key in track_bias_map:
                    return track_bias_map[key]
                return 0.075 # 平均勝率でのフォールバック

            df_copy['トラック脚質適性'] = df_copy.apply(get_track_suitability, axis=1)
        else:
            df_copy['トラック脚質適性'] = 0.075

        return df_copy
