import pandas as pd
import numpy as np

class RunningStyleEstimator:
    """
    実績脚質判定（JRA-VAN準拠）、想定脚質推定、馬番ゲートグループ決定、
    および過去走データ不足（欠損値）に対する補完対策を行うクラス。
    """
    def __init__(self, num_past_races: int = 5):
        self.num_past_races = num_past_races

    @staticmethod
    def calculate_position_score(row) -> float:
        """
        Position Score = (第1コーナー通過順 - 1) / (出走頭数 - 1)
        0.0 (先頭) 〜 1.0 (最後方) の値に正規化する。
        """
        try:
            passing_order_str = str(row.get('通過順', ''))
            num_horses = float(row.get('出走頭数', 0))
            if pd.isna(passing_order_str) or num_horses <= 1:
                return np.nan
            
            parts = [p.strip() for p in passing_order_str.split('-') if p.strip()]
            if not parts:
                return np.nan
            
            # 第1コーナーの通過順位
            first_corner_pos = float(parts[0])
            
            score = (first_corner_pos - 1) / (num_horses - 1)
            return max(0.0, min(1.0, score))
        except (ValueError, IndexError, TypeError):
            return np.nan

    @staticmethod
    def classify_actual_running_style(passing_order_str: str, num_horses: int) -> str:
        """
        JRA-VANの判定ロジックを再現した実績脚質の分類。
        - 逃げ：最終コーナー以外のいずれかのコーナーを１位で通過
        - 先行：逃げに該当しない馬で、最終コーナーを４位以内で通過
        - 差し：逃げ・先行に該当しない馬で、最終コーナー通過順位が出走頭数の３分の２以内（８頭未満は該当なし）
        - 追込：上記いずれにも該当しない馬
        """
        if pd.isna(passing_order_str) or not isinstance(passing_order_str, str) or num_horses <= 0:
            return 'unknown'
        try:
            positions = [int(p) for p in passing_order_str.split('-') if p.strip()]
            if not positions:
                return 'unknown'
            
            # 1. 逃げの判定 (最終コーナー以外のコーナーで1位通過)
            if len(positions) > 1:
                non_final_corners = positions[:-1]
                final_corner = positions[-1]
                is_nige = any(p == 1 for p in non_final_corners)
            else:
                # コーナー数が1のみ（新潟直線1000mなどや極端な短距離）
                final_corner = positions[0]
                is_nige = (final_corner == 1)
                
            if is_nige:
                return '逃げ'
                
            # 2. 先行の判定 (最終コーナーを4位以内)
            if final_corner <= 4:
                return '先行'
                
            # 3. 差しの判定 (最終コーナーが出走頭数の 2/3 以内、かつ8頭以上)
            if num_horses >= 8 and final_corner <= (num_horses * 2.0 / 3.0):
                return '差し'
                
            # 4. 追込の判定 (いずれにも該当しない)
            return '追込'
        except Exception:
            return 'unknown'

    def assign_gate_groups(self, df: pd.DataFrame) -> pd.Series:
        """
        出走頭数に応じて、馬番を「内(1)」「中(2)」「外(3)」グループに動的に分類する。
        """
        if df.empty or not all(col in df.columns for col in ['race_id', '馬番', '出走頭数']):
            return pd.Series(['不明'] * len(df), index=df.index, name='馬番グループ')
            
        all_gate_groups = pd.Series(index=df.index, dtype=str, name='馬番グループ')
        
        for race_id, group_df in df.groupby('race_id'):
            num_horses = group_df['出走頭数'].iloc[0]
            if pd.isna(num_horses) or num_horses < 3:
                labels = pd.Series(['少頭数'] * len(group_df), index=group_df.index)
            else:
                third = num_horses / 3
                q1 = int(np.ceil(third))
                q2 = int(np.ceil(2 * third))
                conditions = [
                    group_df['馬番'] <= q1,
                    (group_df['馬番'] > q1) & (group_df['馬番'] <= q2),
                    group_df['馬番'] > q2
                ]
                choices = ['内', '中', '外']
                labels = pd.Series(np.select(conditions, choices, default='不明'), index=group_df.index)
            all_gate_groups.loc[group_df.index] = labels
            
        return all_gate_groups.fillna('不明')

    def estimate_running_style(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        過去N走のポジションスコアを基に、今回のレースでの「想定脚質」を決定する。
        また、バグ対策として「過去走数」（0〜5の数値）を新規特徴量として追加する。
        """
        if df.empty:
            return df.copy()
            
        df_copy = df.copy()
        
        # --- 新特徴量: 過去走数の算出 (3歳馬・新馬の過小評価バグ修正) ---
        # 過去走の日付カラムが非空である数を数える
        past_date_cols = [f'日付{i}' for i in range(1, self.num_past_races + 1) if f'日付{i}' in df_copy.columns]
        if past_date_cols:
            df_copy['過去走数'] = df_copy[past_date_cols].notna().sum(axis=1)
        else:
            df_copy['過去走数'] = 0

        # ポジションスコアの過去走シフト列の一覧を取得
        pos_score_cols = [f'ポジションスコア{i}' for i in range(1, self.num_past_races + 1) if f'ポジションスコア{i}' in df_copy.columns]
        
        if pos_score_cols:
            # 過去走のポジションスコア平均を算出 (NaNは無視される)
            df_copy[pos_score_cols] = df_copy[pos_score_cols].apply(pd.to_numeric, errors='coerce')
            df_copy['平均ポジションスコア'] = df_copy[pos_score_cols].mean(axis=1)
            # 過去走が1走もない馬（過去走数=0）は 0.5（中団）で埋める
            df_copy['平均ポジションスコア'] = df_copy['平均ポジションスコア'].fillna(0.5)
        else:
            df_copy['平均ポジションスコア'] = 0.5

        # レース内の相対順位・割合を算出して想定脚質を割り振る
        if 'race_id' in df_copy.columns:
            # 昇順ランク (0.0: 最前に行きたがる 〜 1.0: 最後方)
            df_copy['ポジションランク'] = df_copy.groupby('race_id')['平均ポジションスコア'].rank(pct=True, ascending=True)
            df_copy['ポジション順位'] = df_copy.groupby('race_id')['平均ポジションスコア'].rank(method='min', ascending=True)
            
            def assign_assumed_style(row):
                # 1位は最前列＝「逃げ」
                if row['ポジション順位'] == 1:
                    return '逃げ'
                
                pct_rank = row['ポジションランク']
                if pct_rank <= 0.30:
                    return '先行'
                elif pct_rank <= 0.70:
                    return '差し'
                else:
                    return '追込'

            df_copy['想定脚質'] = df_copy.apply(assign_assumed_style, axis=1)
        else:
            df_copy['想定脚質'] = 'unknown'
            
        return df_copy
