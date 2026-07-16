import pandas as pd
import numpy as np
import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

try:
    from utils.course_data import get_course_features
except ImportError:
    from src.utils.course_data import get_course_features

class CourseAnalyzer:
    """
    コース物理形態（直線距離、勾配、一周距離、幅員）をマージするクラス。
    """
    def __init__(self):
        pass

    def apply_course_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        データフレームを受け取り、コース特徴量を算出して列を追加した新規データフレームを返す。
        """
        if df.empty:
            return df.copy()
            
        df_copy = df.copy()
        
        # 必要なカラムの存在チェック
        if not all(col in df_copy.columns for col in ['場名', '芝・ダート', '距離']):
            # 必要なカラムが揃っていない場合は、空のカラムを追加して返す
            course_feat_cols = ['コース直線距離', 'コース勾配', 'コース一周距離', 'コース幅員']
            for col in course_feat_cols:
                df_copy[col] = np.nan
            return df_copy

        def apply_single_row(row):
            course_str = row.get('コース', '') or row.get('レース名', '')
            if pd.isna(course_str):
                course_str = None
                
            dist = pd.to_numeric(row['距離'], errors='coerce')
            
            feats = get_course_features(
                row['場名'], 
                row['芝・ダート'], 
                dist, 
                detailed_course_str=course_str
            )
            if feats:
                return pd.Series([feats['straight_dist'], feats['slope'], feats['circumference'], feats['width']])
            else:
                return pd.Series([np.nan, np.nan, np.nan, np.nan])

        course_feat_cols = ['コース直線距離', 'コース勾配', 'コース一周距離', 'コース幅員']
        df_copy[course_feat_cols] = df_copy.apply(apply_single_row, axis=1)
        
        return df_copy
