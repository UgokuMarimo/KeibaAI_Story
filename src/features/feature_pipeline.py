import pandas as pd
import numpy as np
import re
from typing import List, Dict, Tuple, Any
from sklearn.preprocessing import LabelEncoder
import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

import config

from features.course_analyzer import CourseAnalyzer
from features.lap_analyzer import LapAnalyzer
from features.running_style_estimator import RunningStyleEstimator
from features.bayesian_stats_calculator import BayesianStatsCalculator

# --- ヘルパー関数群 ---
def safe_float_convert(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce')

def class_mapping(row: pd.Series) -> int:
    """
    レースの格付けを数値に変換する。
    """
    race_name = str(row.get('レース名', ''))
    class_info = str(row.get('クラス', ''))
    track_type = str(row.get('芝・ダート', ''))

    if '障' in track_type:
        return -99

    combined_info = race_name + " " + class_info

    if re.search(r'[（\(](?:G|Jpn|g|jpn)(?:I|Ⅰ|1)[）\)]', combined_info): return 8
    if re.search(r'[（\(](?:G|Jpn|g|jpn)(?:II|Ⅱ|2)[）\)]', combined_info): return 7
    if re.search(r'[（\(](?:G|Jpn|g|jpn)(?:III|Ⅲ|3)[）\)]', combined_info): return 6
    if re.search(r'[（\(]重賞[）\)]', combined_info): return 6

    if 'オープン' in combined_info or '(OP)' in combined_info or re.search(r'[（\(]L[）\)]', combined_info):
        return 5

    score = 5
    if re.search(r'3勝|３勝|1600万', combined_info): score = 4
    elif re.search(r'2勝|２勝|1000万|900万', combined_info): score = 3
    elif re.search(r'1勝|１勝|500万', combined_info): score = 2
    elif '新馬' in combined_info or '未出走' in combined_info: score = 0
    elif '未勝利' in combined_info: score = 1

    is_jra = row.get('is_jra')
    if is_jra is not None:
        try:
            is_jra_val = float(is_jra)
            if is_jra_val == 0:
                score = min(score, 3)
        except (ValueError, TypeError):
            pass

    return score

def process_passing_order(series: pd.Series) -> pd.DataFrame:
    def parse_single_order(order_str):
        if pd.isna(order_str) or not isinstance(order_str, str): 
            return [np.nan, np.nan]
        try:
            positions = [int(p) for p in order_str.split('-') if p.strip()]
            if not positions: 
                return [np.nan, np.nan]
            return [np.mean(positions), positions[-1] - positions[0]]
        except (ValueError, IndexError): 
            return [np.nan, np.nan]
            
    parsed_data = series.apply(parse_single_order)
    return pd.DataFrame(parsed_data.tolist(), index=series.index, columns=['通過順_平均', '通過順_変動'])


class FeatureEngineerPipeline:
    """
    データ前処理、特徴量生成、統計量マージ、エンコーディングまでを
    一括制御するメイン特徴量エンジニアリングパイプラインクラス。
    """
    def __init__(self):
        self.course_analyzer = CourseAnalyzer()
        self.lap_analyzer = LapAnalyzer()
        self.running_style_estimator = RunningStyleEstimator(num_past_races=config.NUM_PAST_RACES)
        self.bayesian_stats_calculator = BayesianStatsCalculator()

    def preprocess_and_clean(self, df: pd.DataFrame, time_scaler: dict = None) -> Tuple[pd.DataFrame, dict]:
        """
        データの前処理とクレンジングを行う。
        """
        if df.empty: 
            return pd.DataFrame(), time_scaler
            
        df_copy = df.copy()

        # 性齢の分割
        if '性齢' in df_copy.columns:
            df_copy['性'] = df_copy['性齢'].str[0]
            df_copy['齢'] = pd.to_numeric(df_copy['性齢'].str[1:], errors='coerce')
            df_copy.drop('性齢', axis=1, inplace=True, errors='ignore')

        # 日付処理
        if '日付' in df_copy.columns:
            if not pd.api.types.is_datetime64_any_dtype(df_copy['日付']):
                df_copy['日付'] = pd.to_datetime(df_copy['日付'], format='%Y年%m月%d日', errors='coerce')
            if df_copy['日付'].isnull().all():
                print("[ERROR] All date values are null. Aborting.")
                return pd.DataFrame(), time_scaler
        else:
            print("[ERROR] '日付' column not found. Aborting.")
            return pd.DataFrame(), time_scaler

        # 数値型変換
        numeric_cols = ['馬番', '着順', '体重', '体重変化', '齢', '斤量', '上がり', '人気', '距離', 'オッズ', '枠番']
        for col in numeric_cols:
            if col in df_copy.columns:
                df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')

        # is_jra カラムの整備
        if 'is_jra' not in df_copy.columns:
            if 'is_jra_race' in df_copy.columns:
                df_copy['is_jra'] = df_copy['is_jra_race'].astype(float)
            elif '場名' in df_copy.columns:
                df_copy['is_jra'] = df_copy['場名'].apply(lambda x: 1 if x in config.JRA_PLACE_NAMES else 0)
            else:
                df_copy['is_jra'] = 1

        # 走破時間のスケーリング
        if '走破時間' in df_copy.columns:
            df_copy['走破時間_seconds'] = np.nan
            mask_valid_time_str = df_copy['走破時間'].notna() & df_copy['走破時間'].astype(str).str.contains(':')
            
            if mask_valid_time_str.any():
                df_with_time_str = df_copy.loc[mask_valid_time_str, '走破時間'].astype(str)
                time_parts = df_with_time_str.str.split(':', expand=True)
                minutes = pd.to_numeric(time_parts[0], errors='coerce')
                seconds_part = pd.to_numeric(time_parts[1], errors='coerce')
                total_seconds = minutes * 60 + seconds_part
                df_copy.loc[mask_valid_time_str, '走破時間_seconds'] = total_seconds

            valid_times_for_scaling = df_copy['走破時間_seconds'].dropna()
            
            if not valid_times_for_scaling.empty:
                inverted_times = -valid_times_for_scaling
                
                if time_scaler is None:
                    mean_val = inverted_times.mean()
                    std_val = inverted_times.std()
                    if std_val == 0:
                        std_val = 1.0
                    time_scaler = {
                        'running_time_scaled_mean': mean_val,
                        'running_time_scaled_std': std_val,
                        'running_time_scaled_clip_lower': -3.0,
                        'running_time_scaled_clip_upper': 3.0
                    }
                
                if time_scaler and time_scaler['running_time_scaled_std'] != 0:
                    scaled_inverted_times = (inverted_times - time_scaler['running_time_scaled_mean']) / time_scaler['running_time_scaled_std']
                else: 
                    scaled_inverted_times = inverted_times * 0
                
                clipped_scaled_times = scaled_inverted_times.clip(
                    lower=time_scaler['running_time_scaled_clip_lower'],
                    upper=time_scaler['running_time_scaled_clip_upper']
                )
                df_copy.loc[clipped_scaled_times.index, '走破時間_scaled'] = clipped_scaled_times
            
            df_copy.drop('走破時間', axis=1, inplace=True, errors='ignore')

        # ① コース物理特徴量のマージ (CourseAnalyzerに委譲)
        df_copy = self.course_analyzer.apply_course_features(df_copy)

        # カテゴリ変数の数値マッピング
        CATEGORY_MAPPINGS = {
            '性': {'牡': 0, '牝': 1, 'セ': 2}, 
            '芝・ダート': {'芝': 0, 'ダ': 1, '障': 2}, 
            '回り': {'右': 0, '左': 1, '芝': 2, '直': 2}
        }
        for col, mapping in CATEGORY_MAPPINGS.items():
            if col in df_copy.columns: 
                df_copy[col] = df_copy[col].astype(str).str.strip().map(mapping)
                
        if '天気' in df_copy.columns:
            tenki_map = {'晴': 0, '曇': 1, '小': 2, '雨': 3, '雪': 4}
            df_copy['天気'] = df_copy['天気'].str.strip().str[0].map(tenki_map)
            
        if '馬場' in df_copy.columns:
            baba_map = {'良': 0, '稍': 1, '重': 2, '不': 3}
            df_copy['馬場'] = df_copy['馬場'].str.strip().str[0].map(baba_map)

        # 通過順・格付けの処理
        if '通過順' in df_copy.columns: 
            df_copy = pd.concat([df_copy, process_passing_order(df_copy['通過順'].astype(str))], axis=1)
            
        if 'レース名' in df_copy.columns:
            df_copy['クラス'] = df_copy.apply(class_mapping, axis=1)

        df_copy['year'] = df_copy['日付'].dt.year
        
        # 出走頭数・頭数の整備
        if '出走頭数' not in df_copy.columns:
             if '頭数' in df_copy.columns:
                 df_copy['出走頭数'] = df_copy['頭数']
             else:
                 df_copy['出走頭数'] = np.nan
        df_copy['出走頭数'] = pd.to_numeric(df_copy['出走頭数'], errors='coerce')
        calculated_counts = df_copy.groupby('race_id')['馬'].transform('count')
        df_copy['出走頭数'] = df_copy['出走頭数'].fillna(calculated_counts)
        
        if '頭数' in df_copy.columns:
            df_copy.drop('頭数', axis=1, inplace=True, errors='ignore')

        df_copy['is_niigata_1000m'] = ((df_copy['場名'] == '新潟') & (df_copy['距離'] == 1000) & (df_copy['芝・ダート'] == 0)).astype(int)

        # ポジションスコアの計算 (RunningStyleEstimatorに委譲)
        if '通過順' in df_copy.columns and '出走頭数' in df_copy.columns:
            df_copy['ポジションスコア'] = df_copy.apply(self.running_style_estimator.calculate_position_score, axis=1)
        else:
            df_copy['ポジションスコア'] = np.nan
            
        # ③ 実績脚質判定の適用 (JRA-VAN準拠ロジック、RunningStyleEstimatorに委譲)
        if '通過順' in df_copy.columns and '出走頭数' in df_copy.columns:
            df_copy['脚質'] = df_copy.apply(
                lambda r: self.running_style_estimator.classify_actual_running_style(r['通過順'], r['出走頭数']), 
                axis=1
            )
        else:
            df_copy['脚質'] = 'unknown' 
            
        # 動的ゲートグループ決定 (RunningStyleEstimatorに委譲)
        df_copy['馬番グループ'] = self.running_style_estimator.assign_gate_groups(df_copy)

        # 体重増減カテゴリ
        if '体重変化' in df_copy.columns:
            def categorize_weight_diff(val):
                 try:
                     v = float(val)
                     if pd.isna(v): return 9
                     if v > 0: return 2
                     elif v < 0: return 0
                     else: return 1
                 except: return 9
            df_copy['体重増減カテゴリ'] = df_copy['体重変化'].apply(categorize_weight_diff)
        else:
            df_copy['体重増減カテゴリ'] = 9 

        # ② ラップタイム解析 (LapAnalyzerに委譲)
        df_copy = self.lap_analyzer.apply_lap_features(df_copy)
        
        return df_copy, time_scaler

    def add_past_race_features(self, df: pd.DataFrame, num_past_races: int, past_race_features: List[str]) -> pd.DataFrame:
        """
        指定された過去走特徴量を、馬と日付に基づいてシフトして追加する。
        """
        if df.empty: 
            return pd.DataFrame(columns=df.columns)
        if '馬' not in df.columns or '日付' not in df.columns: 
            return df 
            
        df_copy = df.copy() 
        group_key = '馬'
        if 'horse_id' in df_copy.columns and df_copy['horse_id'].notna().any():
            group_key = 'horse_id'
            df_copy['horse_id'] = df_copy['horse_id'].astype(str)
        
        # 直近のレースが最初に来るように日付で降順ソート
        df_copy.sort_values(by=[group_key, '日付'], ascending=[True, False], inplace=True) 
        
        new_features = {}
        
        for i in range(1, num_past_races + 1):
            new_features[f'日付{i}'] = df_copy.groupby(group_key)['日付'].shift(-i)
            
            for feature in past_race_features:
                if feature == '通過順': 
                    if f'{feature}_平均' in df_copy.columns: 
                        new_features[f'{feature}_平均{i}'] = df_copy.groupby(group_key)[f'{feature}_平均'].shift(-i)
                    if f'{feature}_変動' in df_copy.columns: 
                        new_features[f'{feature}_変動{i}'] = df_copy.groupby(group_key)[f'{feature}_変動'].shift(-i)
                elif feature in df_copy.columns: 
                    new_features[f'{feature}{i}'] = df_copy.groupby(group_key)[feature].shift(-i)
                else: 
                    new_features[f'{feature}{i}'] = np.nan
            
            if 'ポジションスコア' in df_copy.columns:
                new_features[f'ポジションスコア{i}'] = df_copy.groupby(group_key)['ポジションスコア'].shift(-i)
                    
        if new_features:
            new_features_df = pd.DataFrame(new_features, index=df_copy.index)
            df_copy = pd.concat([df_copy, new_features_df], axis=1)
            
            # 過去走の体重増減カテゴリの NaN 補完 (キャリア不足用)
            for i in range(1, num_past_races + 1):
                col = f'体重増減カテゴリ{i}'
                if col in df_copy.columns:
                    df_copy[col] = df_copy[col].fillna(9)
            
        return df_copy

    def engineer_advanced_features(self, df: pd.DataFrame, num_past_races: int, stats: Dict[str, pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        高度な特徴量生成を行う。
        """
        if df.empty: 
            return pd.DataFrame(columns=df.columns), {}
            
        df_copy = df.copy() 
        df_copy.replace('---', np.nan, inplace=True)
        
        # 日付差・長期休養明けフラグ
        if '日付' in df_copy.columns and '日付1' in df_copy.columns: 
            df_copy['日付差1'] = (df_copy['日付'] - df_copy['日付1']).dt.days
        else: 
            df_copy['日付差1'] = np.nan
        df_copy['長期休養明けフラグ'] = (df_copy['日付差1'] > 180).astype(int)

        # 距離差
        if '距離' in df_copy.columns: df_copy['距離'] = safe_float_convert(df_copy['距離'])
        if '距離1' in df_copy.columns: df_copy['距離1'] = safe_float_convert(df_copy['距離1'])
        if '距離' in df_copy.columns and '距離1' in df_copy.columns: df_copy['距離差1'] = df_copy['距離'] - df_copy['距離1']
            
        for i in range(2, num_past_races + 1):
            if f'日付{i-1}' in df_copy.columns and f'日付{i}' in df_copy.columns: 
                df_copy[f'日付差{i}'] = (df_copy[f'日付{i-1}'] - df_copy[f'日付{i}']).dt.days
            else: 
                df_copy[f'日付差{i}'] = np.nan

        # 過去走統計量
        target_features = ['着順', '上がり', '通過順_平均', '通過順_変動', '賞金']
        for feature in target_features:
            past_cols = [f'{feature}{i}' for i in range(1, num_past_races + 1) if f'{feature}{i}' in df_copy.columns]
            if past_cols:
                df_copy[past_cols] = df_copy[past_cols].apply(pd.to_numeric, errors='coerce')
                df_copy[f'過去{num_past_races}走_{feature}_平均'] = df_copy[past_cols].mean(axis=1)
                df_copy[f'過去{num_past_races}走_{feature}_最大'] = df_copy[past_cols].max(axis=1)
                df_copy[f'過去{num_past_races}走_{feature}_最小'] = df_copy[past_cols].min(axis=1)
                df_copy[f'過去{num_past_races}走_{feature}_標準偏差'] = df_copy[past_cols].std(axis=1)
                
                # EMA算出
                past_cols_rev = past_cols[::-1]
                df_copy[f'過去{num_past_races}走_{feature}_EMA'] = df_copy[past_cols_rev].ewm(span=3, axis=1, ignore_na=True).mean().iloc[:, -1]

        # クラス変動
        if 'クラス' in df_copy.columns and 'クラス1' in df_copy.columns:
            current_class_score = pd.to_numeric(df_copy['クラス'], errors='coerce')
            prev_class_score = pd.to_numeric(df_copy['クラス1'], errors='coerce')
            class_diff = current_class_score - prev_class_score
            df_copy['クラス変動'] = class_diff.clip(lower=-3, upper=3).fillna(0)
        else:
            df_copy['クラス変動'] = 0

        # 距離考慮走破時間スケーリング統計量
        if '距離' in df_copy.columns and f'走破時間_scaled{num_past_races}' in df_copy.columns: 
            for i in range(1, num_past_races + 1):
                if f'距離{i}' in df_copy.columns:
                    df_copy[f'距離差_現在_過去{i}'] = (df_copy['距離'] - df_copy[f'距離{i}']).abs()
                else:
                    df_copy[f'距離差_現在_過去{i}'] = np.nan

            def get_conditional_scaled_times_for_stats(row, num_past_races_val):
                current_distance = row['距離']
                same_distance_times = []
                for i in range(1, num_past_races_val + 1):
                    if pd.notna(row[f'距離{i}']) and row[f'距離{i}'] == current_distance and pd.notna(row[f'走破時間_scaled{i}']):
                        same_distance_times.append(row[f'走破時間_scaled{i}'])
                
                if same_distance_times:
                    return same_distance_times

                min_dist_diff = np.inf
                closest_time_found = np.nan
                closest_race_idx_found = -1

                for i in range(1, num_past_races_val + 1):
                    if pd.notna(row[f'距離差_現在_過去{i}']) and pd.notna(row[f'走破時間_scaled{i}']):
                        dist_diff = row[f'距離差_現在_過去{i}']
                        
                        if dist_diff < min_dist_diff:
                            min_dist_diff = dist_diff
                            closest_time_found = row[f'走破時間_scaled{i}']
                            closest_race_idx_found = i 
                        elif dist_diff == min_dist_diff:
                            if i < closest_race_idx_found:
                                 closest_time_found = row[f'走破時間_scaled{i}']
                                 closest_race_idx_found = i
                
                if pd.notna(closest_time_found):
                    return [closest_time_found]
                return []

            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'] = df_copy.apply(
                lambda row: get_conditional_scaled_times_for_stats(row, num_past_races), axis=1
            )

            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_平均'] = df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'].apply(lambda x: pd.Series(x).mean())
            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_最大'] = df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'].apply(lambda x: pd.Series(x).max())
            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_最小'] = df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'].apply(lambda x: pd.Series(x).min())
            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_標準偏差'] = df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'].apply(lambda x: pd.Series(x).std())
            df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_EMA'] = df_copy[f'過去{num_past_races}走_条件_走破時間_scaled_times'].apply(lambda x: pd.Series(x[::-1]).ewm(span=3).mean().iloc[-1] if len(x) > 0 else np.nan)
            
            df_copy.drop(columns=[f'距離差_現在_過去{i}' for i in range(1, num_past_races + 1) if f'距離差_現在_過去{i}' in df_copy.columns], errors='ignore', inplace=True)
            # times は build_features 側での除去を考慮して残す
            # df_copy.drop(columns=[f'過去{num_past_races}走_条件_走破時間_scaled_times'], errors='ignore', inplace=True)

        # ③ 想定脚質推定と新特徴量「過去走数」の適用 (RunningStyleEstimatorに委譲)
        df_copy = self.running_style_estimator.estimate_running_style(df_copy)

        calculated_stats = {}
        if stats is None: # 学習時 (統計量の新規計算と適用)
            # ④ ベイジアン勝率計算 (BayesianStatsCalculatorに委譲)
            calculated_stats = self.bayesian_stats_calculator.fit(df_copy)
            df_copy = self.bayesian_stats_calculator.transform(df_copy, calculated_stats)
        else: # 予測時 (既存の統計量を適用)
            df_copy = self.bayesian_stats_calculator.transform(df_copy, stats)

        return df_copy, calculated_stats

    def add_race_level_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        レース内の相対的な特徴量（平均、最大、最小、偏差など）を追加する。
        """
        if df.empty: 
            return pd.DataFrame(columns=df.columns)
        if 'race_id' not in df.columns or '馬' not in df.columns: 
            return df
            
        df_copy = df.copy() 
        if '出走頭数' not in df_copy.columns: 
            df_copy['出走頭数'] = df_copy.groupby('race_id')['馬'].transform('count')
        
        # ペース・展開特徴量
        if '想定脚質' in df_copy.columns:
            style_counts = df_copy.groupby('race_id')['想定脚質'].value_counts().unstack(fill_value=0)
            style_cols_map = {
                '逃げ': 'レース_逃げ馬数',
                '先行': 'レース_先行馬数',
                '差し': 'レース_差し馬数',
                '追込': 'レース_追込馬数',
                'unknown': 'レース_脚質不明数'
            }
            style_counts = style_counts.rename(columns=style_cols_map)
            
            for col_name in style_cols_map.values():
                if col_name not in style_counts.columns:
                    style_counts[col_name] = 0
                    
            total_horses = df_copy.groupby('race_id').size()
            pace_numerator = (style_counts['レース_逃げ馬数'] + style_counts['レース_先行馬数'])
            style_counts['レース_前傾ペース指数'] = pace_numerator.div(total_horses).replace([np.inf, -np.inf], 0).fillna(0)
            
            df_copy = pd.merge(df_copy, style_counts, on='race_id', how='left')
        else:
            style_cols = ['レース_逃げ馬数', 'レース_先行馬数', 'レース_差し馬数', 'レース_追込馬数', 'レース_脚質不明数', 'レース_前傾ペース指数']
            for col in style_cols:
                df_copy[col] = 0.0
        
        # 相対特徴量の追加
        relative_features = [
            '斤量', '騎手勝率', '騎手競馬場勝率', 
            f'過去{config.NUM_PAST_RACES}走_着順_平均', f'過去{config.NUM_PAST_RACES}走_上がり_平均', 
            f'過去{config.NUM_PAST_RACES}走_条件_走破時間_scaled_平均', 
            f'過去{config.NUM_PAST_RACES}走_条件_走破時間_scaled_最大', 
            f'過去{config.NUM_PAST_RACES}走_条件_走破時間_scaled_最小',
            # 新特徴量「過去走数」も相対化（そのレースにおけるキャリアの豊富さの相対比較）
            '過去走数'
        ] 
        
        for feature in relative_features:
            if feature in df_copy.columns:
                df_copy[feature] = pd.to_numeric(df_copy[feature], errors='coerce')
                race_stats = df_copy.groupby('race_id')[feature].agg(['mean', 'max', 'min']).rename(
                    columns={'mean': f'{feature}_race_mean', 'max': f'{feature}_race_max', 'min': f'{feature}_race_min'}
                )
                df_copy = pd.merge(df_copy, race_stats, on='race_id', how='left')
                df_copy[f'{feature}_race_dev'] = df_copy[f'{feature}_race_mean'] - df_copy[feature]
                df_copy[f'{feature}_race_max_diff'] = df_copy[f'{feature}_race_max'] - df_copy[feature]
                df_copy[f'{feature}_race_min_diff'] = df_copy[feature] - df_copy[f'{feature}_race_min']
            else:
                for suffix in ['_race_mean', '_race_max', '_race_min', '_dev', '_max_diff', '_min_diff']: 
                    df_copy[f'{feature}{suffix}'] = np.nan
                    
        return df_copy

    def encode_and_finalize(self, df: pd.DataFrame, categorical_features: List[str], label_encoders: Dict[str, LabelEncoder] = None) -> Tuple[pd.DataFrame, Dict[str, LabelEncoder]]:
        """
        Label Encodingを行い、最終的な特徴量データセットを構築する。
        """
        if df.empty: 
            return pd.DataFrame(columns=categorical_features), {} if label_encoders is None else label_encoders
            
        df_copy = df.copy() 
        if label_encoders is None:
            label_encoders = {}
            for col in categorical_features:
                if col in df_copy.columns:
                    df_copy[col] = df_copy[col].astype(str).fillna('unknown')
                    le = LabelEncoder()
                    classes = np.append(df_copy[col].unique(), 'unknown')
                    le.fit(np.unique(classes)) 
                    df_copy[col] = le.transform(df_copy[col])
                    label_encoders[col] = le
                else:
                    df_copy[col] = np.nan
        else: 
            for col in categorical_features:
                if col in df_copy.columns:
                    le = label_encoders.get(col)
                    if le is None: 
                        continue
                    known_labels = set(le.classes_)
                    df_copy[col] = df_copy[col].astype(str).fillna('unknown').apply(lambda x: x if x in known_labels else 'unknown')
                    df_copy[col] = le.transform(df_copy[col])
                else:
                    df_copy[col] = np.nan

        # 不要なカラムの削除
        cols_to_drop = ['頭数', '枠番', 'ペース', '厩舎', '想定脚質']
        df_copy.drop(columns=[c for c in cols_to_drop if c in df_copy.columns], errors='ignore', inplace=True)

        return df_copy, label_encoders
