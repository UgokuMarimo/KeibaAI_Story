"""
KeibaAI Streamlit App - System Management View
"""
import os
import sys
import sqlite3
import subprocess
import pandas as pd
import streamlit as st
from src.config import DB_PATH, PROJECT_ROOT

def render_system_view():
    """Render system management and database status view."""
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
