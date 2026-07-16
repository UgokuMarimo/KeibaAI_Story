import pandas as pd
import numpy as np
import os
import sys
import sqlite3
import json
import lightgbm as lgb
from sklearn.impute import SimpleImputer

sys.stdout.reconfigure(encoding='utf-8')

# プロジェクトパス設定
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import config

def get_model_params(track: str, target_type: str) -> dict:
    param_key = f"LGB_PARAMS_{target_type.upper()}_{track.upper()}"
    params = getattr(config, param_key, None)
    if params is None:
        params = {
            "objective": "binary", "metric": "auc", "verbosity": -1, 
            "boosting_type": "gbdt", "class_weight": "balanced"
        }
    return params

def prepare_data(df: pd.DataFrame, track: str):
    # m03_train_model.py の prepare_features_and_labels と同じドロップ処理
    cols_to_drop = [
        'race_id', 'horse_id', '騎手', '馬', '日付', 'レース名', '開催', 'year', '着順', '通過順', 
        '芝・ダート', 
        f'過去{config.NUM_PAST_RACES}走_条件_走破時間_scaled_times'
    ]
    leak_features_current_race = config.LEAKAGE_FEATURES
    cols_to_drop.extend([c for c in leak_features_current_race if c not in cols_to_drop])

    past_date_cols = [f'日付{i}' for i in range(1, config.NUM_PAST_RACES + 2)]
    cols_to_drop.extend(past_date_cols)

    old_scaled_race_level_features = [
        '走破時間_scaled_race_mean', '走破時間_scaled_race_max', '走破時間_scaled_race_min', 
        '走破時間_scaled_race_dev', '走破時間_scaled_race_max_diff', '走破時間_scaled_race_min_diff'
    ]
    cols_to_drop.extend(old_scaled_race_level_features)
    
    # 不要な特徴量を削除
    features_to_drop_conf = config.FEATURES_TO_DROP
    cols_to_drop.extend(features_to_drop_conf.get('common', []))
    cols_to_drop.extend(features_to_drop_conf.get(track, []))
    
    cols_to_drop = list(set(cols_to_drop))
    X = df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')
    X = X.dropna(axis=1, how='all')
    
    # 数値型以外の列（文字列や日付型など）を確実に除外
    X = X.select_dtypes(include=[np.number])
    
    return X

def main():
    print("=== 勝率・複勝率の複合閾値シミュレーション ===")
    
    # 1. 芝データのロード (大容量のため低メモリ読み込み)
    encoded_path = os.path.join(config.ENCODED_DIR, config.EXPERIMENT_VERSION, 'encoded_data_turf.csv')
    print(f"Loading turf encoded data: {encoded_path}")
    df = pd.read_csv(encoded_path, low_memory=False)
    
    # 日付から年度を取得
    df['parsed_date'] = pd.to_datetime(df['日付'])
    df['year'] = df['parsed_date'].dt.year
    
    # 2026年をテストデータ、それ以前を学習データにする
    train_df = df[df['year'] < 2026].copy()
    test_df = df[df['year'] == 2026].copy()
    
    print(f"Train data size: {len(train_df)} rows")
    print(f"Test data size (2026): {len(test_df)} rows")
    
    if test_df.empty:
        print("[ERROR] No test data in 2026!")
        return
        
    # 生データからオッズをロードしてテストデータにマージ
    raw_2026_path = os.path.join(config.RAW_DATA_DIR, "2026.csv")
    print(f"Loading raw 2026 data for odds and popularity: {raw_2026_path}")
    raw_df = pd.read_csv(raw_2026_path, encoding="SHIFT-JIS", usecols=['race_id', '馬番', 'オッズ', '人気'])
    raw_df['race_id'] = raw_df['race_id'].astype(str)
    
    # テストデータにマージ
    test_df['race_id'] = test_df['race_id'].astype(str)
    test_df = test_df.merge(raw_df, on=['race_id', '馬番'], how='left')
    
    # 期待値計算のためにオッズがNaNのものを除外
    test_df['オッズ'] = pd.to_numeric(test_df['オッズ'], errors='coerce')
    test_df = test_df.dropna(subset=['オッズ'])
    
    # 2. モデル用特徴量の抽出
    X_train = prepare_data(train_df, 'turf')
    X_test = prepare_data(test_df, 'turf')
    
    # 列の一致を確保
    common_cols = X_train.columns.intersection(X_test.columns)
    X_train = X_train[common_cols]
    X_test = X_test[common_cols]
    
    # 目的変数
    y_train_win = (train_df['着順'] == 1)
    y_train_place = (train_df['着順'] <= 3)
    
    # 欠損値補完 (高速化のため中央値で補完)
    print("Imputing missing values...")
    imputer = SimpleImputer(strategy='median')
    X_train_imputed = imputer.fit_transform(X_train)
    X_test_imputed = imputer.transform(X_test)
    
    # 3. モデル学習 (LightGBM)
    print("Training win model...")
    win_params = get_model_params('turf', 'win')
    model_win = lgb.LGBMClassifier(**win_params)
    model_win.fit(X_train_imputed, y_train_win)
    
    print("Training place model...")
    place_params = get_model_params('turf', 'place')
    model_place = lgb.LGBMClassifier(**place_params)
    model_place.fit(X_train_imputed, y_train_place)
    
    # 4. 2026年テストデータに対する推論
    print("Predicting probabilities for 2026 test data...")
    test_df['win_prob'] = model_win.predict_proba(X_test_imputed)[:, 1]
    test_df['place_prob'] = model_place.predict_proba(X_test_imputed)[:, 1]
    
    # 5. SQLiteデータベースから複勝配当をマージ (もしあれば)
    fukusho_payouts_map = {}
    db_path = 'predictions.db'
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT race_id, fukusho_payouts FROM payouts")
            for r_id, pay_json in cursor.fetchall():
                try:
                    fukusho_payouts_map[str(r_id)] = json.loads(pay_json)
                except Exception:
                    pass
            conn.close()
            print(f"Loaded {len(fukusho_payouts_map)} payout records from database.")
        except Exception as e:
            print(f"Warning: failed to load sqlite payouts: {e}")
            
    # 複勝回収率の計算用配当列を追加
    def get_fukusho_payout(row):
        r_id = str(row['race_id'])
        umaban_str = str(int(row['馬番']))
        if r_id in fukusho_payouts_map:
            payout_dict = fukusho_payouts_map[r_id]
            if umaban_str in payout_dict:
                return payout_dict[umaban_str]
        # なければ、実際の着順が3以内なら簡易で 1.2倍程度、あるいはオッズに比例した値を入れる（簡易計算）
        if row['着順'] <= 3:
            odds = row['オッズ']
            if pd.isna(odds) or odds <= 0:
                return 120
            return max(110, int(odds * 100 * 0.3)) # 簡易的な複勝配当推算
        return 0
        
    test_df['fukusho_payout'] = test_df.apply(get_fukusho_payout, axis=1)
    
    # 期待値の計算 (勝率 × オッズ)
    test_df['win_ev'] = test_df['win_prob'] * test_df['オッズ']
    
    # シミュレーション用のデータフレームを整理
    sim_df = test_df[['race_id', '馬番', 'オッズ', '人気', '着順', 'win_prob', 'place_prob', 'win_ev', 'fukusho_payout']].copy()
    
    # 6. シミュレーションの実行
    # 抽出条件: 予測勝率 (win_prob) >= 10%
    base_cond = sim_df['win_prob'] >= 0.10
    
    print("\n==================================================================")
    print("   単勝予測確率 >= 10% 固定時の、予測複勝率しきい値ごとの成績比較")
    print("==================================================================")
    print(f"{'複勝率しきい値':<10} | {'購入馬数':<6} | {'単勝的中率':<6} | {'単勝回収率':<6} | {'複勝的中率':<6} | {'複勝回収率':<6}")
    print("-" * 75)
    
    # スイープするしきい値
    place_thresholds = [0.0, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    
    for th in place_thresholds:
        # 条件適用
        sel = sim_df[base_cond & (sim_df['place_prob'] >= th)]
        bets = len(sel)
        
        if bets == 0:
            print(f"{th*100:4.1f}%以上     | {'0':<6} | {'-':<6} | {'-':<6} | {'-':<6} | {'-':<6}")
            continue
            
        win_hits = (sel['着順'] == 1).sum()
        win_hit_rate = win_hits / bets * 100
        
        # 単勝配当: 1着ならオッズ * 100、それ以外は 0
        win_payouts = np.where(sel['着順'] == 1, sel['オッズ'] * 100, 0).sum()
        win_return_rate = win_payouts / (bets * 100) * 100
        
        place_hits = (sel['着順'] <= 3).sum()
        place_hit_rate = place_hits / bets * 100
        
        # 複勝配当
        place_payouts = sel['fukusho_payout'].sum()
        place_return_rate = place_payouts / (bets * 100) * 100
        
        print(f"{th*100:4.1f}%以上     | {bets:<8d} | {win_hit_rate:5.1f}% | {win_return_rate:5.1f}% | {place_hit_rate:5.1f}% | {place_return_rate:5.1f}%")

    print("==================================================================")
    
    # 追加分析: 期待値が 1.2 以上かつ予測勝率 >= 10% の馬において、複勝率を閾値にした場合
    print("\n==================================================================")
    print("   【期待値 1.2 以上 かつ 勝率 >= 10%】時の、予測複勝率しきい値ごとの成績")
    print("==================================================================")
    print(f"{'複勝率しきい値':<10} | {'購入馬数':<6} | {'単勝的中率':<6} | {'単勝回収率':<6} | {'複勝的中率':<6} | {'複勝回収率':<6}")
    print("-" * 75)
    
    base_ev_cond = (sim_df['win_prob'] >= 0.10) & (sim_df['win_ev'] >= 1.20)
    
    for th in place_thresholds:
        sel = sim_df[base_ev_cond & (sim_df['place_prob'] >= th)]
        bets = len(sel)
        if bets == 0:
            print(f"{th*100:4.1f}%以上     | {'0':<6} | {'-':<6} | {'-':<6} | {'-':<6} | {'-':<6}")
            continue
        win_hits = (sel['着順'] == 1).sum()
        win_hit_rate = win_hits / bets * 100
        win_payouts = np.where(sel['着順'] == 1, sel['オッズ'] * 100, 0).sum()
        win_return_rate = win_payouts / (bets * 100) * 100
        
        place_hits = (sel['着順'] <= 3).sum()
        place_hit_rate = place_hits / bets * 100
        place_payouts = sel['fukusho_payout'].sum()
        place_return_rate = place_payouts / (bets * 100) * 100
        
        print(f"{th*100:4.1f}%以上     | {bets:<8d} | {win_hit_rate:5.1f}% | {win_return_rate:5.1f}% | {place_hit_rate:5.1f}% | {place_return_rate:5.1f}%")
    print("==================================================================")

if __name__ == '__main__':
    main()
