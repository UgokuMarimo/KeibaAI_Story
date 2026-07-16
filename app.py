"""
🐎 KeibaAI 統合ダッシュボード (app.py)

■ 概要
  本スクリプトは、競馬予測AIシステムの統合管理ダッシュボード（Web UI）です。
  予測スコアの確認、AIによるレース・出走馬解説の生成、過去走データを用いた回収率分析、
  およびGemini/ベクトルDBを統合した競馬AIチャット（RAG）を直感的に操作できます。

■ 起動方法
  ターミナルで仮想環境（.venv）を有効化し、以下のコマンドを実行してください。
  
  streamlit run app.py

  ※ 自動的にブラウザが起動し、ダッシュボード画面（デフォルトでは http://localhost:8501）が開きます。

■ 主要機能
  1. 🔮 リアルタイム予測  : カレンダーからのレース選択、AI勝率予測、AI解説（Gemini）と要因分析（SHAP）、期待値ダッシュボード
  2. 📈 回収率実績分析    : 過去の予測と確定結果を用いた馬券シミュレーション・回収率ビジュアル分析
  3. 🤖 競馬AIチャット    : 過去走やレース分析のベクトルデータをRAGとして用いたGeminiチャット
  4. ⚙️ システム管理・更新: データベース状態の可視化、レース確定結果と払い戻しの手動・自動同期
"""
import streamlit as st
import os
import sys
import json
import subprocess
import chromadb
import google.generativeai as genai
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, date
from dotenv import load_dotenv
import plotly.graph_objects as go
import time

# --- プロジェクトパス設定 ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# .envファイルの読み込み
load_dotenv()

import src.config # 設定ファイルの読み込み

# --- モジュールインポート ---
try:
    from explanation.explanation_templates import EXPLANATION_TEMPLATES, get_original_value_display, get_feature_name_display, get_group_for_feature
    from utils import analytics
    from utils.schedule_scraper import get_race_schedule_for_date, get_monthly_schedule_metadata
    from utils.scraper import scrape_shutuba_table
    from prediction.predict import predict_race, load_models
except ImportError as e:
    st.error(f"インポートエラー: {e}")
    try:
        from explanation.explanation_templates import EXPLANATION_TEMPLATES, get_original_value_display, get_feature_name_display
        import src.utils.analytics as analytics
    except ImportError:
        pass

# App Components
try:
    from app_components.analytics_view import render_recovery_analysis
except ImportError as e:
    def render_recovery_analysis(db_path, project_root):
        st.error(f"回収率分析モジュールの読み込みに失敗しました。\n\n原因: {e}")

try:
    from app_components.calendar_view import render_schedule_html
    from explanation.explanation_view import render_ai_explanation
except ImportError as e:
    pass

EMBEDDING_MODEL = "models/text-embedding-004"
GENERATION_MODEL = "gemini-2.5-flash"
DB_PATH = os.path.join(PROJECT_ROOT, 'predictions.db')
BET_AMOUNT = 100

# --- Streamlit UI初期設定 ---
st.set_page_config(page_title="KeibaAI 統合ダッシュボード", layout="wide", initial_sidebar_state="expanded")

# --- プレミアムダークテーマ・カスタムCSS ---
st.markdown("""
    <style>
    /* 全体背景とフォントの設定 */
    .stApp {
        background-color: #0d0f12;
        color: #e2e8f0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* ヘッダー・グラデーションタイトル */
    .main-title {
        background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.2rem;
        margin-bottom: 0.2rem;
        text-align: left;
    }
    
    .subtitle {
        color: #718096;
        font-size: 1.0rem;
        margin-bottom: 1.5rem;
    }

    /* ガラスモーフィズム・カードスタイル */
    .custom-card {
        background: rgba(22, 29, 39, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    
    .custom-card-header {
        font-weight: 700;
        font-size: 1.15rem;
        color: #00f2fe;
        margin-bottom: 0.8rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* レース選択用のNetkeiba風グリッドカード */
    .race-grid-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(0, 242, 254, 0.15);
        border-radius: 8px;
        padding: 0.8rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .race-grid-card:hover {
        border-color: #00f2fe;
        background: rgba(30, 41, 59, 0.9);
        transform: translateY(-2px);
    }

    /* 予測マーク（印）の装飾バッジ */
    .badge-mark {
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        font-weight: 800;
        font-size: 0.85rem;
        display: inline-block;
        text-align: center;
    }
    .badge-honmei { background-color: #e53e3e; color: white; } /* ◎ */
    .badge-taiko { background-color: #dd6b20; color: white; } /* ○ */
    .badge-tanana { background-color: #3182ce; color: white; } /* ▲ */
    .badge-renka { background-color: #319795; color: white; } /* △ */

    /* 文字サイズ調整 */
    .stMarkdown h1 { font-size: 1.8rem !important; }
    .stMarkdown h2 { font-size: 1.4rem !important; }
    .stMarkdown h3 { font-size: 1.15rem !important; margin-top: 0.5em !important; margin-bottom: 0.2em !important; }
    .stMarkdown p { font-size: 0.95rem !important; }
    
    /* アコーディオン・拡張エリア */
    .stExpander {
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        background-color: rgba(22, 29, 39, 0.4) !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- データベース・モデルのロード処理 ---
@st.cache_resource
def load_vector_db():
    vector_db_path = os.path.join(PROJECT_ROOT, "vector_db")
    if not os.path.exists(vector_db_path):
        return None
    try:
        client = chromadb.PersistentClient(path=vector_db_path)
        return client.get_collection(name="race_results")
    except Exception as e:
        return None

collection = load_vector_db()

def get_shap_dir(race_id):
    race_id_str = str(race_id)
    if len(race_id_str) == 12:
        year = race_id_str[:4]
        course = race_id_str[4:6]
        kaisai = race_id_str[6:8]
        nissuu = race_id_str[8:10]
        race_num = race_id_str[10:]
        return os.path.join(src.config.SHAP_RESULTS_DIR, year, course, kaisai, nissuu, race_num)
    else:
        return os.path.join(src.config.SHAP_RESULTS_DIR, race_id_str)

@st.cache_resource(show_spinner="予測モデルを読み込んでいます...")
def get_cached_models():
    try:
        models, artifacts = load_models()
        return models, artifacts, None
    except TypeError:
        models, artifacts, model_conf = load_models('B')
        return models, artifacts, model_conf

# --- ナビゲーションメニュー（サイドバー） ---
st.sidebar.markdown("<h2 style='color:#00f2fe;font-weight:800;font-size:1.4rem;margin-bottom:1rem;'>🏁 KeibaAI Menu</h2>", unsafe_allow_html=True)
page = st.sidebar.radio(
    "画面の切り替え",
    ["🔮 リアルタイム予測", "📈 回収率実績分析", "🤖 競馬AIチャット (RAG)", "⚙️ システム管理・更新"],
    index=0
)

# 予測設定
if page == "🔮 リアルタイム予測":
    st.sidebar.markdown("---")
    st.sidebar.markdown("<h3 style='font-size:1.0rem;'>⚙️ 予測オプション</h3>", unsafe_allow_html=True)
    send_discord_notification = st.sidebar.checkbox("Discordに結果を通知する", value=True)
else:
    send_discord_notification = True

# --- 1. 🔮 リアルタイム予測画面 ---
if page == "🔮 リアルタイム予測":
    st.markdown('<div class="main-title">🔮 リアルタイムレース予測</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">今日・過去の開催レースの日程選択、AI予測の実行、勝率解説および要因分析</div>', unsafe_allow_html=True)

    # クエリパラメータ同期
    query_params = st.query_params
    if "date" in query_params:
        p_date = query_params["date"]
        p_venue = query_params.get("venue", "ALL")
        if (st.session_state.get("selected_date_str") != p_date or st.session_state.get("selected_venue") != p_venue):
            st.session_state["selected_date_str"] = p_date
            st.session_state["selected_venue"] = p_venue
            try:
                st.session_state["selected_date"] = datetime.strptime(p_date, "%Y-%m-%d").date()
            except ValueError:
                pass
            st.session_state['selected_race_id'] = None
            st.rerun()

    # タブ設定 (スケジュール ＆ EVダッシュボード)
    tab_pred, tab_ev = st.tabs(["📅 開催スケジュール ＆ レース選択", "📊 期待値分析ダッシュボード"])

    with tab_ev:
        try:
            from src.utils import analytics
            analytics.render_ev_dashboard(DB_PATH)
        except Exception as e:
            st.error(f"期待値分析ダッシュボードの表示に失敗しました: {e}")

    with tab_pred:
        # スケジュール選択用のカードレイアウト
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown('<div class="custom-card-header">📅 開催スケジュールの指定</div>', unsafe_allow_html=True)
        
        col_year, col_month, col_manual = st.columns([1, 1, 2])
        today = date.today()
        with col_year:
            selected_year = st.selectbox("対象年", range(today.year - 1, today.year + 2), index=1)
        with col_month:
            selected_month = st.selectbox("対象月", range(1, 13), index=today.month - 1)
        with col_manual:
            manual_date = st.date_input("特定日付を指定", value=None)
            if manual_date:
                st.session_state["selected_date_str"] = str(manual_date)
                st.session_state["selected_venue"] = "ALL"

        col_force, _ = st.columns([1, 3])
        with col_force:
            if st.button("🔄 開催スケジュールの強制再取得"):
                get_monthly_schedule_metadata(selected_year, selected_month, force_reload=True)
                st.success("開催スケジュールを再取得しました。")
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        @st.cache_data(ttl=3600*24, show_spinner="月間スケジュールを読み込み中...")
        def get_cached_monthly_schedule(year, month):
            return get_monthly_schedule_metadata(year, month)

        @st.cache_data(ttl=3600*12, show_spinner="日付ごとのレース情報をロード中...")
        def get_cached_schedule(date_obj):
            return get_race_schedule_for_date(date_obj)

        monthly_schedule = get_cached_monthly_schedule(selected_year, selected_month)
        
        # HTMLカレンダー表示
        html_content = render_schedule_html(selected_year, selected_month, monthly_schedule)
        st.markdown(html_content, unsafe_allow_html=True)

        # レース一覧表示
        if "selected_date_str" in st.session_state and "selected_venue" in st.session_state:
            date_str = st.session_state["selected_date_str"]
            target_venue = st.session_state["selected_venue"]
            
            st.markdown(f"<h3 style='margin-top:2rem;'>🏇 {date_str} レース一覧 ({'全開催場' if target_venue == 'ALL' else target_venue})</h3>", unsafe_allow_html=True)
            
            try:
                target_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                st.error(f"日付形式エラー: {date_str}")
                target_date_obj = None

            if target_date_obj:
                schedule_df = get_cached_schedule(target_date_obj)
                
                if schedule_df is not None and not schedule_df.empty:
                    if target_venue == "ALL":
                        venue_races = schedule_df.copy()
                    else:
                        venue_races = schedule_df[schedule_df['venue_name'] == target_venue].copy()

                    # 一括予測アコーディオン
                    with st.expander("🚀 複数レースの一括予測 (Batch Prediction)", expanded=False):
                        all_races_label = venue_races.apply(lambda x: f"{x['venue_name']} {x['race_number']}R ({x['race_name'] or '名無し'})", axis=1).tolist()
                        race_id_map = {f"{x['venue_name']} {x['race_number']}R ({x['race_name'] or '名無し'})": x['race_id'] for _, x in venue_races.iterrows()}
                        
                        col_sel_all, _ = st.columns([1, 3])
                        with col_sel_all:
                            if st.button("全選択"):
                                st.session_state['batch_race_selector'] = all_races_label
                        
                        selected_labels = st.multiselect("対象レースを選択", all_races_label, key="batch_race_selector")
                        enable_explanation = st.checkbox("AIによる詳細なレース解説も生成する (処理時間が増加します)", value=False)
                        
                        if st.button("選択したレースをまとめて予測", type="primary"):
                            if not selected_labels:
                                st.warning("予測対象のレースを選択してください。")
                            else:
                                selected_ids = [race_id_map[label] for label in selected_labels]
                                st.info(f"{len(selected_ids)} レースの一括予測を開始しました...")
                                
                                script_path = os.path.join(PROJECT_ROOT, 'src', 'prediction', 'batch_predict.py')
                                cmd = [sys.executable, script_path, '--race_ids', ",".join(selected_ids)]
                                if enable_explanation:
                                    cmd.append('--explanation')
                                if not send_discord_notification:
                                    cmd.append('--no-discord')

                                with st.spinner("AI一括予測を実行中..."):
                                    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                                    if res.returncode == 0:
                                        st.success("一括予測が正常に完了しました！")
                                        with st.expander("実行ログ"):
                                            st.text(res.stdout)
                                        get_cached_schedule.clear()
                                        st.rerun()
                                    else:
                                        st.error("予測中にエラーが発生しました。")
                                        st.text(res.stderr)

                    # レース選択グリッド (Netkeiba風タブレイアウト)
                    if not venue_races.empty:
                        # 競馬場ごとにタブを分ける
                        venues = venue_races['venue_name'].unique()
                        venue_tabs = st.tabs(list(venues))
                        
                        for idx, v_name in enumerate(venues):
                            with venue_tabs[idx]:
                                group = venue_races[venue_races['venue_name'] == v_name].copy()
                                try:
                                    group['race_num_int'] = group['race_number'].astype(str).str.extract(r'(\d+)').astype(int)
                                    group = group.sort_values('race_num_int', ascending=True)
                                except:
                                    pass
                                
                                # グリッド表示
                                cols = st.columns(4)
                                for b_idx, (_, row) in enumerate(group.iterrows()):
                                    col = cols[b_idx % 4]
                                    r_id = str(row['race_id'])
                                    s_dir = get_shap_dir(r_id)
                                    is_pred = os.path.exists(os.path.join(s_dir, "prediction_summary.json"))
                                    
                                    # マーク付け
                                    btn_label = f"{row['race_number']}R | {row['start_time']} | {row['race_name'] or '名無し'}"
                                    if is_pred:
                                        btn_label = "✅ " + btn_label
                                        
                                    if col.button(btn_label, key=f"btn_r_{r_id}", use_container_width=True):
                                        st.session_state['selected_race_id'] = r_id
                                        st.rerun()
                else:
                    st.warning("指定された日付のスケジュール情報が存在しません。")

        # --- レース予測詳細ビュー ---
        if 'selected_race_id' in st.session_state and st.session_state['selected_race_id']:
            target_race_id = st.session_state['selected_race_id']
            st.markdown("---")
            st.markdown(f'<div class="custom-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="custom-card-header">🔮 予測情報表示 (ID: {target_race_id})</div>', unsafe_allow_html=True)
            
            # 自動ロード
            shap_dir = get_shap_dir(target_race_id)
            summary_path = os.path.join(shap_dir, "prediction_summary.json")
            
            if st.session_state.get('last_prediction_race_id') != target_race_id:
                loaded_df = None
                if os.path.exists(summary_path):
                    try:
                        with open(summary_path, 'r', encoding='utf-8') as f:
                            loaded_data = json.load(f)
                        rows = []
                        for item in loaded_data:
                            raw_score = item.get('pred_win') or item.get('pred_win_prob')
                            rows.append({
                                'pred_rank': item['pred_rank'],
                                '馬番': item['umaban'],
                                '馬名': item['horse_name'],
                                'pred_win': raw_score,
                                'tansho_odds': np.nan
                            })
                        loaded_df = pd.DataFrame(rows)
                    except:
                        pass

                # DBフォールバック
                if loaded_df is None and os.path.exists(DB_PATH):
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            db_df = pd.read_sql_query("SELECT * FROM predictions WHERE race_id = ?", conn, params=(str(target_race_id),))
                            if not db_df.empty:
                                db_df.rename(columns={'umaban': '馬番', 'horse_name': '馬名'}, inplace=True)
                                loaded_df = db_df
                    except:
                        pass
                
                if loaded_df is not None:
                    if 'pred_rank' in loaded_df.columns:
                        loaded_df = loaded_df.sort_values('pred_rank', ascending=True)
                    st.session_state['last_prediction_result'] = loaded_df
                    st.session_state['last_prediction_race_id'] = target_race_id
                    st.rerun()

            col_pred_run, _ = st.columns([1, 3])
            with col_pred_run:
                if st.button("🚀 このレースの予測・解説を生成する", type="primary", key="btn_run_single"):
                    with st.spinner('予測AI計算 ＆ SHAP・解説テキスト生成中...'):
                        models, artifacts, _ = get_cached_models()
                        res_df = predict_race(
                            race_id=str(target_race_id),
                            run_shap=True,
                            use_overseas=False,
                            enable_explanation=True,
                            models=models,
                            artifacts=artifacts,
                            send_discord=send_discord_notification,
                            realtime_odds=False
                        )
                        if res_df is not None and not res_df.empty:
                            if 'rank_win' in res_df.columns and 'pred_rank' not in res_df.columns:
                                res_df = res_df.rename(columns={'rank_win': 'pred_rank'})
                            if 'pred_rank' in res_df.columns:
                                res_df = res_df.sort_values('pred_rank', ascending=True)
                            st.session_state['last_prediction_result'] = res_df
                            st.session_state['last_prediction_race_id'] = target_race_id
                            st.success("予測完了！")
                            st.rerun()
                        else:
                            st.error("予測データの生成に失敗しました。")

            # 予測結果テーブル表示
            if 'last_prediction_result' in st.session_state and st.session_state.get('last_prediction_race_id') == target_race_id:
                result_df = st.session_state['last_prediction_result'].copy()
                
                # 実際の着順のロードと結合
                if os.path.exists(DB_PATH):
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            res_df = pd.read_sql_query("SELECT umaban, result_rank FROM predictions WHERE race_id = ?", conn, params=(str(target_race_id),))
                            if not res_df.empty:
                                res_df['umaban'] = res_df['umaban'].astype(str)
                                result_df['馬番'] = result_df['馬番'].astype(str)
                                result_df = pd.merge(result_df, res_df[['umaban', 'result_rank']], left_on='馬番', right_on='umaban', how='left')
                                result_df['確定着順'] = result_df['result_rank'].fillna('-')
                    except:
                        pass
                
                # 勝率の正規化
                if 'pred_win' in result_df.columns:
                    total_score = result_df['pred_win'].sum()
                    result_df['win_prob'] = (result_df['pred_win'] / total_score) if total_score > 0 else 0.0
                    result_df['勝率'] = result_df['win_prob'].apply(lambda x: f"{x*100:.1f}%")
                
                # 予測印バッジの追加
                def get_mark_badge(rank):
                    if rank == 1: return "◎ (本命)"
                    elif rank == 2: return "○ (対抗)"
                    elif rank == 3: return "▲ (単穴)"
                    elif rank == 4: return "△ (連下)"
                    return "-"
                
                result_df['AI印'] = result_df['pred_rank'].apply(get_mark_badge)
                
                # 表示用カラムの再整理
                display_cols = ['pred_rank', 'AI印', '馬番', '馬名', '勝率']
                if '確定着順' in result_df.columns:
                    display_cols.append('確定着順')
                
                st.markdown("#### 📊 予測期待度ランキング")
                st.dataframe(
                    result_df[display_cols],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "pred_rank": st.column_config.NumberColumn("順位"),
                        "AI印": "AI予想印",
                        "勝率": "勝率(シェア)"
                    }
                )

                # 各馬ごとのAI解説 ＆ SHAP 寄与度詳細
                st.markdown("---")
                st.markdown("#### 🏇 各出走馬の詳細AI解説 ＆ 要因分析")
                
                # 馬の選択ドロップダウン
                horse_list = result_df['馬名'].tolist()
                selected_horse = st.selectbox("解説を表示する馬を選択", horse_list)
                
                # 解説データの取得
                if os.path.exists(summary_path):
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        horses_data = json.load(f)
                    
                    target_horse_data = next((h for h in horses_data if h['horse_name'] == selected_horse), None)
                    
                    if target_horse_data:
                        col_exp, col_shap = st.columns([1, 1])
                        
                        with col_exp:
                            st.markdown(f"### 📝 {selected_horse} の解説（AI分析）")
                            if "explanation_rich" in target_horse_data:
                                for section in target_horse_data["explanation_rich"]:
                                    with st.expander(f"📌 {section['title']}", expanded=True):
                                        st.markdown(section['detail'])
                            elif "explanation" in target_horse_data:
                                st.markdown(target_horse_data["explanation"])
                            else:
                                st.info("解説テキストが生成されていません。")
                                
                        with col_shap:
                            st.markdown("### 🧠 評価スコアを分けた主な要因 (SHAP重要度)")
                            all_factors = target_horse_data.get('positive_factors', []) + target_horse_data.get('negative_factors', [])
                            all_factors = sorted(all_factors, key=lambda x: abs(x['shap_value']), reverse=True)
                            
                            TOP_N = 10
                            top_factors = all_factors[:TOP_N]
                            top_factors = top_factors[::-1] # 反転
                            
                            if top_factors:
                                features = [get_feature_name_display(f['feature']) for f in top_factors]
                                shap_values = [f['shap_value'] for f in top_factors]
                                colors = ['#e53e3e' if v < 0 else '#319795' for v in shap_values]
                                
                                fig = go.Figure(go.Bar(
                                    x=shap_values,
                                    y=features,
                                    orientation='h',
                                    marker=dict(color=colors)
                                ))
                                fig.update_layout(
                                    title=f"要因分析 TOP {TOP_N} (赤: マイナス / 緑: プラス)",
                                    yaxis=dict(dtick=1),
                                    height=400,
                                    margin=dict(l=10, r=10, t=30, b=10),
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0)',
                                    font=dict(color='#e2e8f0')
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("要因データが存在しません。")
                            
                            # 寄与度テーブル
                            with st.expander("📋 特徴量別寄与度の詳細一覧データ", expanded=False):
                                table_data = [{
                                    "特徴量名": get_feature_name_display(f['feature']),
                                    "SHAP貢献度": f"{f['shap_value']:.4f}",
                                    "特徴量の実際の値": str(f['value'])
                                } for f in all_factors]
                                st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

# --- 2. 📈 回収率実績分析画面 ---
elif page == "📈 回収率実績分析":
    st.markdown('<div class="main-title">📈 回収率実績分析</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">過去のAI予測と実際のレース確定データを元に、的中率・回収率のシミュレーションを行います。</div>', unsafe_allow_html=True)
    
    # 既存の分析モジュール呼び出し
    render_recovery_analysis(DB_PATH, PROJECT_ROOT)

# --- 3. 🤖 競馬AIチャット (RAG) 画面 ---
elif page == "🤖 競馬AIチャット (RAG)":
    st.markdown('<div class="main-title">🤖 競馬AIチャットアシスタント</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">ベクトルDBとGeminiを統合し、指定したレースや出走馬、競馬全般の傾向についてAIと自由に対話できます。</div>', unsafe_allow_html=True)

    # チャットのセッション・コンテキスト設定
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown('<div class="custom-card-header">⚙️ チャットコンテキストの指定</div>', unsafe_allow_html=True)
    
    # 最近予測されたレースIDの一覧を取得
    predicted_races = []
    if os.path.exists(src.config.SHAP_RESULTS_DIR):
        # 簡易走査
        for root, dirs, files in os.walk(src.config.SHAP_RESULTS_DIR):
            if "prediction_summary.json" in files:
                race_id = os.path.basename(root)
                if race_id.isdigit():
                    predicted_races.append(race_id)
    
    predicted_races = sorted(list(set(predicted_races)), reverse=True)[:15] # 最新15個
    
    col_sel_race, col_sel_horse = st.columns(2)
    
    selected_chat_race = None
    selected_chat_horse = None
    
    with col_sel_race:
        selected_chat_race = st.selectbox("対象レースを選択 (コンテキスト用)", ["選択なし"] + predicted_races)
        
    with col_sel_horse:
        if selected_chat_race != "選択なし":
            summary_p = os.path.join(get_shap_dir(selected_chat_race), "prediction_summary.json")
            if os.path.exists(summary_p):
                with open(summary_p, 'r', encoding='utf-8') as f:
                    r_data = json.load(f)
                h_names = [h['horse_name'] for h in r_data]
                selected_chat_horse = st.selectbox("メインで聞く馬を選択", ["選択なし"] + h_names)
            else:
                st.selectbox("メインで聞く馬を選択", ["選択なし"], disabled=True)
        else:
            st.selectbox("メインで聞く馬を選択", ["選択なし"], disabled=True)
            
    if st.button("💬 会話履歴をクリア"):
        st.session_state['chat_history_rag'] = []
        st.session_state['chat_target_race_rag'] = None
        st.session_state['chat_target_horse_rag'] = None
        st.success("チャット履歴を初期化しました。")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # セッション状態の管理
    if 'chat_history_rag' not in st.session_state:
        st.session_state['chat_history_rag'] = []
    
    # 履歴の表示
    for message in st.session_state['chat_history_rag']:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # ユーザー入力
    if prompt := st.chat_input("競馬場や今回のレース特性、気になる馬の適性についてAIに質問してください。"):
        st.session_state['chat_history_rag'].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AIの思考・RAGのコンテキスト構築
        with st.chat_message("assistant"):
            with st.spinner("AIがデータベースから情報を検索・分析中..."):
                try:
                    # コンテキスト変数
                    current_race_context = ""
                    horse_context = ""
                    race_context = ""
                    full_history_str = ""
                    
                    if selected_chat_race != "選択なし":
                        s_dir = get_shap_dir(selected_chat_race)
                        s_path = os.path.join(s_dir, "prediction_summary.json")
                        
                        if os.path.exists(s_path):
                            with open(s_path, 'r', encoding='utf-8') as f:
                                horses_data = json.load(f)
                                
                            # 1. レースメタデータのロード
                            try:
                                shutuba_df = scrape_shutuba_table(str(selected_chat_race), use_cache=True)
                                if not shutuba_df.empty:
                                    current_race_context = f"""
                                    【今回のレース開催条件】
                                    - レース名: {shutuba_df['レース名'].iloc[0]}
                                    - 開催場所: {shutuba_df['場所'].iloc[0]}
                                    - コース・距離: {shutuba_df['距離'].iloc[0]}
                                    - 天候 / 馬場: {shutuba_df['天気'].iloc[0]} / {shutuba_df['馬場'].iloc[0]}
                                    """
                            except:
                                pass
                            
                            # 2. 対象馬の情報
                            if selected_chat_horse and selected_chat_horse != "選択なし":
                                target_h = next((h for h in horses_data if h['horse_name'] == selected_chat_horse), None)
                                if target_h:
                                    def clean_fn(feat_name):
                                        return feat_name.replace("1走前_", "前走_").replace("オッズ", "単勝オッズ")
                                    
                                    horse_context = f"""
                                    対象馬: {selected_chat_horse}
                                    予測順位: {target_h['pred_rank']}位
                                    AI予測スコア: {target_h.get('pred_win', 0):.4f}
                                    
                                    【プラス材料】
                                    {chr(10).join([f"- {clean_fn(f['feature'])} (値: {get_original_value_display(f['feature'], f['value'])})" for f in target_h.get('positive_factors', [])[:5]])}
                                    
                                    【マイナス材料】
                                    {chr(10).join([f"- {clean_fn(f['feature'])} (値: {get_original_value_display(f['feature'], f['value'])})" for f in target_h.get('negative_factors', [])[:5]])}
                                    """
                            
                            # 3. 他馬の予測
                            race_context = "\n".join([f"{h['pred_rank']}位: {h['horse_name']}" for h in horses_data])
                            
                            # 4. 全馬の過去5走情報
                            raw_df_path = os.path.join(s_dir, "raw_race_data.csv")
                            if os.path.exists(raw_df_path):
                                try:
                                    try:
                                        raw_df = pd.read_csv(raw_df_path, encoding='utf-8')
                                    except:
                                        raw_df = pd.read_csv(raw_df_path, encoding='shift-jis')
                                    
                                    id_map = {str(h['horse_id']): h['horse_name'] for h in horses_data if 'horse_id' in h}
                                    histories = []
                                    if 'horse_id' in raw_df.columns:
                                        for hid, group in raw_df.groupby('horse_id'):
                                            h_name = id_map.get(str(hid), f"Unknown({hid})")
                                            r_lines = [f"### 馬名: {h_name}"]
                                            for _, r in group.head(5).iterrows():
                                                r_lines.append(f"- {r.get('日付')} {r.get('レース名')}: {r.get('着順')}着 (人:{r.get('人気')}, オ:{r.get('オッズ')}) {r.get('芝・ダート')}{r.get('距離')}m")
                                            histories.append("\n".join(r_lines))
                                    full_history_str = "\n\n".join(histories)
                                except:
                                    pass

                    # システムプロンプト定義
                    system_prompt = f"""
                    あなたは高度な競馬専門AIです。
                    
                    ## レースの文脈情報 (Context)
                    {current_race_context}
                    
                    ## メイン対象馬情報
                    {horse_context}
                    
                    ## AI予測順位一覧
                    {race_context}
                    
                    ## 出走メンバーの直近過去走データ
                    {full_history_str}
                    
                    ## 回答時の重要ルール:
                    1. レースの展開予測、馬の適性、競馬場特性について、客観的なデータ（オッズ、着順、ラップ傾向など）を引用して分析してください。
                    2. 不明な部分は憶測せず、「データ不足」である旨を記述してください。
                    """

                    # ベクトルDB (ChromaDB) 検索
                    additional_context = ""
                    if collection:
                        try:
                            embedding_res = genai.embed_content(
                                model=EMBEDDING_MODEL,
                                content=prompt,
                                task_type="RETRIEVAL_QUERY"
                            )
                            query_emb = embedding_res['embedding']
                            retrieved = collection.query(query_embeddings=[query_emb], n_results=10)
                            if retrieved['documents'] and retrieved['documents'][0]:
                                additional_context = f"\n\n## 関連する過去のレースデータ結果 (Vector DB Search):\n" + "\n".join(retrieved['documents'][0])
                        except:
                            pass

                    # Gemini API リクエスト
                    gemini_history = []
                    for msg in st.session_state['chat_history_rag']:
                        role = "user" if msg["role"] == "user" else "model"
                        gemini_history.append({"role": role, "parts": [msg["content"]]})
                        
                    chat = genai.GenerativeModel(GENERATION_MODEL).start_chat(history=gemini_history[:-1])
                    full_p = f"{system_prompt}{additional_context}\n\nユーザーからの質問: {prompt}"
                    
                    # 出力表示とセッション更新
                    response = chat.send_message(full_p)
                    ai_response = response.text
                    
                    st.markdown(ai_response)
                    st.session_state['chat_history_rag'].append({"role": "assistant", "content": ai_response})
                    
                except Exception as e:
                    st.error(f"Gemini API実行エラー: {e}")

# --- 4. ⚙️ システム管理・更新画面 ---
elif page == "⚙️ システム管理・更新":
    st.markdown('<div class="main-title">⚙️ システム管理・データ同期</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">データベース情報の確認、予測結果が未確定のレース結果のNetkeibaからの同期を実行します。</div>', unsafe_allow_html=True)

    # データベースの統計情報の表示
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown('<div class="custom-card-header">📊 データベース情報 (predictions.db)</div>', unsafe_allow_html=True)
    if os.path.exists(DB_PATH):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                p_count = pd.read_sql_query("SELECT COUNT(*) as count FROM predictions", conn)['count'].iloc[0]
                unconfirmed_count = pd.read_sql_query("SELECT COUNT(DISTINCT race_id) as count FROM predictions WHERE result_rank IS NULL", conn)['count'].iloc[0]
                payout_count = pd.read_sql_query("SELECT COUNT(*) as count FROM payouts", conn)['count'].iloc[0]
                
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("総登録予測データ件数", f"{p_count:,} 件")
            col_stat2.metric("結果未同期のレース数", f"{unconfirmed_count:,} レース")
            col_stat3.metric("払い戻しデータ(payouts)件数", f"{payout_count:,} 件")
        except Exception as e:
            st.error(f"DBの読み込み中にエラーが発生しました: {e}")
    else:
        st.warning("データベースファイルが見つかりません。")
    st.markdown('</div>', unsafe_allow_html=True)

    # レース結果の同期実行エリア
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown('<div class="custom-card-header">🔄 レース結果・確定オッズの同期</div>', unsafe_allow_html=True)
    st.write("予測完了後、確定した着順および配当情報をNetkeibaから取得し、データベースをアップデートします。")
    
    if st.button("🔄 レース結果同期スクリプトを実行する", type="primary"):
        st.info("同期処理プロセスを起動しました。実行状況を監視しています...")
        
        # サブプロセスとして実行
        script_path = os.path.join(PROJECT_ROOT, 'src', 'prediction', 'update_results.py')
        
        log_placeholder = st.empty()
        
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                env=env
            )
            
            full_log = []
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    full_log.append(output.strip())
                    log_placeholder.code("\n".join(full_log[-50:]))
                    
            rc = process.poll()
            if rc == 0:
                st.success("✅ レース結果同期が正常に完了しました！")
            else:
                st.error(f"❌ 同期スクリプトがエラーコード {rc} で異常終了しました。")
                
        except Exception as e:
            st.error(f"プロセスの起動に失敗しました: {e}")
            
    st.markdown('</div>', unsafe_allow_html=True)
