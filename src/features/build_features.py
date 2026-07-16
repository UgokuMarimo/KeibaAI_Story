# C:\KeibaAI\code\a2_build_features\m02_build_training_data.py

"""
生のレース結果データを元に、特徴量エンジニアリングを行い、
学習データと変換器を生成する統合スクリプト。

■ このスクリプトの役割
- config.py の設定に基づき、特徴量の選択や処理を行う。
- バージョン管理されたディレクトリにデータを保存する。

■ 修正版 ("Split-Scale-Merge-History-Split" パターン)
1. Split & Scale: 芝/ダートそれぞれでスケーリング (物理的な違いを考慮)
2. Merge: 一度統合
3. History: 統合データで過去走を参照 (芝⇔ダート替わりの馬の履歴保持)
4. Split: モデル用に再度分割して保存

■ 使い方
- データを生成: python code/a2_build_features/m02_build_training_data.py
"""
# --- プロジェクトパスとライブラリのインポート ---
import sys
import os
import pandas as pd
from joblib import dump
import warnings
from typing import List, Dict, Tuple, Any

warnings.filterwarnings('ignore')

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# --- モジュールインポート ---
import config
from utils.feature_pipeline import(
    preprocess_and_clean, add_past_race_features, engineer_advanced_features, 
    add_race_level_features, encode_and_finalize
)

def load_and_combine_data(start_year: int, end_year: int) -> pd.DataFrame:
    """指定された期間の生データを読み込み、一つのDataFrameに結合する（共通関数）"""
    print("--- Loading and combining raw data ---")
    df_list = []
    dtype_spec = {'race_id': str, 'horse_id': str, 'jockey_id': str}
    
    for year in range(start_year, end_year + 1):
        # 1. JRA Data
        file_path = os.path.join(config.RAW_DATA_DIR, f"{year}.csv")
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path, encoding="SHIFT-JIS", header=0, low_memory=False, 
                                dtype=dtype_spec)
                # 日付パース (JRA形式: YYYY年MM月DD日)
                df['日付'] = pd.to_datetime(df['日付'], format='%Y年%m月%d日', errors='coerce')
                df['is_jra'] = 1
                df_list.append(df)
            except Exception as e:
                print(f"ERROR: Failed to read {file_path}: {e}")

        # 2. Overseas/Local Data
        kaigai_path = os.path.join(config.DATA_DIR, "kaigai", f"local_overseas_past_races_{year}.csv")
        if os.path.exists(kaigai_path):
            try:
                df_kaigai = pd.read_csv(kaigai_path, encoding="SHIFT-JIS", header=0, low_memory=False, 
                                        dtype=dtype_spec)
                # 日付パース (柔軟に対応)
                parsed_dates = pd.to_datetime(df_kaigai['日付'], format='%Y年%m月%d日', errors='coerce')
                missing_mask = parsed_dates.isna() & df_kaigai['日付'].notna()
                if missing_mask.any():
                    parsed_dates[missing_mask] = pd.to_datetime(df_kaigai['日付'][missing_mask], errors='coerce')
                df_kaigai['日付'] = parsed_dates
                df_kaigai['is_jra'] = 0
                df_list.append(df_kaigai)
                print(f"  [INFO] Loaded overseas/local data: {kaigai_path}")
            except Exception as e:
                print(f"ERROR: Failed to read {kaigai_path}: {e}")
            
    if not df_list:
        print("FATAL: No data to process."); return pd.DataFrame()
        
    raw_df = pd.concat(df_list, ignore_index=True)
    
    # race_idの数値変換は行わない (海外レースID 'local_overseas' がNaNになるのを防ぐため)
    # raw_df['race_id'] = pd.to_numeric(raw_df['race_id'], errors='coerce')
    
    print(f"--- Data loading complete ({len(raw_df)} rows) ---")
    return raw_df

def main():
    """学習データを生成するメイン関数"""
    
    # --- 保存先ディレクトリ設定 ---
    # バージョンごとにディレクトリを分ける
    output_base_dir = os.path.join(config.ENCODED_DIR, config.EXPERIMENT_VERSION)
    artifacts_base_dir = os.path.join(config.ARTIFACTS_DIR, config.EXPERIMENT_VERSION)
    os.makedirs(output_base_dir, exist_ok=True)
    os.makedirs(artifacts_base_dir, exist_ok=True)

    # --- 1. データ読み込み ---
    raw_df_combined = load_and_combine_data(config.BUILD_START_YEAR, config.BUILD_END_YEAR)
    if raw_df_combined.empty: return

    # --- 賞金データの処理 (獲得賞金_合計) ---
    if '賞金' in raw_df_combined.columns:
        raw_df_combined['賞金'] = pd.to_numeric(raw_df_combined['賞金'], errors='coerce').fillna(0)
        raw_df_combined.sort_values(by=['馬', '日付'], inplace=True)
        raw_df_combined['獲得賞金_合計'] = raw_df_combined.groupby('馬')['賞金'].transform(lambda x: x.cumsum().shift(1)).fillna(0)
    else:
        print("[WARN] '賞金' column not found. '獲得賞金_合計' will be 0.")
        raw_df_combined['獲得賞金_合計'] = 0

    track_map = {'turf': '芝', 'dirt': 'ダ'}

    # --- 2. Split & Scale (個別スケーリング) ---
    print("\n--- Phase 2: Separate Scaling (Turf/Dirt) ---")
    df_scaled_list = []
    
    for track_key, track_name in track_map.items():
        # ダート/芝でフィルタリング
        df_track = raw_df_combined[raw_df_combined['芝・ダート'].str.strip() == track_name].copy()
        
        if df_track.empty:
            print(f"[WARN] No data for {track_key}. Skipping scaling.")
            continue
            
        print(f"Processing {track_key} scaling... ({len(df_track)} rows)")
        
        # preprocess_and_clean で time_scaler をフィットさせ、'走破時間_scaled' を生成する
        # ここでフィットされた time_scaler を保存し、このデータセットに適用する
        df_track_scaled, track_time_scaler = preprocess_and_clean(df_track, time_scaler=None)
        
        # スケーラー保存 (time_scaler_turf.joblib, time_scaler_dirt.joblib)
        dump(track_time_scaler, os.path.join(artifacts_base_dir, f'time_scaler_{track_key}.joblib'))
        
        df_scaled_list.append(df_track_scaled)
        
    # トラック以外のデータ（障害など）も含める場合、未スケーリングで追加も検討すべきだが、
    # 今回は芝・ダート予測がメインなので、それらのみを結合して学習用とする。
    # (海外レースも芝・ダートいずれかに入っているはず)
    
    if not df_scaled_list:
        print("[FATAL] No scaled data available.")
        return

    # --- 3. Merge (統合) ---
    print("\n--- Phase 3: Merging Scaled Data ---")
    df_all_scaled = pd.concat(df_scaled_list, ignore_index=True)
    print(f"Merged Data Shape: {df_all_scaled.shape}")
    
    # --- 4. History (過去走追加 - クロスサーフェス対応) ---
    print("\n--- Phase 4: Adding Past Race Features (Cross-Surface History) ---")
    # ここで全データに対して過去走参照を行うため、芝⇔ダート替わりの履歴も保持される
    df_with_history = add_past_race_features(df_all_scaled, config.NUM_PAST_RACES, config.PAST_RACE_FEATURES)
    
    # 重複回避のため race_id, 馬 で一意にする (add_past_race_features は行数を変えないが念のため)
    # ここでの重複排除は不要かもしれないが、念のためgroupby firstなどはせずそのまま進む。
    
    # --- 5. Stats Calculation (統計量算出) ---
    print("\n--- Phase 5: Calculating Advanced Stats ---")
    
    # 統計量算出用のデータ期間フィルタリング (リーク防止 & 近走重視)
    stats_calc_start_year = config.JOCKEY_RATE_BUILD_END_YEAR - config.JOCKEY_RATE_TERM
    df_for_stats = df_with_history[
        (df_with_history['year'] <= config.JOCKEY_RATE_BUILD_END_YEAR) & 
        (df_with_history['year'] > stats_calc_start_year) # 直近N年分のみ
    ].copy()
    
    print(f"[INFO] Calculating stats using data from {stats_calc_start_year + 1} to {config.JOCKEY_RATE_BUILD_END_YEAR} ({config.JOCKEY_RATE_TERM} years)")
    
    if df_for_stats.empty:
        print("[FATAL] No data for stats calculation.")
        return

    # 統計量を計算 (jockey_rates=None で計算モード)
    # ここで計算される騎手勝率などは「芝・ダート混合」全体の成績になるが、
    # engineer_advanced_features 内で 'jockey_track_suitability' (芝・ダート別勝率) も計算されるため問題ない。
    # むしろ混合データで計算することで、よりロバストな統計量になる。
    _, calculated_stats = engineer_advanced_features(df_for_stats, config.NUM_PAST_RACES, jockey_rates=None)
    
    # 統計量アーティファクトの保存
    # 注意: ここでは 'jockey_rate' はトラック区別なしの全体勝率として保存される。
    # トラック別の予測モデル作成時に読み込む際、これが共通で使われる。
    stats_to_save = config.STATS_TO_SAVE
    print(f"[INFO] Saving {len(stats_to_save)} types of artifacts (Common Stats).")
    
    for key in stats_to_save:
        if key in calculated_stats:
            # 以前は _turf.joblib のように分けていたが、今回は共通統計量とするため _common を使うか、
            # 既存の読み込みコード(m04)との互換性を考え、同じものを _turf, _dirt 両方の名前で保存する。
            # または m04 側で読み込むファイル名を変更する必要がある。
            # m04_predict.py の load_artifacts は f"{artifact_name}_{model_type}.joblib" を探すか？
            # 確認要: m04は artifacts[f'jockey_rate_{model_type}'] のように使うか？
            # 既存feature_pipeline.pyの engineer_advanced_features は引数 jockey_rates を辞書で受け取る。
            # m04では load_artifacts で辞書を作って渡している。
            # feature_pipeline.py 内で辞書キーは 'jockey_rate' 固定。ファイル名だけが可変。
            # したがって、保存時に _turf, _dirt 両方の名前でコピー保存しておくのが最も安全（変更コスト小）。
            
            dump(calculated_stats[key], os.path.join(artifacts_base_dir, f'{key}_turf.joblib'))
            dump(calculated_stats[key], os.path.join(artifacts_base_dir, f'{key}_dirt.joblib'))

    # --- 6. Apply Stats & Final Split (統計量適用と最終分割) ---
    print("\n--- Phase 6: Applying Stats & Final Splitting ---")
    
    # 全期間データに統計量を適用
    df_all_featured, _ = engineer_advanced_features(df_with_history, config.NUM_PAST_RACES, jockey_rates=calculated_stats)
    
    # レースレベル特徴量 (平均・標準偏差など) の追加
    # これはレースごとなので、分割前でも後でも良いが、ここで一括でやる
    df_all_featured = add_race_level_features(df_all_featured)
    
    track_map_encoded = {'turf': 0, 'dirt': 1}

    # 最終分割と保存
    for track_key, track_name in track_map.items():
        print(f"\nProcessing Final Output for {track_key.upper()}...")
        
        # トラックで分割 (エンコード済みの値を使用)
        encoded_val = track_map_encoded[track_key]
        df_final = df_all_featured[df_all_featured['芝・ダート'] == encoded_val].copy()
        
        if df_final.empty:
            print(f"No data for {track_key} in final stage.")
            continue
            
        # 特徴量選択 (Drop)
        categorical_features = config.CATEGORICAL_FEATURES
        drop_conf = config.FEATURES_TO_DROP
        cols_to_drop = drop_conf.get('common', []) + drop_conf.get(track_key, [])
        
        df_final_dropped = df_final.drop(columns=[c for c in cols_to_drop if c in df_final.columns], errors='ignore').copy()
        print(f"[INFO] Dropped columns for {track_key}. Final shape: {df_final_dropped.shape}")
        
        # エンコーディング (Label Encoding)
        # 各トラックごとにエンコーダーを作成・保存する
        df_encoded, label_encoders_calculated = encode_and_finalize(df_final_dropped, categorical_features, label_encoders=None)
        dump(label_encoders_calculated, os.path.join(artifacts_base_dir, f'label_encoders_{track_key}.joblib'))
        
        # 保存
        output_path = os.path.join(output_base_dir, f'encoded_data_{track_key}.csv')
        df_encoded.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"SUCCESS: Full training data ({track_key}) saved to -> {output_path}")

    print(f"\n--- All training data building processes finished. ---")

if __name__ == "__main__":
    main()