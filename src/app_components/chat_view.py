"""
KeibaAI Streamlit App - AI Chatbot (RAG) View
"""
import os
import json
import pandas as pd
import streamlit as st
import chromadb
import google.generativeai as genai

import src.config
from explanation.explanation_templates import get_original_value_display
from utils.scraper import scrape_shutuba_table

EMBEDDING_MODEL = "models/text-embedding-004"
GENERATION_MODEL = "gemini-2.5-flash"

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

@st.cache_resource
def load_vector_db():
    vector_db_path = os.path.join(src.config.PROJECT_ROOT, "vector_db")
    if not os.path.exists(vector_db_path):
        return None
    try:
        client = chromadb.PersistentClient(path=vector_db_path)
        return client.get_collection(name="race_results")
    except Exception:
        return None

def render_chat_view():
    """Render RAG chatbot view."""
    st.markdown('<div class="main-title">🤖 競馬AIチャット (Gemini RAG)</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">過去データ・予測根拠・展開分析をGeminiと対話形式で深く分析できます。</div>', unsafe_allow_html=True)

    collection = load_vector_db()

    # チャットのセッション・コンテキスト設定
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown('<div class="custom-card-header">⚙️ チャットコンテキストの指定</div>', unsafe_allow_html=True)
    
    # 最近予測されたレースIDの一覧を取得
    predicted_races = []
    if os.path.exists(src.config.SHAP_RESULTS_DIR):
        for root, dirs, files in os.walk(src.config.SHAP_RESULTS_DIR):
            if "prediction_summary.json" in files:
                race_id = os.path.basename(root)
                if race_id.isdigit():
                    predicted_races.append(race_id)
    
    predicted_races = sorted(list(set(predicted_races)), reverse=True)[:15]
    
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
                            except Exception:
                                pass
                            
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
                            
                            race_context = "\n".join([f"{h['pred_rank']}位: {h['horse_name']}" for h in horses_data])
                            
                            raw_df_path = os.path.join(s_dir, "raw_race_data.csv")
                            if os.path.exists(raw_df_path):
                                try:
                                    try:
                                        raw_df = pd.read_csv(raw_df_path, encoding='utf-8')
                                    except Exception:
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
                                except Exception:
                                    pass

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
                        except Exception:
                            pass

                    gemini_history = []
                    for msg in st.session_state['chat_history_rag']:
                        role = "user" if msg["role"] == "user" else "model"
                        gemini_history.append({"role": role, "parts": [msg["content"]]})
                        
                    chat = genai.GenerativeModel(GENERATION_MODEL).start_chat(history=gemini_history[:-1])
                    full_p = f"{system_prompt}{additional_context}\n\nユーザーからの質問: {prompt}"
                    
                    response = chat.send_message(full_p)
                    ai_response = response.text
                    
                    st.markdown(ai_response)
                    st.session_state['chat_history_rag'].append({"role": "assistant", "content": ai_response})
                    
                except Exception as e:
                    st.error(f"Gemini API実行エラー: {e}")
