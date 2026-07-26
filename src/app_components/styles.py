"""
KeibaAI Streamlit App - Custom CSS Styles
"""
import streamlit as st

def apply_custom_css():
    """Apply premium dark theme and custom CSS styles to the Streamlit app."""
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
