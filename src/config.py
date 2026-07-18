# C:\KeibaAI\config.py (最終確定版)

import os
import ast # このファイル内で関数を使うため、astを再度インポート

# --- プロジェクトパス設定 ---
# このconfig.pyファイル自身があるディレクトリをプロジェクトのルートとする
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# データベースの保存先を 'C:\KeibaAI\predictions.db' に変更
DB_PATH = os.path.join(PROJECT_ROOT, 'predictions.db')
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
RAW_DATA_DIR = os.path.join(DATA_DIR, 'raw')
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, 'processed')

ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
MODEL_DIR_BASE = os.path.join(PROJECT_ROOT, 'models')
TUNING_RESULTS_DIR = os.path.join(PROCESSED_DATA_DIR, 'tuning_results')
ENCODED_DIR = os.path.join(PROCESSED_DATA_DIR, 'encoded')
FEATURE_SELECTION_DIR = os.path.join(PROCESSED_DATA_DIR, 'feature_selection')
SHAP_RESULTS_DIR = os.path.join(PROCESSED_DATA_DIR, 'shap_results')
PREDICT_DATA_DIR = os.path.join(PROJECT_ROOT, 'predict_data')

WEBAPP_EXPORTS_DIR = os.path.join(PROJECT_ROOT, 'webapp_exports')

# --- 期間設定 & バージョン管理 ---
EXPERIMENT_VERSION = "v03_rap"
SCRAPE_START_YEAR = 1990
SCRAPE_END_YEAR = 2027
BUILD_START_YEAR = 1990
BUILD_END_YEAR = 2027
TRAINING_START_YEAR = 1993
EVALUATION_YEAR = 2026
JOCKEY_RATE_BUILD_END_YEAR = 2026
JOCKEY_RATE_TERM = 5       # 騎手勝率などを計算する期間 (直近N年) - 衰えや調子を反映させるため
VECTOR_DB_START_YEAR = 2016 # 過去10年以上の傾向分析用

# --- 自動投票設定 ---
AUTO_VOTING_MAX_HORSES_PER_RACE = 1

# ヘルパー関数をこのファイル内に戻す
def load_best_params_from_file(filepath: str) -> dict:
    """Optunaのスタディ結果のようなテキストファイルから最適なパラメータを読み込む。"""
    if not os.path.exists(filepath):
        # print(f"[WARN] Hyperparameter file not found: {filepath}. Returning empty dict.")
        return {}
    params = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if "Best params:" in line: break
            for line in f:
                line = line.strip()
                if not line.startswith("'"): continue
                key, value = line.split(':', 1)
                key = ast.literal_eval(key)
                value = ast.literal_eval(value.rstrip(','))
                params[key] = value
    except Exception as e:
        print(f"[ERROR] Failed to parse hyperparameter file {filepath}: {e}")
        return {}
    return params



# --- LightGBM ハイパーパラメータ設定 ---
LGB_BASE_PARAMS = {
    "objective": "binary", "metric": "auc", "verbosity": -1, 
    "boosting_type": "gbdt", "class_weight": "balanced"
}

# 2026年テスト年において最高予測精度(AUC)を達成した確定最良ハイパーパラメータ（Pruning適用済み）
LGB_PARAMS_WIN_TURF = {
    **LGB_BASE_PARAMS,
    'num_leaves': 96,
    'max_depth': 17,
    'learning_rate': 0.0289467638660008,
    'n_estimators': 900,
    'min_child_samples': 5,
    'lambda_l1': 9.00876774827701,
    'lambda_l2': 6.297738171604734e-06,
}

LGB_PARAMS_PLACE_TURF = {
    **LGB_BASE_PARAMS,
    'num_leaves': 268,
    'max_depth': 16,
    'learning_rate': 0.027934246540934144,
    'n_estimators': 700,
    'min_child_samples': 90,
    'lambda_l1': 4.90865936564065,
    'lambda_l2': 2.7606911824111887e-08,
}

LGB_PARAMS_WIN_DIRT = {
    **LGB_BASE_PARAMS,
    'num_leaves': 123,
    'max_depth': 12,
    'learning_rate': 0.04295620005967905,
    'n_estimators': 250,
    'min_child_samples': 41,
    'lambda_l1': 2.769323181014847e-05,
    'lambda_l2': 3.398336036999812e-05,
}

LGB_PARAMS_PLACE_DIRT = {
    **LGB_BASE_PARAMS,
    'num_leaves': 112,
    'max_depth': 10,
    'learning_rate': 0.047070854425421846,
    'n_estimators': 350,
    'min_child_samples': 72,
    'lambda_l1': 6.62635941486578e-08,
    'lambda_l2': 0.8544336932691985,
}


# --- 特徴量エンジニアリング設定 ---
TRACK_TYPES = ['turf', 'dirt']
NUM_PAST_RACES = 5
PAST_RACE_FEATURES = [
    '馬番', 'jockey_id', '斤量', 'オッズ', '人気', '体重', '体重変化', '頭数', 
    '上がり', '通過順', '着順', '距離', 'クラス', 
    '走破時間_seconds', 
    '走破時間_scaled', 
    '芝・ダート', '天気', '馬場',
    '脚質', '賞金', 'is_jra',
    # 新規追加: ラップタイム解析特徴量
    'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
    'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
    'pace_volatility', 'pace_trend',
    # 新規追加: コース物理特徴量
    'コース直線距離', 'コース勾配', 'コース一周距離', 'コース幅員'
]

# --- モデル設定 (Single Model Versioning) ---
LEAKAGE_FEATURES = [
    '賞金', '通過順', '上がり', '走破時間_scaled', '走破時間_seconds',
    "ペース", '脚質', '通過順_平均', "通過順_変動",
    'ポジションスコア', '芝ダート脚質適性',
    '平均ポジションスコア',
    # 新規取得データ (文字列のため除外)
    'lap_times', 'race_pace', 'corner_passage_text',
    # 新規生成特徴量 (予測時は現在のレースのものはリークになるので除外。過去走分は残す)
    'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
    'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
    'pace_volatility', 'pace_trend'
]

CATEGORICAL_FEATURES = [
    'レース名', '開催', '場名', '脚質', '体重増減カテゴリ', '馬番グループ', '想定脚質', 
    *[f'脚質{i}' for i in range(1, NUM_PAST_RACES + 1)]
]

STATS_TO_SAVE = [
    'jockey_rate', 'jockey_venue_rate', 'horse_weight_stats', 'weight_change_suitability', 
    'track_running_style_suitability', 'jockey_track_suitability', 'venue_bias_by_gate_group',
    'track_bias_map',
    'trainer_rate', 'trainer_venue_rate', 'owner_rate'
]

# --- 実験設定 (Experiment Settings) ---
# ★ここで実験タイプを切り替えます★
# 'baseline'   : ベースライン (ラップタイム特徴量・コース物理特徴量を両方除外)
# 'coursedata' : コースデータ実験 (ラップタイム特徴量のみ除外)
# 'laptime'    : ラップタイム実験 (全特徴量を使用)
EXPERIMENT_TYPE = 'laptime' 

# --- 特徴量削除設定の定義 ---
# 新規特徴量グループ定義
_LAP_FEATURES = [
    'lap_cnt_super_fast', 'lap_cnt_fast', 'lap_cnt_normal_fast',
    'lap_cnt_normal_slow', 'lap_cnt_slow', 'lap_cnt_super_slow',
    'pace_volatility', 'pace_trend'
]
_COURSE_FEATURES = ['コース直線距離', 'コース勾配', 'コース一周距離', 'コース幅員']

# 過去走特徴量名も含めて削除リストを作るヘルパー
def _get_past_features(base_features):
    past_feats = []
    for f in base_features:
        for i in range(1, NUM_PAST_RACES + 1):
             past_feats.append(f'{f}{i}')
    return base_features + past_feats

_DROP_DEFINITIONS = {
    # 共通削除 (常に削除するもの)
    'common': [
         '調教師', 'trainer_id','馬主', 'owner_id', "厩舎", 'オッズ',  '人気', 
         "芝・ダート", "馬", "出走頭数", "クラス", 
    ],
    
    # 初期モデル
    'baseline': _get_past_features(_COURSE_FEATURES) + _get_past_features(_LAP_FEATURES),

    # コースの物理的特徴を追加したモデル
    'coursedata': _get_past_features(_LAP_FEATURES),

    # ラップタイムから新しい特徴量を追加したモデル
    'laptime': []
}

# 実際に使用される削除設定 (FEATURES_TO_DROP)
# 実際に使用される削除設定 (FEATURES_TO_DROP)
FEATURES_TO_DROP = {
    'common': _DROP_DEFINITIONS['common'] + _DROP_DEFINITIONS.get(EXPERIMENT_TYPE, []),
    'turf': [
        'is_jra',
        'is_niigata_1000m',
        '体重増減カテゴリ',
        '長期休養明けフラグ',
        '体重変化適性', # Feature Selection 2025-12-19
    ],
    'dirt': [
        '回り',
        '馬場',
        '天気',
        'is_jra',
        '天気1',
        'lap_cnt_fast1',
        'lap_cnt_normal_fast1',
        '距離2',
        '天気2',
        '馬場2',
        'lap_cnt_super_fast2',
        'lap_cnt_fast2',
        'lap_cnt_normal_fast2',
        'lap_cnt_slow2',
        'lap_cnt_super_slow2',
        'コース勾配2',
        'コース幅員2',
        '馬番3',
        '斤量3',
        '天気3',
        'lap_cnt_super_fast3',
        'lap_cnt_fast3',
        'lap_cnt_normal_fast3',
        'lap_cnt_slow3',
        'pace_volatility3',
        'コース幅員3',
        '馬番4',
        '天気4',
        '馬場4',
        '脚質4',
        '賞金4',
        'lap_cnt_super_fast4',
        'lap_cnt_fast4',
        'lap_cnt_normal_fast4',
        'lap_cnt_slow4',
        'コース直線距離4',
        'コース勾配4',
        'ポジションスコア4',
        '天気5',
        'lap_cnt_super_fast5',
        'lap_cnt_fast5',
        'lap_cnt_slow5',
        '長期休養明けフラグ',
        '過去5走_通過順_変動_最小',
        '過去5走_賞金_最小',
        '過去5走_条件_走破時間_scaled_標準偏差',
        '体重変化適性',
        '騎手勝率_race_min',
        '過去5走_条件_走破時間_scaled_平均_race_min',
        '過去5走_条件_走破時間_scaled_最大_race_min',
        'is_niigata_1000m',
    ],
    
    # ターゲット別の詳細な不要特徴量 (Zero importance)
    'turf_win': [
        '枠番', 'is_jra1', 'is_jra2', 'is_jra4', 'is_jra5', 'レース_脚質不明数', '過去走数'
    ],
    'turf_place': [
        '斤量', '馬場', '天気', '場名', '枠番', 'コース勾配', '馬番グループ', '天気1', '馬場1', 'is_jra1',
        'lap_cnt_fast1', 'lap_cnt_normal_fast1', 'lap_cnt_normal_slow1', 'lap_cnt_slow1', 'lap_cnt_super_slow1',
        'コース勾配1', '斤量2', '通過順_平均2', '通過順_変動2', '天気2', '馬場2', 'is_jra2', 'lap_cnt_super_fast2',
        'lap_cnt_fast2', 'lap_cnt_normal_fast2', 'lap_cnt_slow2', 'lap_cnt_super_slow2', 'pace_volatility2',
        '斤量3', '体重3', '体重変化3', '通過順_変動3', '天気3', '馬場3', '賞金3', 'is_jra3', 'lap_cnt_super_fast3',
        'lap_cnt_fast3', 'lap_cnt_normal_fast3', 'lap_cnt_normal_slow3', 'lap_cnt_slow3', 'lap_cnt_super_slow3',
        'コース直線距離3', 'コース勾配3', 'コース一周距離3', 'ポジションスコア3', '馬番4', 'jockey_id4', '斤量4',
        '体重変化4', '上がり4', '通過順_平均4', '通過順_変動4', '距離4', '走破時間_seconds4', '天気4', '馬場4',
        '脚質4', 'is_jra4', 'lap_cnt_super_fast4', 'lap_cnt_fast4', 'lap_cnt_normal_fast4', 'lap_cnt_normal_slow4',
        'lap_cnt_slow4', 'lap_cnt_super_slow4', 'コース直線距離4', 'コース勾配4', 'ポジションスコア4', '馬番5',
        '上がり5', '通過順_平均5', '走破時間_scaled5', '天気5', '馬場5', '賞金5', 'is_jra5', 'lap_cnt_super_fast5',
        'lap_cnt_fast5', 'lap_cnt_normal_fast5', 'lap_cnt_slow5', 'コース勾配5', 'ポジションスコア5',
        '過去5走_通過順_平均_標準偏差', '過去5走_賞金_最小', '過去5走_賞金_標準偏差', '過去5走_条件_走破時間_scaled_平均',
        '過去5走_条件_走破時間_scaled_EMA', '想定脚質', 'レース_逃げ馬数', 'レース_脚質不明数', '斤量_race_min',
        '騎手勝率_race_min', '過去5走_条件_走破時間_scaled_平均_race_mean', '過去5走_条件_走破時間_scaled_平均_race_min',
        '過去5走_条件_走破時間_scaled_平均_race_min_diff', '過去5走_条件_走破時間_scaled_最小_race_min',
        '過去5走_条件_走破時間_scaled_最小_race_min_diff'
    ],
    'dirt_win': [
        '馬番グループ', '体重増減カテゴリ', '体重変化3', '脚質3', 'lap_cnt_super_slow3', 'コース直線距離3',
        '人気4', '上がり4', 'pace_volatility4', 'pace_trend4', 'コース幅員4', '体重変化5', '頭数5',
        '通過順_変動5', '馬場5', '脚質5', 'lap_cnt_super_slow5', 'コース勾配5', 'レース_脚質不明数'
    ],
    'dirt_place': [
        '枠番', '馬番1', '通過順_変動1', '馬場1', 'lap_cnt_super_fast1', 'lap_cnt_normal_slow1',
        'lap_cnt_slow1', 'lap_cnt_super_slow1', 'コース勾配1', 'コース幅員1', '斤量2', '人気2',
        '体重2', '体重変化2', '上がり2', '通過順_平均2', '通過順_変動2', '脚質2', 'is_jra2',
        'lap_cnt_normal_slow2', 'pace_trend2', '人気3', '通過順_変動3', '着順3', '馬場3', '賞金3',
        'is_jra3', 'lap_cnt_normal_slow3', 'コース勾配3', '体重変化4', '通過順_平均4', '通過順_変動4',
        'is_jra4', 'lap_cnt_normal_slow4', 'lap_cnt_super_slow4', '馬番5', '上がり5', '通過順_平均5',
        '着順5', '距離5', 'lap_cnt_normal_slow5', 'pace_volatility5', 'pace_trend5', 'コース直線距離5',
        'コース一周距離5', '想定脚質', 'レース_脚質不明数', '斤量_race_min', '騎手勝率_race_min_diff',
        '過去5走_上がり_平均_race_min', '過去5走_条件_走破時間_scaled_最大_race_dev',
        '過去5走_条件_走破時間_scaled_最小_race_min_diff'
    ]
}


# --- その他 ---
PLACE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"
}

# --- 通知設定 ---
import os
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1472550601547321576/kBJTclsdJkgJYD49Mtb774BAk-I414dqEwC_1G5RT_coD6_TNQfDbtbkfRWNQssLeyUX")
DISCORD_EV_WEBHOOK_URL = os.getenv("DISCORD_EV_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1472605057978732665/F0E4xl9QGZPOmEjhKpS5YcfF2G6QzuVawAbGq-T2qbbG0AlFvvo57fRNsShfZVQZjw6I")
DISCORD_VOTE_WEBHOOK_URL = os.getenv("DISCORD_VOTE_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1510275670905983109/vvR6Sc-TUjxykaJRPDO-el8PEV1fJfuyCcRF3SKP_FrjbvUD_C4SoXikn8MbONvOYvF3")
DISCORD_REPORT_WEBHOOK_URL = os.getenv("DISCORD_REPORT_WEBHOOK_URL")
DISCORD_NOTIFY_MAX_HORSES = 18 # 通知に含める馬の数 (全頭送る場合は18などの最大値を設定)

# --- 予測・馬券戦略設定 ---
TARGET_EV = 1.3         # ターゲット期待値 (ベースデフォルト値)
TARGET_EV_5MIN = 1.2     # 5分前足切り期待値しきい値 (仮選定)
TARGET_EV_VOTE = 1.3     # 投票確定期待値しきい値 (本投票)
MIN_WIN_PROB = 0.10     # 最低勝率の閾値
EV_SAFETY_MARGIN = 0  # 期待値の安全マージン

# --- 自動投票（Auto-Voting）設定 ---
AUTO_VOTING_ENABLED = True          # 自動投票機能のON/OFFフラグ
AUTO_VOTING_MODE = "umaca"            # 動作モード ("mock": 平日模擬投票, "umaca": 本番UMACAスマート投票)
AUTO_VOTING_BET_TYPE = "win"         # 購入馬券のデフォルト種類 ('win': 単勝)
AUTO_VOTING_BASE_AMOUNT = 100        # 1点あたりの基本購入金額 (円)
AUTO_VOTING_MAX_AMOUNT_PER_RACE = 100 # 1レースあたりの最大投資上限額
AUTO_VOTING_MAX_HORSES_PER_RACE = 1  # 1レースあたりの最大購入頭数
AUTO_VOTING_MAX_AMOUNT_PER_DAY = 3000  # 1日の最大投票予算 (円)。Noneまたは0で朝一の投票専用残高Aを自動上限とし、数値を設定すると手動上限になります。

# --- スケジューラー＆投票タイミング設定 ---
PREDICTION_TIMING_MINUTES = 50  # 発走の何分前に予測を開始するか
ODDS_NOTIFY_TIMING_MINUTES = 5  # 発走の何分前にオッズ取得・通知を行うか
AUTO_VOTE_TIMING_MINUTES = 3    # 発走の何分前に自動投票を行うか（本投票）

# --- オッズ制御設定（予算管理）---
AUTO_VOTING_MAX_ODDS = 30.0          # 購入オッズの上限（30倍超は現データで0的中のため除外）
AUTO_VOTING_MIN_ODDS = 2.0           # 購入オッズの下限（AI勝率最大25%×2倍=EV0.5なので実質引っかからない）
AUTO_VOTING_MAX_BETS_PER_DAY = 30   # 1日あたりの最大購入点数（月2万円÷8開催日÷100円=25点が上限、余裕を持たせ25点）
# JRAの競馬場IDマッピング (race_idの4-6桁目)
PLACE_MAP_IDS = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"
}

# JRAの競馬場名 (場名からJRAを判定するため)
JRA_PLACE_NAMES = set([
    "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"
])

# 過去走特徴量を生成する際の過去レース数
NUM_PAST_RACES = 5 
# 個別ページからスクレイピングする過去走の最大数 (少し多めに取得)
NUM_PAST_RACES_TO_SCRAPE = 10 
# --- 予測モデル設定 (新設) ---
# --- 予測モデル設定 (単一モデル構成) ---
MODEL_FILE_TEMPLATE = "lgb_model_{track}_{target_type}.txt"
IMPUTER_FILE_TEMPLATE = "imputer_{track}_{target_type}.joblib"
# 使用するパラメータファイル（学習時に生成されるもの）
PARAMS_FILE_TEMPLATE = "best_params_lgbm_{track}_{target_type}.txt"

