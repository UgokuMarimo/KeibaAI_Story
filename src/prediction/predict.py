"""
レース予測実行スクリプト (m04_predict.py)

■ 役割
指定されたレースIDに対して、学習済みモデル（LightGBM）を用いて予測を行い、
結果をコンソール出力、Discord通知、およびデータベースに保存する。
また、SHAP値を用いた予測根拠の分析や、LLM（Gemini）を用いたレース解説の自動生成も行う。

■ 主な機能
1. 出馬表データのスクレイピング (netkeiba.com)
2. 過去走データの取得（スクレイピングまたはローカルCSV）
3. 特徴量エンジニアリング（m02と同様のパイプライン）
4. モデルによる予測（1着率）
5. SHAP値の計算と重要特徴量の抽出
6. LLMによる解説テキスト生成
7. 結果の保存（DB, JSON）と通知（Discord）

■ 使い方
python code/a4_prediction/m04_predict.py [race_id] [options]

引数:
  race_id       : 予測対象のレースID (12桁, 例: 202506010111)

オプション:
  --no-shap         : SHAP分析をスキップする（高速化のため）
  --use-overseas    : 海外・地方レースデータを含める（現在は未実装または実験的）
  --no-explanation  : LLMによる解説生成をスキップする
  --save-features   : 特徴量加工後のデータを中間ファイルとして保存する (debug_predict_features/{race_id}.csv)

例:
  python code/a4_prediction/m04_predict.py 202506010111
"""
import argparse
import traceback
import asyncio
import os
import sys

# --- プロジェクトパス設定 (最優先) ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# ここで初めて config をインポート
import config

import json
import lightgbm as lgb
import shap
from joblib import load
from dotenv import load_dotenv
import sys
import os
import pandas as pd
import numpy as np

# --- Windows環境でのUnicode出力エラー対策 (重要) ---
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# .envファイルの読み込み
load_dotenv()

# --- モジュールインポート ---
import config
from utils.feature_pipeline import (
    preprocess_and_clean, add_past_race_features, 
    engineer_advanced_features, add_race_level_features, encode_and_finalize
)
from utils.scraper import scrape_shutuba_table, load_past_race_data, load_past_race_data_with_overseas
from utils.db_utils import save_prediction_to_db, send_discord_webhook, format_for_discord

# 解説生成用モジュール
try:
    import google.generativeai as genai
    import chromadb
    import chromadb
    from explanation.explanation_templates import get_original_value_display, get_group_for_feature, EXPLANATION_TEMPLATES, get_feature_name_display
    
    # APIキー設定
    if "GOOGLE_API_KEY" in os.environ:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        GENERATION_MODEL = "gemini-2.5-flash"
        ENABLE_EXPLANATION = True
    else:
        print("[WARN] GOOGLE_API_KEY not found. Automated explanation disabled.")
        ENABLE_EXPLANATION = False

except ImportError as e:
    print(f"[WARN] Failed to import explanation modules: {e}. Automated explanation disabled.")
    ENABLE_EXPLANATION = False

def load_vector_db():
    """ベクトルDBクライアントをロード"""
    vector_db_path = os.path.join(PROJECT_ROOT, "vector_db")
    if not os.path.exists(vector_db_path):
        return None
    try:
        client = chromadb.PersistentClient(path=vector_db_path)
        return client.get_collection(name="race_results")
    except Exception as e:
        print(f"[WARN] Failed to load vector DB: {e}")
        return None

def generate_explanation(horse_data, collection, full_race_context=None):
    """
    上位馬の解説を生成する関数 (app.pyのロジックを移植 + 強化)
    """
    if not ENABLE_EXPLANATION:
        return None

    try:
        # RAG: ベクトルDB検索
        context_docs = ""
        if collection:
            search_query = f"{horse_data['horse_name']}の最近のレース内容"
            try:
                # Embedding Modelの設定 (安定版に変更)
                # EMBEDDING_MODEL = "models/text-embedding-004" # 404エラーが出るため変更 -> 元に戻す
                EMBEDDING_MODEL = "models/text-embedding-004"
                
                embedding_result = genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=search_query,
                    task_type="RETRIEVAL_QUERY"
                )
                query_embedding = embedding_result['embedding']
                
                retrieved = collection.query(
                    query_embeddings=[query_embedding], 
                    n_results=3
                )
                if retrieved['documents']:
                    context_docs = "\n".join(retrieved['documents'][0])
            except Exception as e:
                print(f"[WARN] Vector DB query failed: {e}")

        # --- 特徴量の整理とグループ化 (m04aとロジック統一) ---
        all_factors = horse_data['positive_factors'] + horse_data['negative_factors']
        shap_df = pd.DataFrame(all_factors)
        
        # グループ化
        if not shap_df.empty:
            shap_df['group'] = shap_df.apply(lambda row: get_group_for_feature(row['feature'], row['shap_value']), axis=1)
            group_summary = shap_df.groupby('group')['shap_value'].sum().sort_values(ascending=False)
        else:
            group_summary = pd.Series()
            shap_df['group'] = []

        positive_themes_list = []
        negative_themes_list = []

        for group_name, total_shap in group_summary.items():
            if abs(total_shap) < 0.05: continue # 影響の小さいグループは無視

            theme_body = f"\n## テーマ：{group_name} (総合貢献度: {total_shap:+.2f})\n"
            
            group_features = shap_df[shap_df['group'] == group_name].sort_values('shap_value', ascending=False)

            # 個々の特徴量の内訳を記述
            for _, factor in group_features.iterrows():
                feature_name = factor['feature']
                numeric_value = factor['value']
                shap_value = factor['shap_value']

                # 数値データを元の文字データに変換
                value_display = get_original_value_display(feature_name, numeric_value)

                # デフォルトテンプレートを使用
                if shap_value >= 0:
                    reason_text = EXPLANATION_TEMPLATES["default_positive"](feature_name, value_display, shap_value)
                else:
                    reason_text = EXPLANATION_TEMPLATES["default_negative"](feature_name, value_display, shap_value)

                theme_body += f"- {reason_text}\n"
            
            if total_shap > 0:
                positive_themes_list.append(theme_body)
            else:
                negative_themes_list.append(theme_body)

        # プロンプト作成 (User Request v2: 予想屋マスター風 & ストーリー重視)
        prompt = f"""あなたは「予想屋マスター」のような簡潔かつ鋭い分析を行うプロの競馬予想家です。
提供された機械学習モデルの分析データ（SHAP値）を元に、競走馬「{horse_data['horse_name']}」の「勝つための戦術」を明確にする解説文を生成してください。

# AIの総合評価
- 予測順位: {horse_data['pred_rank']}位
- 予測勝率: {horse_data['pred_win_prob']:.1%}

# 分析データサマリー
--- ポジティブ要因 ---
{chr(10).join(positive_themes_list) if positive_themes_list else "特になし"}

--- ネガティブ要因 ---
{chr(10).join(negative_themes_list) if negative_themes_list else "特になし"}

# 参考情報 (過去のレース内容など)
{context_docs if context_docs else "特になし"}

# 全出走馬の過去データ (Reference)
※ここにライバル馬の直近データがあります。他馬との比較（ペース判断、力量比較など）に活用してください。
{full_race_context if full_race_context else "データなし"}

# 出力形式の指示（この構造を厳守してください）

以下の5つのセクション（項目名を含む）に分けて解説文を記述してください。各セクションは詳細に、論理的かつ具体的に記述してください。

### 1. 結論と戦術
- 予測値（勝率）を踏まえた総合評価と、この馬が勝つために最も重要な戦術（例：先行粘り込み、末脚勝負、外からの差し切りなど）を明確に述べてください。
- 必要に応じて「ライバルの〇〇が逃げる展開なら…」といった相対的な視点を含めてください。

### 2. 根拠（強み）の詳細
- 「ポジティブ要因」から、特に貢献度が高い要因を抽出し、それがレースでどのように有利に働くかを具体的に、競馬用語を交えて解説してください。
- 特徴量名は既に「近走の末脚のメンバー内優位性」のように日本語化されていますので、そのまま使用してください。

### 3. 懸念材料とリスク
- 「ネガティブ要因」から、特に貢献度が高い要因を抽出し、どういうレース展開や条件になると不利になるかを具体的に解説してください。

### 4. 馬券戦略
- 予測順位と勝率から、この馬の馬券的信頼度を述べ、どのような種類の馬（例：先行力のある馬、タフなレース経験馬）を相手に選ぶべきかを推奨してください。

### 5. 総評
- 全てを統合し、最終的な見解を「今回のレースでは、～と見られます。」という形で締めてください。
- 勝つ確率の低い馬については、その厳しさを正当に評価しつつ、「唯一、～といった展開に恵まれれば、掲示板争いも可能です」のように、恵まれた場合の条件を記述してください。
"""
        # LLM実行
        model = genai.GenerativeModel(GENERATION_MODEL)
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"[WARN] Failed to generate explanation for {horse_data['horse_name']}: {e}")
        return None

def load_models():
    """
    モデルと関連アーティファクトを読み込む関数。
    バッチ処理などで再利用可能にするために分離。
    """
    print(f"[INFO] Loading models...")
    
    # トラックタイプごとにモデルをロード (芝/ダート)
    models = {}
    artifacts = {}
    
    for track_type in ['turf', 'dirt']:
        # Update path construction to match m03 (single versioning)
        # Old: models/{model_type}_models/{version} -> New: models/{version}
        artifacts_base_dir = os.path.join(config.ARTIFACTS_DIR, config.EXPERIMENT_VERSION)
        model_dir = os.path.join(config.MODEL_DIR_BASE, config.EXPERIMENT_VERSION)
        
        # アーティファクト読み込み
        try:
            time_scaler = load(os.path.join(artifacts_base_dir, f'time_scaler_{track_type}.joblib'))
            label_encoders = load(os.path.join(artifacts_base_dir, f'label_encoders_{track_type}.joblib'))
            
            # 統計情報の読み込み
            stats_to_load = config.STATS_TO_SAVE
            loaded_stats = {}
            for key in stats_to_load:
                path = os.path.join(artifacts_base_dir, f'{key}_{track_type}.joblib')
                if os.path.exists(path):
                    loaded_stats[key] = load(path)
                else:
                    print(f"[WARN] Artifact not found: {path}")
            
            artifacts[track_type] = {
                'time_scaler': time_scaler,
                'label_encoders': label_encoders,
                'loaded_stats': loaded_stats
            }
            
            # モデル読み込み
            imputer_win = load(os.path.join(model_dir, f'imputer_{track_type}_win.joblib'))
            imputer_place = load(os.path.join(model_dir, f'imputer_{track_type}_place.joblib')) if os.path.exists(os.path.join(model_dir, f'imputer_{track_type}_place.joblib')) else None
            
            # 特徴量リストのロード (UTF-8)
            features_win_path = os.path.join(model_dir, f'features_{track_type}_win.txt')
            features_win = []
            if os.path.exists(features_win_path):
                with open(features_win_path, 'r', encoding='utf-8') as f:
                    features_win = [line.strip() for line in f if line.strip()]
            
            features_place_path = os.path.join(model_dir, f'features_{track_type}_place.txt')
            features_place = []
            if os.path.exists(features_place_path):
                with open(features_place_path, 'r', encoding='utf-8') as f:
                    features_place = [line.strip() for line in f if line.strip()]

            models[track_type] = {
                'lgb_model_win': lgb.Booster(model_file=os.path.join(model_dir, f'lgb_model_{track_type}_win.txt')),
                'lgb_model_place': lgb.Booster(model_file=os.path.join(model_dir, f'lgb_model_{track_type}_place.txt')) if os.path.exists(os.path.join(model_dir, f'lgb_model_{track_type}_place.txt')) else None,
                'imputer_win': imputer_win,
                'imputer_place': imputer_place,
                'features_win': features_win,
                'features_place': features_place
            }
            
        except Exception as e:
            print(f"[WARN] Failed to load models/artifacts for {track_type}: {e}")
            # 該当するトラックタイプのレースが予測できないだけなので、続行
            
    return models, artifacts

def predict_race(race_id: str, run_shap: bool, use_overseas: bool = False, enable_explanation: bool = True, save_features: bool = False, send_discord: bool = True, realtime_odds: bool = False, models=None, artifacts=None):
    """
    1レース分の予測を実行する関数。
    models, artifacts が渡されない場合は内部でロードする。
    """
    try:
        print(f"--- [START] Prediction for race_id: {race_id} ---")
    except Exception as e:
        # Windows環境などでエンコーディングエラーが起きる場合の対策
        pass
    
    try:
        # モデルが渡されていない場合はロード
        # モデルが渡されていない場合はロード
        if models is None or artifacts is None:
            models, artifacts = load_models()

        # --- [Phase 0] Real-time Odds Fetching (Skip: get_realtime_win_odds is not defined) ---
        # Instead, we will use odds from shutuba_df which is scraped in Phase 1.
        realtime_odds_data = {} 

        # --- [Phase 1/5] データ取得 ---
        shutuba_df = scrape_shutuba_table(race_id)
        if shutuba_df is None or shutuba_df.empty:
            print("[FATAL] Failed to scrape shutuba data. Exiting.")
            return None

        
        # --- [Phase 2/5] 過去走データ取得 ---
        horse_ids = shutuba_df['horse_id'].astype(str).unique().tolist()
        race_date = shutuba_df['日付'].iloc[0]
        
        # ユーザー要望により、常に各馬の個別ページから最新データを取得する
        print("[INFO] Fetching past race data from individual horse pages (Scraping)...")
        try:
            past_race_df = load_past_race_data_with_overseas(
                horse_ids,
                race_date=race_date,
                num_past_races=config.NUM_PAST_RACES,
                use_horse_page=True, # 常にTrue
                save_to_cache=True
            )
        except Exception as e:
            print(f"[WARN] Failed to scrape data: {e}. Falling back to local CSVs.")
            traceback.print_exc()
            past_race_df = load_past_race_data(horse_ids)

        # 生データ (raw_race_data.csv) の保存
        # チャットボットのコンテキストとして使用するため
        if past_race_df is not None and not past_race_df.empty:
            race_id_str = str(race_id)
            if len(race_id_str) == 12:
                year, course, kaisai, nissuu, race_num = race_id_str[:4], race_id_str[4:6], race_id_str[6:8], race_id_str[8:10], race_id_str[10:]
                shap_output_dir = os.path.join(config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num)
            else:
                 shap_output_dir = os.path.join(config.SHAP_RESULTS_DIR, race_id_str)
            
            os.makedirs(shap_output_dir, exist_ok=True)
            raw_data_path = os.path.join(shap_output_dir, "raw_race_data.csv")
            try:
                past_race_df.to_csv(raw_data_path, index=False, encoding='utf-8')
                print(f"[INFO] Saved raw race data to: {raw_data_path}")
            except Exception as e:
                print(f"[WARN] Failed to save raw_race_data.csv: {e}")

        track_surface = shutuba_df['芝・ダート'].iloc[0]
        if '障' in track_surface or '新馬' in shutuba_df['レース名'].iloc[0]:
            print(f"[INFO] Skipping prediction for steeplechase or debut race.")
            print("[SKIPPED] This race is a debut or steeplechase race and is not supported.")
            return None

        # --- [Phase 3/5] 特徴量生成 ---
        print("\n--- [Phase 3/5] Feature Generation ---")
        track_type = 'turf' if '芝' in track_surface else 'dirt'
        
        if track_type not in models:
            print(f"[FATAL] Model for {track_type} not loaded.")
            return None
            
        current_artifacts = artifacts[track_type]
        time_scaler = current_artifacts['time_scaler']
        label_encoders = current_artifacts['label_encoders']
        loaded_stats = current_artifacts['loaded_stats']

        # 特徴量パイプライン実行
        if past_race_df is not None and not past_race_df.empty:
            # FutureWarning対策: 全てNaNの列は除外してから結合
            past_race_df = past_race_df.dropna(how='all', axis=1)
            
            # --- 簡易的な獲得賞金_合計の計算 (過去走データからの積み上げ) ---
            # 本来はプロフィールページから取得するべきだが、予測時は過去データから推定する
            if '賞金' in past_race_df.columns and 'horse_id' in past_race_df.columns:
                 # 数値変換
                 past_race_df['賞金_temp'] = pd.to_numeric(past_race_df['賞金'], errors='coerce').fillna(0)
                 total_prize = past_race_df.groupby('horse_id')['賞金_temp'].sum().reset_index()
                 total_prize.rename(columns={'賞金_temp': '獲得賞金_合計'}, inplace=True)
                 
                 # shutuba_dfにマージ
                 shutuba_df = pd.merge(shutuba_df, total_prize, on='horse_id', how='left')
                 shutuba_df['獲得賞金_合計'] = shutuba_df['獲得賞金_合計'].fillna(0) # 過去走ない馬は0
                 
                 # 不要カラム削除
                 if '賞金_temp' in past_race_df.columns: past_race_df.drop('賞金_temp', axis=1, inplace=True)
            else:
                 shutuba_df['獲得賞金_合計'] = 0

            combined_df = pd.concat([shutuba_df, past_race_df], ignore_index=True, sort=False)
        else:
            shutuba_df['獲得賞金_合計'] = 0
            combined_df = shutuba_df.copy()

        processed_df, _ = preprocess_and_clean(combined_df, time_scaler=time_scaler)
        
        df_with_past = add_past_race_features(processed_df, config.NUM_PAST_RACES, config.PAST_RACE_FEATURES)
        df_featured, _ = engineer_advanced_features(df_with_past, config.NUM_PAST_RACES, jockey_rates=loaded_stats)
        df_race_level = add_race_level_features(df_featured)
        
        predict_target_df = df_race_level[df_race_level['race_id'] == str(race_id)].copy()
        if predict_target_df.empty:
            print("[FATAL] No target race data to process after feature engineering.")
            return None
            
        categorical_features = config.CATEGORICAL_FEATURES
        features_df, _ = encode_and_finalize(predict_target_df, categorical_features, label_encoders=label_encoders)
        
        features_df.reset_index(drop=True, inplace=True)

        # --- [Phase 4/5] 予測実行 ---
        print("\n--- [Phase 4/5] Prediction ---")
        
        current_model = models[track_type]
        lgb_model_win = current_model['lgb_model_win']
        lgb_model_place = current_model.get('lgb_model_place') # 3着以内モデル (あれば)
        imputer_win = current_model['imputer_win']
        imputer_place = current_model.get('imputer_place')

        # --- 1着率 (Win) 予測のデータ構成と実行 ---
        model_columns_win = current_model.get('features_win', [])
        if not model_columns_win:
            model_columns_win = lgb_model_win.feature_name()
        X_predict_win = pd.DataFrame(columns=model_columns_win, index=features_df.index)
        for col in model_columns_win:
            if col in features_df.columns:
                X_predict_win[col] = features_df[col]
            else:
                X_predict_win[col] = np.nan

        leakage_cols = config.LEAKAGE_FEATURES
        cols_to_drop_win = [col for col in X_predict_win.columns if col in leakage_cols]
        X_predict_cleaned_win = X_predict_win.drop(columns=cols_to_drop_win, errors='ignore')
        X_predict_cleaned_win.replace('', np.nan, inplace=True)
        X_predict_cleaned_win = X_predict_cleaned_win.apply(pd.to_numeric, errors='coerce')

        # --- Debug Feature Output ---
        if save_features:
            debug_dir = os.path.join(PROJECT_ROOT, 'debug_predict_features')
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, f"{race_id}.csv")
            debug_df = X_predict_cleaned_win.copy()
            
            if '馬番' not in debug_df.columns and '馬番' in features_df.columns:
                debug_df['馬番'] = features_df['馬番'].values

            name_map = shutuba_df[['馬番', '馬']].drop_duplicates().set_index('馬番')['馬']
            if '馬番' in debug_df.columns:
                 debug_df['馬番'] = pd.to_numeric(debug_df['馬番'], errors='coerce')
                 debug_df['馬名'] = debug_df['馬番'].map(name_map)
            
            cols = list(debug_df.columns)
            if '馬番' in cols: cols.remove('馬番'); cols.insert(0, '馬番')
            if '馬名' in cols: cols.remove('馬名'); cols.insert(1, '馬名')
            debug_df = debug_df[cols]
            
            debug_df.to_csv(debug_file, index=False, encoding='utf_8_sig')
            print(f"[DEBUG] Saved feature data to: {debug_file}")

        X_predict_imputed_win = pd.DataFrame(imputer_win.transform(X_predict_cleaned_win), columns=X_predict_cleaned_win.columns)
        pred_win = lgb_model_win.predict(X_predict_imputed_win.values)
        
        # SHAP分析で使用するために X_predict_imputed を定義しておく (互換性維持のため、win用のデータを代入)
        X_predict_imputed = X_predict_imputed_win
        
        # --- 3着内率 (Place) 予測のデータ構成と実行 ---
        if lgb_model_place and imputer_place:
            model_columns_place = current_model.get('features_place', [])
            if not model_columns_place:
                model_columns_place = lgb_model_place.feature_name()
            X_predict_place = pd.DataFrame(columns=model_columns_place, index=features_df.index)
            for col in model_columns_place:
                if col in features_df.columns:
                    X_predict_place[col] = features_df[col]
                else:
                    X_predict_place[col] = np.nan

            cols_to_drop_place = [col for col in X_predict_place.columns if col in leakage_cols]
            X_predict_cleaned_place = X_predict_place.drop(columns=cols_to_drop_place, errors='ignore')
            X_predict_cleaned_place.replace('', np.nan, inplace=True)
            X_predict_cleaned_place = X_predict_cleaned_place.apply(pd.to_numeric, errors='coerce')

            X_predict_imputed_place = pd.DataFrame(imputer_place.transform(X_predict_cleaned_place), columns=X_predict_cleaned_place.columns)
            pred_place = lgb_model_place.predict(X_predict_imputed_place.values)
            
            # --- 3.0正規化を適用 (同一レース内での合計が 3.0 になるようにスケーリング) ---
            sum_pred_place = np.sum(pred_place)
            headcount = len(pred_place)
            limit = min(3.0, float(headcount))
            if sum_pred_place > 0:
                pred_place = pred_place * (limit / sum_pred_place)
                pred_place = np.minimum(1.0, pred_place)
        else:
            pred_place = np.zeros(len(pred_win))

        # 結果を整形
        base_info_df = shutuba_df[['馬番', '馬', 'horse_id']].copy().rename(columns={'馬': '馬名'})
        pred_df = pd.DataFrame({
            'pred_win': pred_win, 
            'pred_place': pred_place,
            '馬番': features_df['馬番'].values
        })
        
        base_info_df['馬番'] = pd.to_numeric(base_info_df['馬番'], errors='coerce')
        pred_df['馬番'] = pd.to_numeric(pred_df['馬番'], errors='coerce')
        
        final_result_df = pd.merge(base_info_df, pred_df, on='馬番', how='left')
        final_result_df['rank_win'] = final_result_df['pred_win'].rank(ascending=False, method='first').astype(int)
        final_result_df.sort_values('rank_win', inplace=True)
        
        # --- 正規化予測スコアの計算 (解説生成用) ---
        # Rawスコアの合計で割って確率化する (合計1.0にする)
        total_pred_win = final_result_df['pred_win'].sum()
        if total_pred_win > 0:
            final_result_df['normalized_pred_win'] = final_result_df['pred_win'] / total_pred_win
        else:
            final_result_df['normalized_pred_win'] = 0.0

        # --- [Phase 5/5] SHAP 分析 & 結果保存 ---
        # フォルダ構成を階層化: shap_results/YYYY/CC/KK/DD/RR
        race_id_str = str(race_id)
        if len(race_id_str) == 12:
            year, course, kaisai, nissuu, race_num = race_id_str[:4], race_id_str[4:6], race_id_str[6:8], race_id_str[8:10], race_id_str[10:]
            shap_output_dir = os.path.join(config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num)
        else:
            # Fallback for invalid format
            shap_output_dir = os.path.join(config.SHAP_RESULTS_DIR, race_id)
            
        os.makedirs(shap_output_dir, exist_ok=True)
        
        # 全頭の結果サマリーを作成
        summary_data = []
        
        # ベクトルDBのロード (解説生成用)
        vector_db_collection = load_vector_db() if ENABLE_EXPLANATION else None
        
        if run_shap:
            print("\n--- [Phase 5/5] SHAP Analysis ---")
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning, module="shap")
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning, module="shap")
                    # SHAPはWinモデルで計算する
                    explainer = shap.TreeExplainer(lgb_model_win)
                    shap_values_list = explainer.shap_values(X_predict_imputed)
                
                if isinstance(shap_values_list, list):
                    shap_values = shap_values_list[1]
                else:
                    shap_values = shap_values_list

                # 全出走馬の過去データコンテキスト構築 (Gemini 2.5 Flash用)
                full_race_context_str = ""
                if past_race_df is not None and not past_race_df.empty:
                    try:
                        history_lines = []
                        if 'horse_id' in past_race_df.columns:
                             # shutuba_dfから馬名マップ
                             id_name_map = {}
                             if 'horse_id' in shutuba_df.columns and '馬' in shutuba_df.columns:
                                 id_name_map = shutuba_df.set_index('horse_id')['馬'].to_dict()
                             
                             grouped = past_race_df.groupby('horse_id')
                             for hid, group in grouped:
                                 hid_str = str(hid)
                                 horse_name = id_name_map.get(hid, id_name_map.get(str(hid), f"ID:{hid}"))
                                 
                                 if '日付' in group.columns:
                                     group['date_dt'] = pd.to_datetime(group['日付'], format='%Y年%m月%d日', errors='coerce')
                                     group = group.sort_values('date_dt', ascending=False)
                                 
                                 recent_5 = group.head(5)
                                 
                                 h_lines = [f"### {horse_name} (ID:{hid_str})"]
                                 for _, r in recent_5.iterrows():
                                     race_str = f"- {r.get('日付')} {r.get('レース名', '')}: {r.get('着順')}着 (人:{r.get('人気', '-')}) {r.get('芝・ダート', '')}{r.get('距離', '')}m {r.get('走破時間', '-')} (3F:{r.get('上がり', '-')}) 通過:{r.get('通過順', '-')}"
                                     h_lines.append(race_str)
                                 history_lines.append("\n".join(h_lines))
                        full_race_context_str = "\n\n".join(history_lines)
                    except Exception as e:
                        print(f"[WARN] Failed to build full race context: {e}")

                # 全頭分のデータを処理
                for i in range(len(final_result_df)): 
                    horse_info = final_result_df.iloc[i]
                    horse_umaban = int(horse_info['馬番'])
                    
                    original_idx_list = features_df.index[features_df['馬番'] == horse_umaban].tolist()
                    if not original_idx_list: continue
                    original_idx = original_idx_list[0]

                    shap_df = pd.DataFrame({
                        'feature': X_predict_imputed.columns,
                        'shap_value': shap_values[original_idx],
                        'value': X_predict_imputed.iloc[original_idx].values
                    })
                    
                    shap_df['value'] = shap_df['value'].astype(float)
                    shap_df['shap_value'] = shap_df['shap_value'].astype(float)

                    positive_features_all = shap_df[shap_df['shap_value'] > 0].sort_values('shap_value', ascending=False)
                    negative_features_all = shap_df[shap_df['shap_value'] < 0].sort_values('shap_value', ascending=True)

                    # データ構築
                    horse_data = {
                        "race_id": race_id,
                        "horse_name": horse_info['馬名'],
                        "horse_id": str(horse_info['horse_id']) if 'horse_id' in horse_info else "", 
                        "umaban": horse_umaban,
                        "track_type": track_type, # Add track type
                        # 解説用に正規化した勝率を使用する
                        "pred_win_prob": float(horse_info['normalized_pred_win']), 
                        "pred_win": float(horse_info['pred_win']), # Add raw prediction score
                        "pred_rank": int(horse_info['rank_win']),
                        "positive_factors": positive_features_all.to_dict('records'),
                        "negative_factors": negative_features_all.to_dict('records'),
                        "explanation": None # 初期値
                    }
                    
                    # 上位3頭は解説を自動生成
                    if horse_info['rank_win'] <= 3 and ENABLE_EXPLANATION and enable_explanation:
                        print(f"  Generating explanation for Rank {horse_info['rank_win']}: {horse_info['馬名']}...")
                        explanation = generate_explanation(horse_data, vector_db_collection, full_race_context=full_race_context_str)
                        horse_data["explanation"] = explanation

                    summary_data.append(horse_data)

                    # 上位3頭は個別のJSONも保存（互換性維持のため）
                    if horse_info['rank_win'] <= 3:
                        save_path = os.path.join(shap_output_dir, f"shap_rank_{horse_info['rank_win']}.json")
                        with open(save_path, 'w', encoding='utf-8') as f:
                            json.dump(horse_data, f, ensure_ascii=False, indent=4)
                        
                        # コンソール表示 (Top 3のみ)
                        print(f"\n[予測] {horse_info['rank_win']}位: {horse_umaban}番 {horse_info['馬名']} (予測値: {horse_info['pred_win']:.4f})")
                        print("  [好材料] TOP5")
                        for _, row in positive_features_all.head(5).iterrows():
                            print(f"    - {row['feature']:<30} (値: {row['value']:.2f}, 貢献度: {row['shap_value']:.4f})")
                        print("  [不安材料] TOP5")
                        for _, row in negative_features_all.head(5).iterrows():
                            print(f"    - {row['feature']:<30} (値: {row['value']:.2f}, 貢献度: {row['shap_value']:.4f})")

            except Exception as e:
                print(f"\n[SHAP ERROR] An error occurred: {e}")
                traceback.print_exc()
        else:
            # SHAPなしの場合でもサマリーは作成
             for i in range(len(final_result_df)):
                horse_info = final_result_df.iloc[i]
                summary_data.append({
                    "race_id": race_id,
                    "horse_name": horse_info['馬名'],
                    "umaban": int(horse_info['馬番']),
                    "track_type": track_type, # Add track type
                    "pred_win_prob": float(horse_info['normalized_pred_win']),
                    "pred_win": float(horse_info['pred_win']),
                    "pred_rank": int(horse_info['rank_win']),
                    "positive_factors": [],
                    "negative_factors": [],
                    "explanation": None
                })



        # --- Real-time Odds & EV Calculation ---
        # --- Real-time Odds & EV Calculation ---
        if realtime_odds:
            print("\n--- Calculating Expected Value (EV) with Real-time Odds ---")
            try:
                # Use odds from shutuba_df
                if shutuba_df is not None and not shutuba_df.empty and 'オッズ' in shutuba_df.columns:
                    # Create odds dict from shutuba_df
                    # '馬番' column might be int or float. Convert to string for consistent key.
                    odds_dict = {}
                    for _, row in shutuba_df.iterrows():
                        try:
                            # 'オッズ' is already numeric or NaN in shutuba_df (from scrape_shutuba_table)
                            o = row['オッズ']
                            if pd.notna(o):
                                u = str(int(row['馬番']))
                                odds_dict[u] = float(o)
                        except:
                            pass
                    
                    if not odds_dict:
                        print("[WARN] No valid odds found in shutuba_df. Skipping EV calculation.")
                    else:
                        print(f"Using odds from shutuba table for {len(odds_dict)} horses.")
                        
                        # Merge and Calculate EV
                        count_matched = 0
                        for horse in summary_data:
                            umaban = str(horse['umaban'])
                            if umaban in odds_dict:
                                odds = odds_dict[umaban]
                                horse['win_odds'] = odds
                                horse['expected_value'] = horse['pred_win_prob'] * odds
                                count_matched += 1
                            else:
                                horse['win_odds'] = None
                                horse['expected_value'] = 0.0
                        print(f"Updated EV for {count_matched} horses.")
                else:
                    print("[WARN] shutuba_df is missing or has no 'オッズ' column. Skipping EV calculation.")

            except Exception as e:
                print(f"[ERROR] Failed during EV calculation: {e}")
                traceback.print_exc()

            except Exception as e:
                print(f"[ERROR] Failed during EV calculation: {e}")
                traceback.print_exc()

        # 全頭サマリーJSONの保存
        summary_path = os.path.join(shap_output_dir, "prediction_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=4)
        print(f"-> Full prediction summary saved to: {summary_path}")

        # --- [完了] 通知とDB保存 ---
        discord_message = format_for_discord(race_id, shutuba_df.iloc[0], final_result_df)
        if send_discord:
            send_discord_webhook(discord_message)
        else:
            print("[INFO] Discord notification skipped.")
        
        try:
            save_prediction_to_db(final_result_df, shutuba_df, race_id)
        except Exception as e:
            print(f"[DB ERROR] Failed to save to DB: {e}")

        print("\n--- [SUCCESS] All processes complete. ---")
        return final_result_df
        
    except Exception as e:
        print("\n--- [FATAL ERROR] An unexpected error occurred in main process ---")
        traceback.print_exc()

def main(race_id: str, run_shap: bool, use_overseas: bool = False, enable_explanation: bool = True, send_discord: bool = True, realtime_odds: bool = False):
    predict_race(race_id, run_shap, use_overseas, enable_explanation, send_discord=send_discord, realtime_odds=realtime_odds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict and explain a horse race.")
    parser.add_argument('race_id', help='Target 12-digit race ID')
    # parser.add_argument('--model', dest='model_type', default='B', help="Model type to use (default: 'B' for Baseline)")
    parser.add_argument('--no-shap', action='store_false', dest='run_shap', help="Disable SHAP analysis.")
    parser.add_argument('--use-overseas', action='store_true', dest='use_overseas', help="Include overseas and local race data.")
    parser.add_argument('--no-explanation', action='store_true', help='Skip LLM explanation generation')
    parser.add_argument('--save-features', action='store_true', help='Save processed features to CSV for debugging')
    parser.add_argument('--no-discord', action='store_false', dest='send_discord', help="Disable Discord notification.")
    parser.add_argument('--realtime_odds', action='store_true', help="Fetch real-time odds and calculate EV.")
    parser.set_defaults(send_discord=True)
    
    args = parser.parse_args()
    
    predict_race(
        args.race_id, 
        run_shap=args.run_shap, 
        use_overseas=args.use_overseas,
        enable_explanation=not args.no_explanation,
        save_features=args.save_features,
        send_discord=args.send_discord,
        realtime_odds=args.realtime_odds
    )