"""
KeibaAI Streamlit App - Custom CSS Styles
"""
import streamlit as st

def apply_custom_css():
    """白ベースと毬藻グリーン(#1b4332 / #2d6a4f)の目に優しいスタイルを適用する"""
    st.markdown("""
        <style>
        /* 全体背景とフォントの設定 (白ベース & 和モダンナチュラル) */
        .stApp {
            background-color: #f7f9f7;
            color: #212529;
            font-family: 'Noto Sans JP', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        
        /* ヘッダー・毬藻グリーングラデーションタイトル */
        .main-title {
            background: linear-gradient(135deg, #1b4332 0%, #2d6a4f 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 2.2rem;
            margin-bottom: 0.2rem;
            text-align: left;
        }
        
        .subtitle {
            color: #5a6b5d;
            font-size: 1.0rem;
            margin-bottom: 1.5rem;
        }

        /* 毬藻グリーン・カードスタイル */
        .custom-card {
            background: #ffffff;
            border: 1px solid #e2e8e4;
            border-radius: 12px;
            padding: 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 15px rgba(27, 67, 50, 0.04);
        }
        
        .custom-card-header {
            font-weight: 700;
            font-size: 1.15rem;
            color: #1b4332;
            margin-bottom: 0.8rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            border-bottom: 2px solid #e8f5e9;
            padding-bottom: 0.4rem;
        }
        
        /* レース選択用のナチュラルカード */
        .race-grid-card {
            background: #ffffff;
            border: 1px solid #c8d6cb;
            border-radius: 8px;
            padding: 0.8rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            color: #1b4332;
        }
        .race-grid-card:hover {
            border-color: #2d6a4f;
            background: #e8f5e9;
            transform: translateY(-2px);
        }

        /* 予測マーク（印）の装飾バッジ (毬藻グリーン階層) */
        .badge-mark {
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-weight: 800;
            font-size: 0.85rem;
            display: inline-block;
            text-align: center;
        }
        .badge-honmei { background-color: #1b4332; color: white; } /* ◎ 毬藻ダーク */
        .badge-taiko { background-color: #2d6a4f; color: white; }  /* ◯ 毬藻ミディアム */
        .badge-tanana { background-color: #52b788; color: white; } /* ▲ ライトグリーン */
        .badge-renka { background-color: #84a98c; color: white; }  /* △ ソフトグリーン */

        /* 文字サイズ調整 */
        .stMarkdown h1 { font-size: 1.8rem !important; color: #1b4332 !important; }
        .stMarkdown h2 { font-size: 1.4rem !important; color: #1b4332 !important; }
        .stMarkdown h3 { font-size: 1.15rem !important; color: #2d6a4f !important; margin-top: 0.5em !important; margin-bottom: 0.2em !important; }
        .stMarkdown p { font-size: 0.95rem !important; color: #212529 !important; }
        
        /* アコーディオン・拡張エリア */
        .stExpander {
            border: 1px solid #e2e8e4 !important;
            background-color: #ffffff !important;
            border-radius: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True)
