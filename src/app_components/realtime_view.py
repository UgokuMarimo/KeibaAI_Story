"""
KeibaAI Streamlit App - Realtime Prediction View
"""
import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime, date
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import src.config
from src.config import DB_PATH, PROJECT_ROOT
from explanation.explanation_templates import get_feature_name_display
from prediction.predict import predict_race, load_models
from utils import analytics
from utils.schedule_scraper import get_race_schedule_for_date, get_monthly_schedule_metadata
from app_components.calendar_view import render_schedule_html

@st.cache_resource(show_spinner="予測モデルを読み込んでいます...")
def get_cached_models():
    try:
        models, artifacts = load_models()
        return models, artifacts, None
    except TypeError:
        models, artifacts, model_conf = load_models('B')
        return models, artifacts, model_conf

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

def render_realtime_view(send_discord_notification=True):
    """Render Realtime Race Prediction view."""
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
                        venues = venue_races['venue_name'].unique()
                        venue_tabs = st.tabs(list(venues))
                        
                        for idx, v_name in enumerate(venues):
                            with venue_tabs[idx]:
                                group = venue_races[venue_races['venue_name'] == v_name].copy()
                                try:
                                    group['race_num_int'] = group['race_number'].astype(str).str.extract(r'(\d+)').astype(int)
                                    group = group.sort_values('race_num_int', ascending=True)
                                except Exception:
                                    pass
                                
                                cols = st.columns(4)
                                for b_idx, (_, row) in enumerate(group.iterrows()):
                                    col = cols[b_idx % 4]
                                    r_id = str(row['race_id'])
                                    s_dir = get_shap_dir(r_id)
                                    is_pred = os.path.exists(os.path.join(s_dir, "prediction_summary.json"))
                                    
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
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="custom-card-header">🔮 予測情報表示 (ID: {target_race_id})</div>', unsafe_allow_html=True)
            
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
                    except Exception:
                        pass

                if loaded_df is None and os.path.exists(DB_PATH):
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            db_df = pd.read_sql_query("SELECT * FROM predictions WHERE race_id = ?", conn, params=(str(target_race_id),))
                            if not db_df.empty:
                                db_df.rename(columns={'umaban': '馬番', 'horse_name': '馬名'}, inplace=True)
                                loaded_df = db_df
                    except Exception:
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
                
                if os.path.exists(DB_PATH):
                    try:
                        with sqlite3.connect(DB_PATH) as conn:
                            res_df = pd.read_sql_query("SELECT umaban, result_rank FROM predictions WHERE race_id = ?", conn, params=(str(target_race_id),))
                            if not res_df.empty:
                                res_df['umaban'] = res_df['umaban'].astype(str)
                                result_df['馬番'] = result_df['馬番'].astype(str)
                                result_df = pd.merge(result_df, res_df[['umaban', 'result_rank']], left_on='馬番', right_on='umaban', how='left')
                                result_df['確定着順'] = result_df['result_rank'].fillna('-')
                    except Exception:
                        pass
                
                if 'pred_win' in result_df.columns:
                    total_score = result_df['pred_win'].sum()
                    result_df['win_prob'] = (result_df['pred_win'] / total_score) if total_score > 0 else 0.0
                    result_df['勝率'] = result_df['win_prob'].apply(lambda x: f"{x*100:.1f}%")
                
                def get_mark_badge(rank):
                    if rank == 1: return "◎ (本命)"
                    elif rank == 2: return "○ (対抗)"
                    elif rank == 3: return "▲ (単穴)"
                    elif rank == 4: return "△ (連下)"
                    return "-"
                
                result_df['AI印'] = result_df['pred_rank'].apply(get_mark_badge)
                
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

                st.markdown("---")
                st.markdown("#### 🏇 各出走馬の詳細AI解説 ＆ 要因分析")
                
                horse_list = result_df['馬名'].tolist()
                selected_horse = st.selectbox("解説を表示する馬を選択", horse_list)
                
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
                            top_factors = top_factors[::-1]
                            
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
                            
                            with st.expander("📋 特徴量別寄与度の詳細一覧データ", expanded=False):
                                table_data = [{
                                    "特徴量名": get_feature_name_display(f['feature']),
                                    "SHAP貢献度": f"{f['shap_value']:.4f}",
                                    "特徴量の実際の値": str(f['value'])
                                } for f in all_factors]
                                st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
