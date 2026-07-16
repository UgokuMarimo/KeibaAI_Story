import streamlit as st
import pandas as pd
import google.generativeai as genai
from explanation.explanation_templates import (
    EXPLANATION_TEMPLATES, 
    get_original_value_display, 
    get_group_for_feature
)

def render_ai_explanation(target_horse_data, collection, generation_model="gemini-2.5-flash"):
    if st.button("詳細解説を生成する (AI)", type="primary"):
        with st.spinner(f"{target_horse_data['horse_name']} の解説を生成中..."):
            # RAG: ベクトルDB検索 (省略無し)
            context_docs = ""
            if collection:
                search_query = f"{target_horse_data['horse_name']}の最近のレース内容"
                try:
                    # Embedding Modelの設定 (build_vector_db.pyと合わせる)
                    EMBEDDING_MODEL = "models/text-embedding-004"
                    
                    # クエリをベクトル化
                    embedding_result = genai.embed_content(
                        model=EMBEDDING_MODEL,
                        content=search_query,
                        task_type="RETRIEVAL_QUERY"
                    )
                    query_embedding = embedding_result['embedding']
                    
                    # ベクトルで検索
                    retrieved = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=3
                    )
                except Exception as e:
                    print(f"[WARN] Vector search failed: {e}")
                    retrieved = {'documents': []}

                if retrieved['documents']:
                    context_docs = "\n".join(retrieved['documents'][0])
            
            # --- 特徴量の整理とグループ化 (m04_predict.pyと統一) ---
            all_factors = target_horse_data.get('positive_factors', []) + target_horse_data.get('negative_factors', [])
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
            提供された機械学習モデルの分析データ（SHAP値）を元に、競走馬「{target_horse_data['horse_name']}」の「勝つための戦術」を明確にする解説文を生成してください。

            # AIの総合評価
            - 予測順位: {target_horse_data['pred_rank']}位
            - 予測勝率: {target_horse_data.get('calc_normalized_prob', 0):.1%}
            - 予測スコア (Raw): {target_horse_data.get('pred_win', target_horse_data.get('pred_win_prob', 0)):.4f}

            # 分析データサマリー
            --- ポジティブ要因 ---
            {"\n".join(positive_themes_list) if positive_themes_list else "特になし"}

            --- ネガティブ要因 ---
            {"\n".join(negative_themes_list) if negative_themes_list else "特になし"}

            # 参考情報 (過去のレース内容など)
            {context_docs if context_docs else "特になし"}
            
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
            model = genai.GenerativeModel(generation_model)
            response = model.generate_content(prompt)
            
            st.markdown(response.text)
